"""State-backed mob handoff regressions; no process injection or cloned entities."""
import re
import uuid
import pytest
from windowrift.minecraft_mobs import (
    MinecraftMobs, TransferError, uuid_from_nbt, position_from_nbt, flag_from_nbt
)

ORIGINAL_UUID = "d2f5bd2a-b67c-4828-93b4-53afa7690201"


class FakeGame:
    def __init__(self):
        self.mob = {
            "uuid": ORIGINAL_UUID,
            "type": "minecraft:zombie",
            "tags": {"windowrift_demo"},
            "pos": (12.5, 70., 12.5),
            "health": 13.,
            "flags": {"NoAI": 0, "NoGravity": 0, "Invulnerable": 0,
                      "Silent": 0, "PersistenceRequired": 1},
        }
        self.outage = None
        self.duplicate = False
        self.scoreboard = {}
    def matches(self, sel):
        return self.mob and all(
            t in self.mob["tags"] for t in re.findall(r"tag=([^,\]]+)", sel)
        ) and all(
            t == self.mob["type"] for t in re.findall(r"type=([^,\]]+)", sel)
        )
    def command(self, command):
        prefix = "execute in minecraft:overworld run "
        assert command.startswith(prefix), command
        cmd = command[len(prefix):]
        if self.outage and self.outage in cmd:
            raise RuntimeError("Simulated Minecraft disconnect")
        if cmd.startswith("scoreboard objectives add "):
            return "Created new objective"
        if cmd.startswith("scoreboard players set "):
            _, _, _, key, obj, value = cmd.split(" ")
            assert obj == "wr_mobs"
            self.scoreboard[key] = int(value)
            return "Set score"
        if cmd.startswith("execute as "):
            match = re.fullmatch(
                r"execute as (.+) run scoreboard players add (#[0-9a-z]+) wr_mobs 1",
                cmd,
            )
            assert match
            selector, holder = match.groups()
            if self.matches(selector):
                self.scoreboard[holder] += 2 if self.duplicate else 1
            return "Score updated"
        if cmd.startswith("scoreboard players get "):
            _, _, _, holder, objective = cmd.split(" ")
            assert objective == "wr_mobs"
            return f"{holder} has {self.scoreboard[holder]} [wr_mobs]"
        if cmd.startswith("forceload add "):
            return "Marked chunk as force loaded"
        if cmd.startswith("execute if block "):
            return "Test passed, count: 1"
        if cmd.startswith("execute if entity "):
            sel = cmd[len("execute if entity "):]
            count = (2 if self.duplicate else 1) if self.matches(sel) else 0
            return f"Test passed, count: {count}" if count else "Test failed"
        if cmd.startswith("data get entity "):
            selector, key = cmd[len("data get entity "):].rsplit(" ", 1)
            if not self.matches(selector): return "No entity was found"
            m = self.mob
            if key == "UUID":
                n = uuid.UUID(m["uuid"]).int
                words = [((n >> i) & 0xffffffff) for i in (96, 64, 32, 0)]
                words = [v-(1<<32) if v >= (1<<31) else v for v in words]
                return "Zombie has the following entity data: [I; " + ", ".join(map(str,words)) + "]"
            if key == "Pos":
                return "Zombie has the following entity data: [" + ", ".join(str(v)+"d" for v in m["pos"]) + "]"
            if key == "Health": return f"Zombie has the following entity data: {m['health']}f"
            if key in m["flags"]:
                return f"Zombie has the following entity data: {m['flags'][key]}b"
            return "Found no elements matching " + key
        if cmd.startswith("tag "):
            _, selector, _, label = cmd.split(" ")
            assert self.matches(selector)
            self.mob["tags"].add(label)
            return "Added tag"
        if cmd.startswith("data merge entity "):
            match = re.fullmatch(r"data merge entity (\S+) \{(.*)\}", cmd)
            assert match and self.matches(match.group(1))
            for name, val in re.findall(r"(\w+):([01])b", match.group(2)):
                self.mob["flags"][name] = int(val)
            return "Modified entity data"
        if cmd.startswith("tp "):
            _, selector, x,y,z = cmd.split(" ")
            assert self.matches(selector)
            self.mob["pos"] = (float(x), float(y), float(z))
            return "Teleported Zombie"
        raise AssertionError(cmd)


def test_original_uuid_and_health_survive_multiple_roundtrips(tmp_path):
    server = FakeGame()
    core = MinecraftMobs(server, tmp_path / "ledger.json")
    r = core.take("windowrift_demo")
    assert r.native_uuid == ORIGINAL_UUID and r.phase == "outside"
    assert server.mob["pos"] == tuple(float(v) for v in r.vault)
    assert server.mob["health"] == 13.
    assert core.put(r.id, (18,70,18)).native_uuid == ORIGINAL_UUID
    assert server.mob["flags"]["NoAI"] == 0
    core.pick_up(r.id)
    assert core.put(r.id, (19,70,19)).revision == 3
    assert server.mob["uuid"] == ORIGINAL_UUID


def test_native_uuid_tampering_causes_rejection(tmp_path):
    server = FakeGame()
    core = MinecraftMobs(server, tmp_path / "ledger.json")
    r = core.take("windowrift_demo")
    server.mob["uuid"] = str(uuid.uuid4())
    with pytest.raises(TransferError, match="UUID"):
        core.put(r.id, (18,70,18))


def test_recovery_after_interrupted_teleport(tmp_path):
    server = FakeGame()
    core = MinecraftMobs(server, tmp_path / "ledger.json")
    server.outage = "tp "
    with pytest.raises(RuntimeError):
        core.take("windowrift_demo")
    assert core.snapshot()[0].phase == "taking"
    server.outage = None
    assert core.recover()


def test_bad_tag_and_ambiguous_source_rejected(tmp_path):
    server = FakeGame()
    core = MinecraftMobs(server, tmp_path / "ledger.json")
    server.duplicate = True
    with pytest.raises(TransferError, match="Exactly one"):
        core.take("windowrift_demo")
    server.duplicate = False
    with pytest.raises(ValueError):
        core.take("bad tag;execute as @a")


def test_native_nbt_decoders():
    native = uuid.UUID(ORIGINAL_UUID)
    pieces = [(native.int >> s) & 0xffffffff for s in (96,64,32,0)]
    pieces = [n-(1<<32) if n >= 2**31 else n for n in pieces]
    assert uuid_from_nbt("[I; " + ", ".join(map(str, pieces)) + "]") == ORIGINAL_UUID
    assert position_from_nbt("Zombie has data: [12.5d, 70.0d, 12.5d]") == (12.5,70.,12.5)
    assert flag_from_nbt("Zombie has data: 1b") == 1
