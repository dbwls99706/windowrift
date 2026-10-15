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
