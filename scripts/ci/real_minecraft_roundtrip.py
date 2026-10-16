"""Game integration proof: query real Minecraft Java state, not a screenshot."""
from __future__ import annotations
import json,os,time
from pathlib import Path
from windowrift.minecraft_rcon import RconClient,RconError
from windowrift.minecraft_transfer import MinecraftTransfer

SOURCE=(10,70,10)
FIRST=(14,70,10)
SECOND=(18,70,12)
ORIENTED='minecraft:oak_stairs[facing=east,half=bottom]'

def sure(response,expected):
    if expected.lower() not in response.lower():
        raise AssertionError(f'Minecraft world verification failed: {response!r}')

def query(server,code):
    return server.command('execute in minecraft:overworld run '+code)

def assert_block(server,loc,material):
    sure(query(server,'execute if block '+' '.join(map(str,loc))+' '+material),'Test passed')

def main():
    server=RconClient(os.environ['WINDOWRIFT_RCON_PASSWORD'],port=25575,timeout=5)
    for _ in range(120):
        try:
            server.command('list')
            break
        except RconError:
            time.sleep(1)
    else:
        raise RuntimeError('Original Minecraft 1.21.1 server not available')
    print('REAL_MINECRAFT_SERVER_AUTHENTICATED=1',flush=True)
    query(server,'forceload add 10 10')
    for position in (SOURCE,FIRST,SECOND):
        query(server,'setblock '+' '.join(map(str,position))+' minecraft:air replace')
    sure(query(server,'setblock 10 70 10 '+ORIENTED+' replace'),'Changed the block')
    assert_block(server,SOURCE,ORIENTED)
    ledger=Path('artifacts/real-minecraft/transfer-ledger.json')
    world=MinecraftTransfer(server,ledger)
    original_id=world.take(SOURCE,'minecraft:oak_stairs').id
    vault=world.records[original_id].vault
    assert_block(server,SOURCE,'minecraft:air')
    assert_block(server,vault,ORIENTED)
    print('REAL_GAME_BLOCK_REMOVED=1',flush=True)

    # Recreate the desktop process and verify the same stored ID is recovered.
    world=MinecraftTransfer(server,ledger)
    assert world.snapshot()[0].id==original_id
    world.move_desktop(original_id,1065,250)
    world.put(original_id,FIRST)
    assert_block(server,FIRST,ORIENTED)
    assert_block(server,vault,'minecraft:air')
    print('REAL_GAME_BLOCK_RESTORED_WITH_ORIENTATION=1',flush=True)

    world.pick_up(original_id)
    assert_block(server,FIRST,'minecraft:air')
    world.put(original_id,SECOND)
    assert_block(server,SECOND,ORIENTED)
    assert_block(server,FIRST,'minecraft:air')
    assert_block(server,vault,'minecraft:air')
    assert world.snapshot()[0].id==original_id
    assert world.snapshot()[0].origin==SOURCE
    assert world.snapshot()[0].revision==3
    print('REAL_MINECRAFT_ROUNDTRIP=PASS',flush=True)
    report={'status':'PASS','game':'Minecraft Java Edition 1.21.1',
       'official_mojang_server':True,'real_world_changes':True,
       'block_properties':{'facing':'east','half':'bottom'},
       'outside_vault_retained_game_state':True,
       'original_windowrift_identity_preserved':True,
       'source_and_vault_clear_after_return':True,
       'game_files_redistributed':False}
    Path('artifacts/real-minecraft/proof.json').write_text(json.dumps(report,indent=2)+'\n')
    print('MINECRAFT_WORLD_STATE_PROOF='+json.dumps(report),flush=True)

if __name__=='__main__':
    main()
