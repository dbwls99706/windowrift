from windowrift.controller import Controls,KeyLatch,Player,Surface,step,surfaces_for_windows
from windowrift.geometry import Rect
from windowrift.windows import AppWindow

SCREEN=Rect(0,0,1600,900)
ROOF=[Surface('source',Rect(70,250,700,4))]
def run(p,c,n=1,surfaces=ROOF):
    for _ in range(n):p=step(p,c,1/60,SCREEN,surfaces)
    return p

def test_keyboard_movement_is_input_driven():
    start=Player(300,180,45,70,ground='source')
    right=run(start,Controls(right=True),20)
    left=run(start,Controls(left=True),20)
    assert right.x>start.x+40 and left.x<start.x-40
    assert right.facing==1 and left.facing==-1
    assert run(right,Controls(),25).vx < right.vx

def test_keyboard_latch_releases_keys():
    keys=KeyLatch();keys.press('D');keys.press('space')
    assert keys.snapshot().right and keys.snapshot().jump
    keys.release('d');keys.release('space')
    assert keys.snapshot()==Controls()
    assert not keys.press('p')

def test_jump_requires_key_release_and_drop_passes_one_platform():
    first=Player(140,180,45,70,ground='source')
    jumped=run(first,Controls(jump=True))
    assert jumped.jumps==1 and jumped.vy<0
    assert run(jumped,Controls(jump=True),15).jumps==1
    stage=[Surface('source',Rect(70,250,700,4)),Surface('bar',Rect(90,330,450,4))]
    dropped=run(first,Controls(down=True,jump=True),surfaces=stage)
    assert dropped.drops==1 and dropped.ground is None
    landed=run(dropped,Controls(down=True),50,surfaces=stage)
    assert landed.ground=='bar' and landed.y==330-70

def test_chrome_has_a_secondary_landing_surface():
    windows=[AppWindow(1,'Game',Rect(40,250,600,600)),AppWindow(2,'Demo - Google Chrome',Rect(800,170,700,660))]
    surfaces=surfaces_for_windows(windows)
    assert len(surfaces)==3
    assert surfaces[-1].name=='omnibox:2'
    assert surfaces[-1].rect.y>170

def test_edge_bounds_and_no_teleport():
    p=step(Player(1578,880,40,40,vx=800,vy=500),Controls(right=True),4,SCREEN,[])
    assert p.x<=1560 and p.y<=860
    assert step(p,Controls(),0,SCREEN,[])==p
