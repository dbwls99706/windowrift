"""Tests for actual game-backed blocks, using a deterministic fake game protocol."""
import json,re
import pytest
from windowrift.minecraft_transfer import MinecraftTransfer,TransferError,coord

class FakeWorld:
    def __init__(self):
        self.cells={}
        self.fail_on=None
    def block(self,p):
        return self.cells.get(p,('minecraft:air',None))
    def command(self,command):
        if self.fail_on and self.fail_on in command:
            raise RuntimeError('Injected game outage')
        matched=re.fullmatch(r'execute in minecraft:overworld run (.+)',command)
        assert matched,command
        instruction=matched.group(1)
        if instruction.startswith('forceload add '):
            return 'Marked chunk as force loaded'
        if instruction.startswith('execute if block '):
            args=instruction.split()
            pos=tuple(map(int,args[3:6]))
            return 'Test passed, count: 1' if self.block(pos)[0]==args[6] else 'Test failed'
        if instruction.startswith('execute if blocks '):
            args=instruction.split()
            pos=tuple(map(int,args[3:6]))
            other=tuple(map(int,args[9:12]))
            return 'Test passed, count: 1' if self.block(pos)==self.block(other) else 'Test failed'
        if instruction.startswith('clone '):
            args=instruction.split()
            src=tuple(map(int,args[1:4]))
            dst=tuple(map(int,args[7:10]))
            assert args[1:4]==args[4:7] and args[10:]==['replace','force']
            self.cells[dst]=self.block(src)
            return 'Successfully cloned 1 block(s)'
        if instruction.startswith('setblock '):
            args=instruction.split()
            pos=tuple(map(int,args[1:4]))
            self.cells.pop(pos,None)
            return 'Changed the block at location'
        raise AssertionError(instruction)

def seed(game,position=(10,70,10),kind='minecraft:oak_stairs'):
    game.cells[position]=(kind,{'facing':'east','half':'bottom'})

def engine(tmp_path,game):
    return MinecraftTransfer(game,tmp_path/'journal.json')

def test_real_block_state_and_identity_survive_repeated_world_transfers(tmp_path):
    game=FakeWorld();seed(game)
    world=engine(tmp_path,game)
    rec=world.take((10,70,10),'minecraft:oak_stairs')
    assert game.block((10,70,10))[0]=='minecraft:air'
    assert game.block(rec.vault)[1]['facing']=='east'
    restarted=engine(tmp_path,game)
    assert restarted.snapshot()[0].id==rec.id
    restarted.move_desktop(rec.id,1200,400)
    assert engine(tmp_path,game).records[rec.id].screen_x==1200
    restarted.put(rec.id,(15,70,10))
    assert game.block((15,70,10))[1]['facing']=='east'
    assert game.block(rec.vault)[0]=='minecraft:air'
    restarted.pick_up(rec.id)
    restarted.put(rec.id,(17,70,10))
    assert restarted.records[rec.id].id==rec.id
    assert restarted.records[rec.id].revision==3
    assert restarted.records[rec.id].origin==(10,70,10)

def test_fails_closed_on_wrong_material_or_occupied_destination(tmp_path):
    game=FakeWorld();seed(game)
    world=engine(tmp_path,game)
    with pytest.raises(TransferError,match='mismatch'):
        world.take((10,70,10),'minecraft:stone')
    assert not world.snapshot()
    rec=world.take((10,70,10),'minecraft:oak_stairs')
    game.cells[(16,70,10)]=('minecraft:stone',None)
    with pytest.raises(TransferError,match='occupied'):
        world.put(rec.id,(16,70,10))
    assert world.records[rec.id].phase=='outside'

def test_recover_interrupted_pickup_with_duplicate_escrow(tmp_path):
    game=FakeWorld();seed(game)
    world=engine(tmp_path,game)
    game.fail_on='setblock 10 70 10'
    with pytest.raises(RuntimeError,match='Injected'):
        world.take((10,70,10),'minecraft:oak_stairs')
    game.fail_on=None
    rec=world.snapshot()[0]
    assert engine(tmp_path,game).recover()==[rec.id]
    assert game.block((10,70,10))[0]=='minecraft:oak_stairs'
    assert game.block(rec.vault)[0]=='minecraft:air'

def test_recover_interrupted_return_by_clearing_verified_duplicate(tmp_path):
    game=FakeWorld();seed(game)
    world=engine(tmp_path,game)
    rec=world.take((10,70,10),'minecraft:oak_stairs')
    game.fail_on=f'setblock {rec.vault[0]} {rec.vault[1]} {rec.vault[2]}'
    with pytest.raises(RuntimeError,match='Injected'):
        world.put(rec.id,(20,70,20))
    game.fail_on=None
    new_world=engine(tmp_path,game)
    assert new_world.recover()==[rec.id]
    assert new_world.records[rec.id].phase=='placed'
    assert game.block(rec.vault)[0]=='minecraft:air'
    assert game.block((20,70,20))[1]['facing']=='east'

def test_vault_tampering_and_cross_vault_source_prohibited(tmp_path):
    game=FakeWorld();seed(game)
    world=engine(tmp_path,game)
    rec=world.take((10,70,10),'minecraft:oak_stairs')
    with pytest.raises(TransferError,match='vault'):
        world.take(rec.vault,'minecraft:oak_stairs')
    game.cells[rec.vault]=('minecraft:dirt',None)
    with pytest.raises(TransferError,match='Vault'):
        world.put(rec.id,(15,70,10))
    assert game.block((15,70,10))[0]=='minecraft:air'

def test_saved_identity_and_invalid_coordinates(tmp_path):
    game=FakeWorld();seed(game)
    rec=engine(tmp_path,game).take((10,70,10),'minecraft:oak_stairs')
    saved=json.loads((tmp_path/'journal.json').read_text())
    assert saved['records'][0]['id']==rec.id
    assert 'password' not in str(saved)
    with pytest.raises(ValueError):
        coord(0,320,0)

def test_multiple_blocks_independent_escrow_slots(tmp_path):
    game=FakeWorld();seed(game)
    seed(game,(11,70,10),'minecraft:stone')
    world=engine(tmp_path,game)
    a=world.take((10,70,10),'minecraft:oak_stairs')
    b=world.take((11,70,10),'minecraft:stone')
    assert a.vault!=b.vault
    world.put(a.id,(18,70,10))
    world.put(b.id,(19,70,10))
    assert game.block((18,70,10))[0]=='minecraft:oak_stairs'
    assert game.block((19,70,10))[0]=='minecraft:stone'
