"""Native Minecraft block UI smoke test, executed offscreen on CI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')

from PySide6.QtWidgets import QApplication
from windowrift.minecraft_desktop import TransferPanel
from windowrift.minecraft_transfer import BlockIdentity

class StubEngine:
    def __init__(self):
        self.block=BlockIdentity(
            '1234567890abcdef1234567890abcdef','minecraft:stone','minecraft:overworld',
            (10,70,10),(10000,300,10000),'outside',origin=(10,70,10))
        self.moved=None

    def snapshot(self):
        return [self.block]

    def move_desktop(self,ident,x,y):
        assert ident==self.block.id
        self.moved=(x,y)
        self.block.screen_x=x
        self.block.screen_y=y

def test_native_desktop_widget_is_backed_by_real_block_identity():
    app=QApplication.instance() or QApplication([])
    world=StubEngine()
    panel=TransferPanel(world,None)
    assert world.block.id in panel.blocks
    sprite=panel.blocks[world.block.id]
    assert sprite.width()>64
    assert sprite.height()>64
    assert 'Minecraft' in sprite.toolTip()
    sprite.move(750,300)
    panel.persist_widget(sprite)
    assert world.moved==(750,300)
    panel.close()
    assert app is not None
