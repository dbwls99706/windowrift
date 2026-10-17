from pathlib import Path
import json
import pytest

from windowrift.desktop_world import Block, DesktopWorld, MATERIALS


def test_snap_stacking_and_arbitrary_screen_coordinates():
    world = DesktopWorld(size=48)
    assert world.place(1100, 120, 'planks')
    assert world.place(1100, 72, 'stone')
    assert world.place(-5, 20, 'dirt')
    assert {(b.x,b.y,b.material) for b in world.blocks} == {
        (1056,96,'planks'),(1056,48,'stone'),(-48,0,'dirt')
    }
    assert not world.place(1100, 72, 'stone')
    assert world.place(1100, 72, 'dirt')


def test_drag_line_builds_solid_bridge_and_single_undo():
    w = DesktopWorld()
    w.begin()
    assert w.stroke_to((600,450),(1100,450), tool='place',material='planks') == 11
    assert w.commit()
    assert len(w.blocks) == 11
    assert w.undo() and not w.blocks
    assert w.redo() and len(w.blocks) == 11


def test_mine_drag_and_idempotent():
    w = DesktopWorld()
    w.stroke_to((0,0),(144,0),tool='place')
    w.begin()
    assert w.stroke_to((0,0),(144,0),tool='mine') == 4
    assert w.commit() and not w.blocks
    assert w.undo() and len(w.blocks) == 4
    assert not w.mine(111,111)


def test_save_reload_persists_world_without_website(tmp_path):
    path = tmp_path/'saved.json'
    w=DesktopWorld(size=48)
    w.place(1056, 240,'planks')
    w.place(1104,240,'stone')
    w.save(path)
    assert DesktopWorld.load(path).blocks == w.blocks
    assert json.loads(path.read_text())['blocks'][0]['material'] in MATERIALS
    assert DesktopWorld.load(tmp_path/'missing.json').blocks == ()


def test_malformed_file_rejected():
    w=DesktopWorld()
    raw=json.loads(w.to_json())
    for item in [{'x':10,'y':0,'material':'stone'}, {'x':0,'y':0,'material':'hack'},
                 {'x':True,'y':0,'material':'dirt'}]:
        with pytest.raises(ValueError):
            DesktopWorld.from_json(json.dumps({**raw,'blocks':[item]}))
    with pytest.raises(ValueError): DesktopWorld.from_json('[]')
    with pytest.raises(ValueError): DesktopWorld.from_json(json.dumps({**raw,'blocks':[{'x':0,'y':0,'material':'dirt'}]*2}))


def test_capacity_guard():
    w=DesktopWorld(max_blocks=1)
    assert w.place(0,0)
    with pytest.raises(ValueError,match='limit'):
        w.place(48,0)
    assert len(w.blocks)==1


def test_no_screen_or_browser_binding():
    w=DesktopWorld()
    w.place(960,480)
    snapshot=w.to_json()
    assert 'chrome' not in snapshot.lower() and 'window' not in snapshot.lower()
    assert Block(960,480,'planks') in w.blocks

def test_desktop_collision_for_any_adapter_actor():
    w = DesktopWorld(size=48)
    w.place(96, 144, 'stone')
    w.place(-48, 144, 'planks')
    assert w.colliding_blocks(100, 100, 24, 44) == ()
    assert w.supported_position(100, 100, 24, 44)
    assert not w.supported_position(144, 100, 24, 44)
    assert len(w.colliding_blocks(110, 130, 20, 20)) == 1
    assert len(w.colliding_blocks(-40, 140, 20, 20)) == 1
    assert w.colliding_blocks(144, 144, 10, 10) == ()


@pytest.mark.parametrize('args', [
    (0, 0, 0, 10), (0, 0, -1, 10),
    (float('nan'), 0, 10, 10),
    (0, float('inf'), 10, 10),
    (0, 0, float('inf'), 10),
    (True, 0, 10, 10),
])
def test_desktop_collision_rejects_invalid_geometry(args):
    with pytest.raises(ValueError):
        DesktopWorld().colliding_blocks(*args)
