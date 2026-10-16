"""Record an actual game-state-backed native GUI over an unrelated Chrome page.

A Minecraft Java dedicated server is running. Its block is *absent from the
world* while the independent desktop QWidget exists. After the native UI's
"Return to game" action, the world is checked again for the same block.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from windowrift.minecraft_rcon import RconClient
from windowrift.minecraft_transfer import MinecraftTransfer
from windowrift.minecraft_desktop import TransferPanel

SOURCE=(12,70,15)
DESTINATION=(16,70,15)
MATERIAL='minecraft:oak_planks'
ROOT=Path('artifacts/real-minecraft')

def query(server,cmd):
    return server.command('execute in minecraft:overworld run '+cmd)

def assert_world(server,at,material):
    response=query(server,'execute if block '+' '.join(map(str,at))+' '+material)
    if 'Test passed' not in response:
        raise AssertionError(f'World block mismatch at {at}: {response!r}')

def capture(label):
    QApplication.processEvents()
    image=QApplication.primaryScreen().grabWindow(0)
    output=ROOT/label
    if not image.save(str(output)):
        raise RuntimeError('Qt failed to capture real X11 desktop')
    screenshot=Image.open(output).convert('RGB')
    if screenshot.size!=(1600,900) or not screenshot.getbbox():
        raise AssertionError('Captured desktop is empty or wrong size')
    return output

def main():
    server=RconClient(os.environ['WINDOWRIFT_RCON_PASSWORD'],timeout=7)
    ledger=ROOT/'transfer-ledger.json'
    query(server,'forceload add 12 15')
    query(server,'setblock 12 70 15 '+MATERIAL+' replace')
    query(server,'setblock 16 70 15 minecraft:air replace')
    assert_world(server,SOURCE,MATERIAL)
    world=MinecraftTransfer(server,ledger)
    record=world.take(SOURCE,MATERIAL)
    assert_world(server,SOURCE,'minecraft:air')
    assert_world(server,record.vault,MATERIAL)

    app=QApplication([])
    app.setStyle('Fusion')
    panel=TransferPanel(world,Path(os.environ['WR_MINECRAFT_CLIENT']))
    panel.setGeometry(850,130,580,360)
    panel.show()
    actor=panel.blocks.get(record.id)
    if actor is None:
        raise AssertionError('Actual world escrow did not produce native block widget')
    actor.move(260,260)
    panel.persist_widget(actor)
    if not actor.toolTip().endswith('Original local game texture'):
        raise AssertionError('Native actor did not load original Mojang client texture')
    panel.destination.setText('16,70,15')
    index=panel.selected.findData(record.id)
    panel.selected.setCurrentIndex(index)
    phase={'stage':'created'}
    def act():
        try:
            assert_world(server,SOURCE,'minecraft:air')
            assert_world(server,record.vault,MATERIAL)
            capture('live-block-outside.png')
            print('REAL_NATIVE_GAME_OBJECT_ON_DESKTOP=1',flush=True)
            panel.put()
            assert_world(server,DESTINATION,MATERIAL)
            assert_world(server,record.vault,'minecraft:air')
            assert record.id not in panel.blocks
            capture('live-block-returned.png')
            phase['stage']='restored'
            result={'gui':'PASS','source':'official Minecraft Java Edition 1.21.1 server',
                'real_game_state_mutations':True,
                'same_object_id':record.id,
                'original_texture_from_official_verified_local_client':True,
                'out_of_game_native_widget':True,
                'returned_by_native_ui':True,
                'headless_server_not_gameplay_client':True}
            (ROOT/'gui-proof.json').write_text(json.dumps(result,indent=2)+'\n')
            print('REAL_WORLD_GUI_ROUNDTRIP='+json.dumps(result),flush=True)
        except Exception as exc:
            phase['stage']='failed'
            phase['error']=repr(exc)
            print('REAL_WORLD_GUI_ERROR='+repr(exc),flush=True)
        finally:
            panel.close()
            app.quit()
    QTimer.singleShot(450,act)
    app.exec()
    if phase['stage']!='restored':
        raise RuntimeError('Game-backed Qt desktop proof failed: '+str(phase))

if __name__=='__main__':
    main()
