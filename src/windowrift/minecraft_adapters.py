"""Adapters wrap real game-owned state rather than scanned screenshots."""
from __future__ import annotations

from .portal_api import Capability, ObjectState
from .minecraft_transfer import MinecraftTransfer
from .minecraft_mobs import MinecraftMobs


class MinecraftBlockAdapter:
    capability = Capability(
        app="minecraft-java:block", kinds=("block",),
        native_state=True, native_identity=False, remove_from_source=True,
        return_to_source=True, desktop_visual=True,
        interaction=("drag", "escrow", "place", "pickup"),
        restrictions="Vanilla 1.21.1 server RCON; whitelist blocks only. "
                     "Stable WindowRift ID is not a native block UUID.",
    )

    def __init__(self, engine: MinecraftTransfer):
        self.engine = engine

    @staticmethod
    def _state(r):
        return ObjectState("minecraft-java:block", r.id, "block", None,
                           "outside" if r.phase == "outside" else
                           "inside" if r.phase == "placed" else "pending",
                           r.screen_x, r.screen_y,
                           {"material": r.material, "revision": r.revision,
                            "source": list(r.source), "vault": list(r.vault)})

    def objects(self):
        return tuple(self._state(r) for r in self.engine.snapshot())

    def take(self, source, material):
        return self._state(self.engine.take(source, material))

    def put(self, object_id, destination):
        return self._state(self.engine.put(object_id, destination))

    def move(self, object_id, x, y):
        return self._state(self.engine.move_desktop(object_id, x, y))

    def recover(self):
        return self.engine.recover()


class MinecraftMobAdapter:
    capability = Capability(
        app="minecraft-java:mob", kinds=("living-entity",),
        native_state=True, native_identity=True, remove_from_source=True,
        return_to_source=True, desktop_visual=True,
        interaction=("drag", "stasis", "restore"),
        restrictions="Only explicitly tagged supported living mobs on an owned "
                     "vanilla 1.21.1 server. Same UUID lives in an isolated, "
                     "force-loaded world vault; its Minecraft AI is paused.",
    )

    def __init__(self, engine: MinecraftMobs):
        self.engine = engine

    @staticmethod
    def _state(r):
        return ObjectState("minecraft-java:mob", r.id, "living-entity",
                           r.native_uuid,
                           "outside" if r.phase == "outside" else
                           "inside" if r.phase == "placed" else "pending",
                           r.screen_x, r.screen_y,
                           {"entity_type": r.entity_type, "health": r.health,
                            "source": list(r.source), "vault": list(r.vault),
                            "revision": r.revision})

    def objects(self):
        return tuple(self._state(r) for r in self.engine.snapshot())

    def take(self, tag, entity_type="minecraft:zombie"):
        return self._state(self.engine.take(tag, entity_type))

    def put(self, object_id, destination):
        return self._state(self.engine.put(object_id, destination))

    def move(self, object_id, x, y):
        return self._state(self.engine.move_desktop(object_id, x, y))

    def recover(self):
        return self.engine.recover()
