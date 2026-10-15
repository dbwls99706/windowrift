from windowrift.geometry import ActorState, Rect, advance


def test_falling_actor_lands_on_a_window_top():
    sprite = ActorState(x=210, y=60, width=50, height=50, vx=0, vy=350)
    window = Rect(180, 130, 260, 300)
    result = advance(sprite, 0.05, Rect(0, 0, 1000, 700), [window])
    assert result.y == 80
    assert result.vy == 0


def test_screen_edge_collision_stays_inside_desktop():
    sprite = ActorState(x=1, y=100, width=60, height=60, vx=-500, vy=0)
    result = advance(sprite, .05, Rect(0, 0, 600, 500), [])
    assert result.x == 0
    assert result.vx > 0


def test_floor_bounce_stops_when_slow():
    sprite = ActorState(x=100, y=439, width=60, height=60, vx=0, vy=3)
    result = advance(sprite, .05, Rect(0, 0, 600, 500), [])
    assert result.y == 440
    assert result.vy < 0
    almost_resting = ActorState(x=100, y=440, width=60, height=60, vx=10, vy=0)
    result = advance(almost_resting, 0.001, Rect(0, 0, 600, 500), [])
    assert result.vy == 0


def test_timestep_is_capped():
    sprite = ActorState(100, 100, 30, 30, vx=0, vy=0)
    a = advance(sprite, 1.0, Rect(0, 0, 1000, 1000), [])
    b = advance(sprite, 0.05, Rect(0, 0, 1000, 1000), [])
    assert a == b
