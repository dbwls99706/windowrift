from windowrift.geometry import Rect
from windowrift.windows import _x11_windows


def test_x11_window_discovery_excludes_own_panel_and_small_children(monkeypatch):
    monkeypatch.setenv('DISPLAY', ':12')
    monkeypatch.setattr('windowrift.windows.shutil.which',
                        lambda name: None if name in ('wmctrl', 'xprop', 'xwininfo') else '/usr/bin/xdotool')

    def fake_command(*args):
        if args[1] == 'search':
            return '101\n102\n103\n'
        if args[1] == 'getwindowname':
            return {'101': 'WindowRift | Control',
                    '102': 'Sample Game', '103': 'Tiny popup'}[args[2]]
        if args[1] == 'getwindowgeometry':
            geometry = {
                '101': (0, 0, 400, 700),
                '102': (40, 60, 900, 500),
                '103': (10, 10, 20, 20),
            }[args[-1]]
            return 'X={}\nY={}\nWIDTH={}\nHEIGHT={}'.format(*geometry)
        raise AssertionError(args)

    monkeypatch.setattr('windowrift.windows._command', fake_command)
    windows = _x11_windows()
    assert len(windows) == 1
    assert windows[0].title == 'Sample Game'
    assert windows[0].bounds.y == 60


def test_parse_wmctrl_geometry_handles_titles_and_bad_lines():
    from windowrift.windows import parse_wmctrl_geometry
    windows = parse_wmctrl_geometry(
        '0x04800001  0  40  55  780  620 host Rift Arcade | Level 1\n'
        'invalid line\n'
        '0x04800004  0 -20  85  340  300 host Paint: 그림판\n'
        '0x04800005  0  10  15  340  300 host WindowRift | Control\n'
    )
    assert [(w.wid, w.title, w.bounds.x) for w in windows] == [
        (0x04800001, 'Rift Arcade | Level 1', 40.0),
        (0x04800004, 'Paint: 그림판', -20.0),
    ]


def test_xwininfo_geometry_extraction(monkeypatch):
    from windowrift.windows import _x11_xwininfo_windows, AppWindow
    def fake(*args):
        if args[0] == 'xprop':
            return '_NET_CLIENT_LIST(WINDOW): window id # 0x40002c'
        return ('xwininfo: Window id: 0x40002c "Rift Arcade - Demo"\nAbsolute upper-left X: 65\nAbsolute upper-left Y: 110\nWidth: 760\nHeight: 600\nMap State: IsViewable\n')
    monkeypatch.setattr('windowrift.windows._command',fake)
    assert _x11_xwininfo_windows() == [AppWindow(0x40002c,'Rift Arcade - Demo', Rect(65,110,760,600))]


def test_chrome_tab_with_windowrift_prefix_is_not_hidden():
    from windowrift.windows import parse_wmctrl_geometry
    from windowrift.omnibox import looks_like_chrome
    listing = (
        "0x00600002  0  825  90  735  680  host WindowRift Collision Lab - Google Chrome\n"
        "0x00400002  0  25  90  760  680  host Minecraft Classic - Google Chrome\n"
        "0x00800002  0  25  90  760  680  host WindowRift | Control\n"
        "0x00800003  0  25  90  760  680  host WindowRift cinematic native actor\n"
    )
    visible = parse_wmctrl_geometry(listing)
    assert len(visible) == 2
    assert {w.title for w in visible} == {
        "WindowRift Collision Lab - Google Chrome",
        "Minecraft Classic - Google Chrome",
    }
    assert all(looks_like_chrome(w) for w in visible)


def test_xwininfo_keeps_windowrift_browser_title(monkeypatch):
    from windowrift.windows import _x11_xwininfo_windows

    def fake(*args):
        if args[0] == "xprop":
            return "_NET_CLIENT_LIST(WINDOW): window id # 0x40002c"
        return (
            'xwininfo: Window id: 0x40002c "WindowRift Collision Lab - Google Chrome"\n'
            'Absolute upper-left X: 825\nAbsolute upper-left Y: 90\n'
            'Width: 735\nHeight: 680\nMap State: IsViewable\n'
        )
    monkeypatch.setattr("windowrift.windows._command", fake)
    assert [w.title for w in _x11_xwininfo_windows()] == [
        "WindowRift Collision Lab - Google Chrome"
    ]
