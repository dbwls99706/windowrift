"""Same-UUID Minecraft Java living-mob transfer via an operator-owned RCON server.

A captured mob remains the *same live native entity*, temporarily parked in a
force-loaded, protected vault. Its AI does NOT run outside Minecraft; the
desktop visual is a separate model and must be described honestly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re
from uuid import UUID, uuid4

from .minecraft_transfer import _write_json, TransferError, coord, xyz

MOB_TYPES = frozenset({"minecraft:zombie", "minecraft:skeleton", "minecraft:creeper",
                       "minecraft:cow", "minecraft:pig", "minecraft:chicken"})
FLAGS = ("NoAI", "NoGravity", "Invulnerable", "Silent", "PersistenceRequired")
DIMENSION = "minecraft:overworld"
TAG_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,48}\Z")
UUID_PATTERN = re.compile(r"\[I;\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\s*\]")
POS_PATTERN = re.compile(r"\[\s*(-?[\d.]+)d?,\s*(-?[\d.]+)d?,\s*(-?[\d.]+)d?\s*\]")


def uuid_from_nbt(text: str) -> str:
    found = UUID_PATTERN.search(text)
    if found is None:
        raise TransferError("Native Minecraft UUID could not be read")
    n = 0
    for word in found.groups():
        n = (n << 32) | (int(word) & 0xffffffff)
    return str(UUID(int=n))


def position_from_nbt(text: str) -> tuple[float, float, float]:
    found = POS_PATTERN.search(text)
    if found is None:
        raise TransferError("Native Minecraft entity position could not be read")
    result = tuple(float(n) for n in found.groups())
    if not all(math.isfinite(v) and abs(v) < 30000000 for v in result):
        raise TransferError("Invalid native entity position")
    return result


def flag_from_nbt(text: str) -> int:
    if "Found no elements matching" in text:
        return 0
    matches = re.findall(r"(?<!\d)([01])b\b", text)
    if len(matches) != 1:
        raise TransferError("Failed to read native entity NBT flag")
    return int(matches[0])


def result_count(text: str) -> int:
    found = re.search(r"Test passed, count: (\d+)", text)
    if found is not None:
        return int(found.group(1))
    if "Test failed" in text:
        return 0
    raise TransferError("Unrecognized Minecraft entity or block query result: " + text[:100])


@dataclass
class MobRecord:
    id: str
    native_uuid: str
    entity_type: str
    source_tag: str
    bridge_tag: str
    dimension: str
    source: tuple[float, float, float]
    vault: tuple[int, int, int]
    flags: dict[str, int]
    health: float | None
    phase: str = "taking"
    destination: tuple[float, float, float] | None = None
    revision: int = 0
    screen_x: int = 540
    screen_y: int = 240

    @classmethod
    def parse(cls, obj: dict) -> "MobRecord":
        try:
            if obj["entity_type"] not in MOB_TYPES or obj["dimension"] != DIMENSION:
                raise ValueError("Unsupported saved mob")
            if not re.fullmatch(r"[a-f0-9]{32}", obj["id"]):
                raise ValueError("Invalid transfer ID")
            if obj["bridge_tag"] != "wr_" + obj["id"]:
                raise ValueError("Transfer tag mismatch")
            if str(UUID(obj["native_uuid"])) != obj["native_uuid"]:
                raise ValueError("Invalid native UUID")
            if not TAG_PATTERN.fullmatch(obj["source_tag"]):
                raise ValueError("Invalid source tag")
            if obj["phase"] not in ("taking", "outside", "placing", "placed"):
                raise ValueError("Unknown saved state")
            flags = obj["flags"]
            if set(flags) != set(FLAGS) or any(v not in (0, 1) for v in flags.values()):
                raise ValueError("Invalid flags")
            src = tuple(float(v) for v in obj["source"])
            vault = tuple(int(v) for v in obj["vault"])
            coord(*vault)
            dest = (tuple(float(v) for v in obj["destination"])
                    if obj.get("destination") is not None else None)
            if len(src) != 3 or not all(math.isfinite(v) for v in src):
                raise ValueError("Invalid source")
            if obj["phase"] == "placing" and dest is None:
                raise ValueError("Pending destination not recorded")
            if dest is not None and (len(dest) != 3 or not all(math.isfinite(v) for v in dest)):
                raise ValueError("Invalid destination")
            x, y = int(obj.get("screen_x", 540)), int(obj.get("screen_y", 240))
            if max(abs(x), abs(y)) > 32768:
                raise ValueError("Invalid screen coordinates")
            hp = float(obj["health"]) if obj.get("health") is not None else None
            return cls(obj["id"], obj["native_uuid"], obj["entity_type"], obj["source_tag"],
                       obj["bridge_tag"], obj["dimension"], src, vault, flags, hp,
                       obj["phase"], dest, int(obj.get("revision", 0)), x, y)
        except (KeyError, TypeError, ValueError) as exc:
            raise TransferError("Invalid saved Minecraft mob ledger") from exc


class MinecraftMobs:
    """Safe, restricted, identity-preserving stasis for explicitly tagged mobs."""
    def __init__(self, backend, ledger: Path, *,
                 vault_base: tuple[int, int, int] = (10300, 300, 10300)):
        self.backend, self.ledger = backend, Path(ledger)
        self.vault_base = coord(*vault_base)
        if not 8 <= self.vault_base[1] <= 313:
            raise ValueError("Unsafe mob vault height")
        if self.ledger.exists():
            raw = json.loads(self.ledger.read_text(encoding="utf-8"))
            if raw.get("version") != 1 or raw.get("vault_base") != list(self.vault_base):
                raise TransferError("Incompatible mob transfer ledger")
            records = [MobRecord.parse(r) for r in raw["records"]]
            self.records = {r.id: r for r in records}
            if len(records) != len(self.records) or len(records) > 16:
                raise TransferError("Duplicate or excessive saved mobs")
        else:
            self.records: dict[str, MobRecord] = {}

    def _save(self):
        _write_json(self.ledger, {"version": 1, "vault_base": list(self.vault_base),
                                  "records": [asdict(r) for r in self.records.values()]})

    def _command(self, instruction: str) -> str:
        result = self.backend.command(f"execute in {DIMENSION} run {instruction}")
        if not isinstance(result, str):
            raise TransferError("Invalid RCON response")
        return re.sub(r"§.", "", result)

    @staticmethod
    def _selector(record: MobRecord) -> str:
        return f"@e[type={record.entity_type},tag={record.bridge_tag},limit=1]"

    def _count(self, selector: str) -> int:
        return result_count(self._command(f"execute if entity {selector}"))

    def _get(self, selector: str, field: str) -> str:
        return self._command(f"data get entity {selector} {field}")

    def _verify(self, record: MobRecord) -> str:
        selector = self._selector(record)
        if self._count(selector) != 1:
            raise TransferError("Native Minecraft entity missing or duplicated")
        if uuid_from_nbt(self._get(selector, "UUID")) != record.native_uuid:
            raise TransferError("Native entity UUID changed, refusing operation")
        return selector

    def _position(self, selector: str) -> tuple[float, float, float]:
        return position_from_nbt(self._get(selector, "Pos"))

    def _at(self, selector: str, pos: tuple[float, float, float]) -> bool:
        return max(abs(a - b) for a, b in zip(self._position(selector), pos)) < 0.55

    def _load(self, pos: tuple[int, int, int]):
        result = self._command(f"forceload add {pos[0]} {pos[2]}").lower()
        if not any(token in result for token in ("marked", "force", "already")):
            raise TransferError("Could not force-load safe mob position")

    def _air(self, pos: tuple[int, int, int]) -> bool:
        return result_count(self._command(
            f"execute if block {xyz(pos)} minecraft:air")) == 1

    def _space(self, point: tuple[float, float, float]):
        x, y, z = (math.floor(v) for v in point)
        coord(x, y, z)
        if not self._air((x, y, z)) or not self._air((x, y + 1, z)):
            raise TransferError("Destination blocks are not empty")

    def _flags(self, selector: str, flags: dict[str, int]):
        payload = ",".join(f"{name}:{flags[name]}b" for name in FLAGS)
        self._command(f"data merge entity {selector} {{{payload}}}")
        for name in FLAGS:
            if flag_from_nbt(self._get(selector, name)) != flags[name]:
                raise TransferError("Server did not preserve mob flag: " + name)

    def _tp(self, selector: str, point: tuple[float, float, float]):
        self._command(f"tp {selector} {point[0]:.3f} {point[1]:.3f} {point[2]:.3f}")
        if not self._at(selector, point):
            raise TransferError("Minecraft did not confirm mob teleport")

    def _slot(self) -> tuple[int, int, int]:
        used = {r.vault for r in self.records.values()}
        for idx in range(16):
            p = coord(self.vault_base[0] + 4 * idx,
                      self.vault_base[1], self.vault_base[2])
            if p not in used:
                return p
        raise TransferError("All mob vault slots in use")

    def take(self, source_tag: str, entity_type: str = "minecraft:zombie") -> MobRecord:
        if not TAG_PATTERN.fullmatch(source_tag) or source_tag.startswith("wr_"):
            raise ValueError("Use a simple non-reserved marker tag")
        if entity_type not in MOB_TYPES:
            raise TransferError("This mob type is not supported")
        selector = f"@e[type={entity_type},tag={source_tag},limit=1]"
        if self._count(f"@e[type={entity_type},tag={source_tag}]") != 1:
            raise TransferError("Exactly one explicitly tagged mob required")
        if len(self.records) >= 16:
            raise TransferError("Mob vault full")
        native = uuid_from_nbt(self._get(selector, "UUID"))
        if any(r.native_uuid == native for r in self.records.values()):
            raise TransferError("Native entity already tracked")
        source = self._position(selector)
        flags = {name: flag_from_nbt(self._get(selector, name)) for name in FLAGS}
        raw_health = self._get(selector, "Health")
        found = re.search(r"(-?[\d.]+)f\b", raw_health)
        health = float(found.group(1)) if found else None
        vault = self._slot()
        self._load(vault)
        self._space(tuple(float(v) for v in vault))
        record = MobRecord(uuid4().hex, native, entity_type, source_tag, "",
                           DIMENSION, source, vault, flags, health)
        record.bridge_tag = "wr_" + record.id
        self.records[record.id] = record
        self._save()  # Durable intent before the first game mutation.
        self._command(f"tag {selector} add {record.bridge_tag}")
        tracked = self._verify(record)
        self._flags(tracked, {name: 1 for name in FLAGS})
        self._tp(tracked, tuple(float(v) for v in vault))
        record.phase = "outside"
        self._save()
        return record

    def put(self, object_id: str, destination: tuple[int, int, int]) -> MobRecord:
        record = self.records.get(object_id)
        if record is None or record.phase != "outside":
            raise TransferError("Only safely escrowed mobs can be returned")
        dest = coord(*destination)
        point = (dest[0] + 0.5, float(dest[1]), dest[2] + 0.5)
        selector = self._verify(record)
        self._load(dest)
        self._space(point)
        if not self._at(selector, tuple(float(v) for v in record.vault)):
            raise TransferError("Native mob is not at its reserved vault")
        record.phase, record.destination = "placing", point
        self._save()
        self._tp(selector, point)
        self._flags(selector, record.flags)
        record.source, record.phase = point, "placed"
        record.revision += 1
        self._save()
        return record

    def pick_up(self, object_id: str) -> MobRecord:
        record = self.records.get(object_id)
        if record is None or record.phase != "placed":
            raise TransferError("Only restored mobs can be picked up")
        selector = self._verify(record)
        self._load(record.vault)
        record.source = self._position(selector)  # Mob may move under native AI.
        record.phase, record.destination = "taking", None
        self._save()
        self._flags(selector, {name: 1 for name in FLAGS})
        self._tp(selector, tuple(float(v) for v in record.vault))
        record.phase = "outside"
        record.revision += 1
        self._save()
        return record

    def move_desktop(self, object_id: str, x: int, y: int) -> MobRecord:
        record = self.records.get(object_id)
        if record is None or record.phase != "outside":
            raise TransferError("Only mobs outside the world can move on desktop")
        if any(type(v) is not int or abs(v) > 32768 for v in (x, y)):
            raise ValueError("Invalid screen coordinates")
        record.screen_x, record.screen_y = x, y
        self._save()
        return record

    def recover(self) -> list[str]:
        fixed = []
        for record in self.records.values():
            if record.phase not in ("taking", "placing"):
                continue
            selector = self._verify(record)
            vault = tuple(float(v) for v in record.vault)
            if self._at(selector, vault):
                self._flags(selector, {name: 1 for name in FLAGS})
                record.phase, record.destination = "outside", None
            elif record.phase == "taking" and self._at(selector, record.source):
                self._flags(selector, record.flags)
                record.phase = "placed"
            elif (record.phase == "placing" and record.destination and
                  self._at(selector, record.destination)):
                self._flags(selector, record.flags)
                record.phase, record.source = "placed", record.destination
            else:
                raise TransferError("Native mob position changed; manual recovery required")
            fixed.append(record.id)
            self._save()
        return fixed

    def snapshot(self) -> list[MobRecord]:
        return list(self.records.values())
