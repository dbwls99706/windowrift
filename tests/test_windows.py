from windowrift.windows import _x11_windows


def test_x11_window_discovery_excludes_own_panel_and_small_children(monkeypatch):
    monkeypatch.setenv('DISPLAY', ':12')

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
