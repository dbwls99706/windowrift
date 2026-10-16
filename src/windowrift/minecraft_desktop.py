"""Actual Minecraft world block as a movable native desktop widget."""
from __future__ import annotations
import argparse,os,sys
from io import BytesIO
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter,QPixmap
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,
                               QLabel,QPushButton,QComboBox,QFormLayout,QMessageBox)
from .minecraft_rcon import RconClient
from .minecraft_transfer import MinecraftTransfer,TransferError,MATERIALS
from .minecraft_textures import render_cube
from .minecraft_cli import parse_location

class WorldBlock(QWidget):
    def __init__(self,panel,identity):
        super().__init__(None)
        self.panel,self.identity=panel,identity
        image,authentic=render_cube(identity.material,panel.jar)
        out=BytesIO()
        image.save(out,'PNG')
        self.pixmap=QPixmap()
        self.pixmap.loadFromData(out.getvalue(),'PNG')
        self.resize(self.pixmap.size())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.setToolTip('Minecraft: '+identity.material+'\nObject: '+identity.id+'\n'+
                        ('Original local game texture' if authentic else 'Diagnostic placeholder; use --game-jar for real texture'))
        self.drag_origin=None
        self.move(identity.screen_x,identity.screen_y)
        self.show()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.drawPixmap(0,0,self.pixmap)
        painter.end()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag_origin=event.globalPosition().toPoint()-self.pos()
            event.accept()

    def mouseMoveEvent(self,event):
        if self.drag_origin is not None:
            self.move(event.globalPosition().toPoint()-self.drag_origin)
            event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.drag_origin is not None:
            self.drag_origin=None
            self.panel.persist_widget(self)
            event.accept()

class TransferPanel(QWidget):
    def __init__(self,engine:MinecraftTransfer,game_jar:Path|None=None):
        super().__init__()
        self.engine,self.jar=engine,game_jar
        self.blocks={}
        self.setWindowTitle('WindowRift | Real Minecraft')
        self.setMinimumWidth(520)
        root=QVBoxLayout(self)
        label=QLabel('Minecraft world → desktop → Minecraft world')
        label.setStyleSheet('font-size:17px;font-weight:bold')
        root.addWidget(label)
        info=QLabel('Blocks here are backed by actual game world cells. Closing the window leaves blocks in escrow until recovered.')
        info.setWordWrap(True)
        root.addWidget(info)
        form=QFormLayout()
        self.source=QLineEdit('10,70,10')
        form.addRow('Source X,Y,Z',self.source)
        self.material=QComboBox()
        for material in sorted(MATERIALS):
            self.material.addItem(material)
        self.material.setCurrentText('minecraft:oak_planks')
        form.addRow('Expected type',self.material)
        self.destination=QLineEdit('14,70,10')
        form.addRow('Destination X,Y,Z',self.destination)
        self.selected=QComboBox()
        form.addRow('Object identity',self.selected)
        root.addLayout(form)
        controls=QHBoxLayout()
        for caption,fn in [('Take real block',self.take),('Return to game',self.put),
                           ('Pick again',self.pick),('Recover',self.recover)]:
            btn=QPushButton(caption)
            btn.clicked.connect(fn)
            controls.addWidget(btn)
        root.addLayout(controls)
        self.status=QLabel('Connect to your own local Minecraft Java Edition server.')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.setStyleSheet('QWidget{background:#16212b;color:#dde7ed}'
                           'QComboBox,QLineEdit,QPushButton{padding:8px;background:#293949;border-radius:5px}')
        self.refresh()

    def selected_id(self):
        value=self.selected.currentData()
        if not value:
            raise TransferError('No object selected')
        return value

    def position(self,control):
        try:
            return parse_location(control.text())
        except argparse.ArgumentTypeError as exc:
            raise ValueError(str(exc)) from exc

    def act(self,fn):
        try:
            result=fn()
        except (TransferError,ValueError,OSError,RuntimeError) as exc:
            QMessageBox.warning(self,'Minecraft transfer',str(exc))
            self.status.setText(str(exc))
            return
        self.status.setText('Confirmed by game: '+str(result))
        self.refresh()

    def take(self):
        self.act(lambda:self.engine.take(self.position(self.source),self.material.currentText()).id)
    def put(self):
        self.act(lambda:self.engine.put(self.selected_id(),self.position(self.destination)).id)
    def pick(self):
        self.act(lambda:self.engine.pick_up(self.selected_id()).id)
    def recover(self):
        self.act(lambda:self.engine.recover())

    def persist_widget(self,widget):
        try:
            self.engine.move_desktop(widget.identity.id,widget.x(),widget.y())
        except (ValueError,TransferError,OSError) as exc:
            self.status.setText('Could not persist desktop position: '+str(exc))

    def refresh(self):
        selected=self.selected.currentData()
        self.selected.clear()
        visible=set()
        for record in self.engine.snapshot():
            self.selected.addItem(record.material+' ['+record.phase+'] '+record.id[:8],record.id)
            if record.phase=='outside':
                visible.add(record.id)
                if record.id not in self.blocks:
                    self.blocks[record.id]=WorldBlock(self,record)
        for ident in list(self.blocks):
            if ident not in visible:
                self.blocks.pop(ident).close()
        if selected is not None:
            index=self.selected.findData(selected)
            if index>=0:self.selected.setCurrentIndex(index)

    def closeEvent(self,event):
        for widget in list(self.blocks.values()):
            widget.close()
        self.blocks.clear()
        super().closeEvent(event)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger',type=Path,default=Path.home()/'.local/share/windowrift/real-minecraft.json')
    p.add_argument('--vault',default='10000,300,10000')
    p.add_argument('--port',type=int,default=25575)
    p.add_argument('--game-jar',type=Path,default=None,help='Your own installed Minecraft client JAR for real textures')
    args=p.parse_args()
    password=os.environ.get('WINDOWRIFT_RCON_PASSWORD','')
    if not password:
        p.error('Set WINDOWRIFT_RCON_PASSWORD')
    try:
        vault=parse_location(args.vault)
        server=RconClient(password,port=args.port)
        server.command('list')
        engine=MinecraftTransfer(server,args.ledger,vault_base=vault)
    except (ValueError,RuntimeError,OSError) as exc:
        p.error(str(exc))
    app=QApplication(sys.argv[:1])
    panel=TransferPanel(engine,args.game_jar)
    panel.show()
    sys.exit(app.exec())

if __name__=='__main__':
    main()
