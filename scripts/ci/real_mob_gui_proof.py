"""Capture the real state-backed desktop mob over an unrelated OS window.

Requires an actual Mojang server and verified client textures; this is
NOT a screenshot from a running Minecraft graphical client.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
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
            panel.selected.setCurrentIndex(panel.selected.findData(record.id))
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
