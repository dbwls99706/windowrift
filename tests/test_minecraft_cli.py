import pytest
from windowrift.minecraft_cli import build_parser,parse_location

def test_cli_parses_game_coordinates():
    p=build_parser()
    args=p.parse_args(['take','--at','10,70,-20','--material','minecraft:oak_stairs'])
    assert args.at==(10,70,-20)
    with pytest.raises(Exception):
        parse_location('10,invalid,20')
    with pytest.raises(SystemExit):
        p.parse_args(['take','--at','10,70,10','--material','minecraft:chest'])
