from dataclasses import asdict
import pytest
from windowrift.portal_api import Capability, ObjectState, AdapterRegistry, PortalError
from windowrift.minecraft_adapters import MinecraftBlockAdapter, MinecraftMobAdapter


def test_capability_contract_truthful():
    b = MinecraftBlockAdapter.capability
    m = MinecraftMobAdapter.capability
    assert b.native_state and b.return_to_source and not b.native_identity
    assert m.native_state and m.native_identity and m.return_to_source
    assert "Minecraft" in m.restrictions or "minecraft" in m.app


def test_fail_closed_capability_claim():
    with pytest.raises(ValueError):
        Capability("bad", ("image",), False, False, True, True, True)


def test_invalid_object_positions_rejected():
    with pytest.raises(ValueError):
        ObjectState("app", "id", "thing", None, "outside", 40000, 0, {})
    with pytest.raises(ValueError):
        ObjectState("app", "id", "thing", None, "unknown", 0, 0, {})


def test_registry_supports_multiple_real_apps():
    class FakeAdapter:
        capability = Capability("sim:one", ("object",), True, True, True, True, True)
        def objects(self): return ()
        def take(self, *a, **k): raise NotImplementedError
        def put(self, *a): raise NotImplementedError
        def move(self, *a): raise NotImplementedError
        def recover(self): return []

    reg = AdapterRegistry()
    reg.register(FakeAdapter())
    assert reg.list_capabilities()[0].app == "sim:one"
    with pytest.raises(ValueError, match="Duplicate"):
        reg.register(FakeAdapter())
    with pytest.raises(PortalError):
        reg.adapter("not installed")


def test_registry_explicitly_rejects_uninstrumented_apps():
    with pytest.raises(TypeError):
        AdapterRegistry().register(object())


def test_snapshot_serialization_is_machine_readable():
    record = ObjectState("minecraft-java:mob", "id", "living-entity",
                         "d2f5bd2a-b67c-4828-93b4-53afa7690201",
                         "outside", 40, 60, {"health": 13.})
    assert asdict(record)["payload"]["health"] == 13.
