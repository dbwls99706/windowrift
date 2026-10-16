"""Opt-in, state-backed object transport across application boundaries.

This protocol is intentionally not a process-injection or image-extraction API.
Applications must expose a trusted native-state adapter. A screenshot overlay
cannot truthfully advertise native identity or reversible state transitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Protocol, runtime_checkable


class PortalError(RuntimeError):
    pass


@dataclass(frozen=True)
class Capability:
    app: str
    kinds: tuple[str, ...]
    native_state: bool
    native_identity: bool
    remove_from_source: bool
    return_to_source: bool
    desktop_visual: bool
    interaction: tuple[str, ...] = ()
    restrictions: str = ""

    def __post_init__(self):
        if not self.app or not self.kinds:
            raise ValueError("An adapter must identify its app and supported objects")
        if self.return_to_source and not self.native_state:
            raise ValueError("Stateful return requires real native state access")


@dataclass(frozen=True)
class ObjectState:
    adapter: str
    object_id: str
    kind: str
    native_identity: str | None
    phase: str
    screen_x: int
    screen_y: int
    payload: dict[str, Any]

    def __post_init__(self):
        if not self.adapter or not self.object_id:
            raise ValueError("Missing object identity")
        if self.phase not in ("outside", "inside", "pending", "conflict"):
            raise ValueError("Unsupported object lifecycle phase")
        if any(type(v) is not int or abs(v) > 32768
               for v in (self.screen_x, self.screen_y)):
            raise ValueError("Invalid desktop position")


@runtime_checkable
class ApplicationAdapter(Protocol):
    @property
    def capability(self) -> Capability: ...

    def objects(self) -> tuple[ObjectState, ...]: ...
    def take(self, *args: Any, **kwargs: Any) -> ObjectState: ...
    def put(self, object_id: str, destination: Any) -> ObjectState: ...
    def move(self, object_id: str, x: int, y: int) -> ObjectState: ...
    def recover(self) -> list[str]: ...


class AdapterRegistry:
    """Do not silently load and execute third-party plugins."""
    def __init__(self):
        self._adapters: dict[str, ApplicationAdapter] = {}

    def register(self, adapter: ApplicationAdapter) -> None:
        if not isinstance(adapter, ApplicationAdapter):
            raise TypeError("Adapter does not implement WindowRift's state contract")
        name = adapter.capability.app
        if name in self._adapters:
            raise ValueError(f"Duplicate adapter: {name}")
        self._adapters[name] = adapter

    def register_entrypoint(self, selected_name: str, **kwargs: Any) -> ApplicationAdapter:
        """Explicitly load one operator-approved, locally installed adapter."""
        matches = [e for e in entry_points(group="windowrift.adapters")
                   if e.name == selected_name]
        if len(matches) != 1:
            raise PortalError(f"Missing or ambiguous installed adapter: {selected_name}")
        adapter = matches[0].load()(**kwargs)
        self.register(adapter)
        return adapter

    def list_capabilities(self) -> tuple[Capability, ...]:
        return tuple(x.capability for x in self._adapters.values())

    def adapter(self, name: str) -> ApplicationAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise PortalError(f"No native-state adapter for {name}") from exc
