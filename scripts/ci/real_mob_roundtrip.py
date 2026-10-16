"""Roundtrip a SAME-UUID zombie on an original, verified Mojang 1.21.1 server."""
from __future__ import annotations
import json
import os
from pathlib import Path
import time

from windowrift.minecraft_rcon import RconClient, RconError
from windowrift.minecraft_mobs import MinecraftMobs, uuid_from_nbt, flag_from_nbt

OUT = Path("artifacts/real-mob")
TAG = "windowrift_ci_mob"


def q(client, statement):
    return client.command("execute in minecraft:overworld run " + statement)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    client = RconClient(os.environ["WINDOWRIFT_RCON_PASSWORD"], timeout=10)
    for _ in range(120):
        try:
            client.command("list")
            break
        except RconError:
            time.sleep(1)
    else:
        raise RuntimeError("Mojang server RCON did not start")
    q(client, "time set midnight")
    for x, z in ((12, 12), (20, 20), (24, 20)):
        q(client, f"forceload add {x} {z}")
        q(client, f"setblock {x} 69 {z} minecraft:stone replace")
        for y in (70, 71):
            q(client, f"setblock {x} {y} {z} minecraft:air replace")
    cmd = ("summon minecraft:zombie 12.5 70 12.5 "
           '{PersistenceRequired:1b,Health:13.0f,Tags:["windowrift_ci_mob"],'
           "NoAI:0b,NoGravity:0b,Invulnerable:0b,Silent:0b}")
    reply = q(client, cmd)
    if "Summoned" not in reply:
        raise RuntimeError(f"Cannot spawn test zombie: {reply}")
    selector = f"@e[type=minecraft:zombie,tag={TAG},limit=1]"
    native_id = uuid_from_nbt(q(client, "data get entity " + selector + " UUID"))
    health = q(client, "data get entity " + selector + " Health")
    print("ORIGINAL_NATIVE_MOB=" + json.dumps({"uuid": native_id, "health": health}), flush=True)
    engine = MinecraftMobs(client, OUT / "mobs-ledger.json")
    mob = engine.take(TAG, "minecraft:zombie")
    assert mob.native_uuid == native_id and mob.phase == "outside"
    assert engine._at(engine._selector(mob), tuple(map(float, mob.vault)))
    assert flag_from_nbt(q(client, "data get entity " + selector + " NoAI")) == 1
    print("MOB_NATIVE_UUID_SAFELY_REMOVED_FROM_SOURCE=" + native_id, flush=True)
    engine = MinecraftMobs(client, OUT / "mobs-ledger.json")
    assert engine.records[mob.id].native_uuid == native_id
    engine.move_desktop(mob.id, 1080, 190)
    returned = engine.put(mob.id, (20, 70, 20))
    assert returned.native_uuid == native_id
    assert flag_from_nbt(q(client, "data get entity " + selector + " NoAI")) == 0
    assert flag_from_nbt(q(client, "data get entity " + selector + " PersistenceRequired")) == 1
    assert engine._at(engine._selector(returned), (20.5, 70., 20.5))
    assert q(client, "data get entity " + selector + " Health") == health
    engine.pick_up(mob.id)
    assert engine.records[mob.id].phase == "outside"
    again = engine.put(mob.id, (24, 70, 20))
    assert again.native_uuid == native_id and again.revision == 3
    result = {
        "version": "1.21.1",
        "same_native_minecraft_entity_uuid": native_id,
        "windowrift_transfer_id": mob.id,
        "native_health_preserved": health,
        "native_ai_restored": True,
        "independent_desktop_projection": True,
        "actual_gameplay_client_footage": False,
        "source": "verified original Mojang dedicated server",
        "status": "PASS",
    }
    (OUT / "mob-proof.json").write_text(json.dumps(result, indent=2) + "\n")
    print("MINECRAFT_NATIVE_MOB_ROUNDTRIP=" + json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
