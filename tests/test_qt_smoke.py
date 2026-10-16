"""Main window smoke test; runs with Qt offscreen on CI, skips without PySide6."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

pytest.importorskip("PySide6")


def test_control_panel_initializes_and_closes(monkeypatch):
    from PySide6.QtWidgets import QApplication
    import windowrift.app as ui

    class BridgeStub:
        token = "test-internal-session-token"
        error = None
        def start(self): pass
        def stop(self): pass
        def publish_actors(self, actors): pass

    monkeypatch.setattr(ui, "BrowserBridge", BridgeStub)
    monkeypatch.setattr(ui, "list_windows", lambda: [])
    app = QApplication.instance() or QApplication([])
    panel = ui.ControlPanel()
    assert panel.windowTitle() == "WindowRift | Control"
    assert panel.track_motion.isEnabled() is False
    panel.live_mode.setChecked(True)
    assert panel.track_motion.isEnabled() is True
    panel.close()
    assert app is not None


def test_chrome_portal_changes_actor_geometry_and_restores(monkeypatch):
    from PIL import Image
    from PySide6.QtWidgets import QApplication
    import windowrift.app as ui
    from windowrift.geometry import Rect
    from windowrift.windows import AppWindow

    class BridgeStub:
        token = "test-internal-session-token"
        error = None
        def start(self): pass
        def stop(self): pass
        def publish_actors(self, actors): pass

    chrome = AppWindow(42, "Search - Chromium", Rect(850, 100, 740, 700))
    monkeypatch.setattr(ui, "BrowserBridge", BridgeStub)
    monkeypatch.setattr(ui, "list_windows", lambda: [chrome])
    app = QApplication.instance() or QApplication([])
    panel = ui.ControlPanel()
    assert panel.chrome_targets.count() == 1
    sprite = ui.Sprite(Image.new("RGBA", (80, 80), (30, 190, 150, 255)), 300, 350, 90)
    sprite.actor_id = 7
    panel.sprites.append(sprite)
    try:
        panel.dock_in_chrome()
        assert 7 in panel._browser_docks
        assert sprite.height() == 58
        panel.tick()
        panel.release_from_chrome()
        assert 7 not in panel._browser_docks
        assert sprite.height() == 90
    finally:
        panel.close()
    assert app is not None


def test_keyboard_play_moves_actor_when_keys_are_pressed(monkeypatch):
    import time
    from PIL import Image
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    import windowrift.app as ui
    from windowrift.geometry import Rect
    from windowrift.windows import AppWindow

    class BridgeStub:
        token = "test-local-browser-session-token"
        error = None
        def start(self): pass
        def stop(self): pass
        def publish_actors(self, actors): pass

    source = AppWindow(15,"Example source",Rect(130,290,440,420))
    browser = AppWindow(19,"Search - Google Chrome",Rect(650,190,720,650))
    monkeypatch.setattr(ui,"BrowserBridge",BridgeStub)
    monkeypatch.setattr(ui,"list_windows",lambda:[source,browser])
    app=QApplication.instance() or QApplication([])
    panel=ui.ControlPanel()
    sprite=ui.Sprite(Image.new('RGBA',(50,60),(40,180,220,255)),320,470,60)
    sprite.actor_id=42
    panel.sprites.append(sprite)
    panel.selected=source
    try:
        panel.toggle_control()
        assert panel._play_id==42
        before=sprite.state.x
        QTest.keyPress(panel,Qt.Key.Key_D)
        panel._last=time.monotonic()-.04
        panel.tick()
        assert sprite.state.x>before
        QTest.keyPress(panel,Qt.Key.Key_Space)
        panel._last=time.monotonic()-.04
        panel.tick()
        assert panel._player.jumps==1
        QTest.keyRelease(panel,Qt.Key.Key_Space)
        QTest.keyRelease(panel,Qt.Key.Key_D)
        QTest.keyPress(panel,Qt.Key.Key_Escape)
        assert panel._play_id is None
    finally:
        panel.close()
    assert app is not None
