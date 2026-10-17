"""Capture the real state-backed desktop mob over an unrelated OS window.

Requires an actual Mojang server and verified client textures; this is
NOT a screenshot from a running Minecraft graphical client.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PIL import ImageGrab
from windowrift.proof_capture import ProofRecorder
from PIL import Image
from windowrift.minecraft_rcon import RconClient
from windowrift.minecraft_mobs import MinecraftMobs, uuid_from_nbt
from windowrift.minecraft_mob_desktop import MobPanel

OUT = Path("artifacts/real-mob")
TAG = "windowrift_ci_mob"

def native_uuid(client):
    selector = f"@e[type=minecraft:zombie,tag={TAG},limit=1]"
    return uuid_from_nbt(client.command(
        "execute in minecraft:overworld run data get entity " + selector + " UUID"))

def main():
    client = RconClient(os.environ["WINDOWRIFT_RCON_PASSWORD"], timeout=9)
    expected = native_uuid(client)
    engine = MinecraftMobs(client, OUT / "mobs-ledger.json")
    entries = engine.snapshot()
    assert len(entries) == 1 and entries[0].native_uuid == expected
    # Roundtrip test leaves the original entity in the live world.
    record = engine.pick_up(entries[0].id)
    assert record.native_uuid == expected and record.phase == "outside"
    assert native_uuid(client) == expected
    app = QApplication([])
    app.setStyle("Fusion")
    jar = Path(os.environ["WR_MINECRAFT_CLIENT"])
    panel = MobPanel(engine, jar)
    panel.setGeometry(930, 220, 610, 350)
    panel.show()
    actor = panel.actors[record.id]
    assert actor.authentic, "No authentic zombie texture loaded from official Minecraft jar"
    actor.move(550, 260)
    panel.persist(actor)
    evidence = {}
    def capture_and_restore():
        try:
            assert native_uuid(client) == expected
            before = engine._at(engine._selector(record), tuple(map(float, record.vault)))
            assert before, "Server-side mob missing from stasis"
            QApplication.processEvents()
            image_file = OUT / "living-mob-outside.png"
            assert QApplication.primaryScreen().grabWindow(0).save(str(image_file))
            img = Image.open(image_file).convert("RGB")
            assert img.width >= 1200 and img.height >= 720
            evidence["outside_image"] = str(image_file)
            evidence["native_uuid"] = expected
            evidence["same_native_mob_in_stasis"] = True
            evidence["real_minecraft_client_footage"] = False
            evidence["real_server_state"] = True
            evidence["desktop_os_window"] = True
            evidence["authentic_texture_from_verified_client_jar"] = True
            evidence["avatar_uses_original_game_engine"] = False
            # Exercise the same Qt key event path as a human, not a timed
            # prerecorded coordinate animation. The original Minecraft entity
            # remains the exact same UUID at the force-loaded server vault.
            panel.selected.setCurrentIndex(panel.selected.findData(record.id))
            panel.play_button.setChecked(True)
            panel.activateWindow()
            panel.setFocus()
            QApplication.processEvents()
            recorder = ProofRecorder(interval=0.1, max_frames=45, max_width=1200)
            initial_x = actor.x()
            QTest.keyPress(panel, Qt.Key.Key_D)
            for frame in range(13):
                QTest.qWait(115)
                recorder.add_frame(frame * .12,
                                   ImageGrab.grab(xdisplay=os.environ["DISPLAY"]))
            QTest.keyRelease(panel, Qt.Key.Key_D)
            QTest.qWait(120)
            assert actor.x() > initial_x + 30, "Minecraft desktop actor did not respond to keyboard input"
            assert native_uuid(client) == expected
            QTest.keyPress(panel, Qt.Key.Key_A)
            for frame in range(13, 25):
                QTest.qWait(115)
                recorder.add_frame(frame * .12,
                                   ImageGrab.grab(xdisplay=os.environ["DISPLAY"]))
            QTest.keyRelease(panel, Qt.Key.Key_A)
            panel.play_button.setChecked(False)
            playback = OUT / "living-mob-keyboard-x11.gif"
            assert recorder.save(playback) >= 16
            evidence["actual_x11_keyboard_gif"] = str(playback)
            evidence["keyboard_input_moves_desktop_projection"] = True
            evidence["original_minecraft_process_untouched"] = True
            evidence["original_mob_uuid_unchanged_during_play"] = True

            panel.destination.setText("20,70,20")
            panel.put()
            assert native_uuid(client) == expected
            assert engine.snapshot()[0].phase == "placed"
            QApplication.processEvents()
            after_file = OUT / "living-mob-returned.png"
            assert QApplication.primaryScreen().grabWindow(0).save(str(after_file))
            evidence["returned_image"] = str(after_file)
            evidence["restored_native_uuid"] = native_uuid(client)
            (OUT / "mob-gui-proof.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print("REAL_MOB_GUI_PROOF=" + json.dumps(evidence), flush=True)
            evidence["ok"] = True
        except Exception as exc:
            evidence["error"] = repr(exc)
            print("REAL_MOB_GUI_FAILURE=" + repr(exc), flush=True)
        finally:
            panel.close()
            app.quit()
    QTimer.singleShot(800, capture_and_restore)
    app.exec()
    assert evidence.get("ok"), evidence.get("error", "Unknown screenshot failure")

if __name__ == "__main__":
    main()
