# State-backed portals: application adapter contract

**Scope:** this is an opt-in extensibility system, not an ability to extract the
native state of arbitrary proprietary executables without their cooperation.
REA-style discoverability is a goal. Every app needs an authorized native-state
API, mod, plugin, or independently verified reverse-engineering adapter.

## Supported adapters

| Adapter | Game-owned state | Native identity | Original object removed | Return | Current restriction |
| --- | --- | --- | --- | --- | --- |
| `minecraft-java:block` | Yes, through `/clone` | No native block UUID | Yes | Yes | Selected whitelist blocks, owned 1.21.1 vanilla RCON server |
| `minecraft-java:mob` | Yes, same living entity | **Yes: Minecraft UUID** | Same mob is moved out of visible map into stasis | Yes | Specifically tagged safe mobs, owned 1.21.1 vanilla RCON server |
| `local-http` | App-implemented | App-implemented | App-implemented | App-implemented | Requires active, trusted app integration |
| Other arbitrary apps | **Not supported** | Unverified | No | No | Image extraction is visual-only and not a native portal |

A Minecraft mob is **not physically running its AI off-process** while outside:
the Minecraft server holds the same mob UUID and state in a force-loaded vault,
with its AI frozen; a separately rendered native desktop avatar can be dragged.
Its state continues when it is returned. Claims and screenshots must distinguish
this approximation from an actual seamless game-engine rendering escape.

## Native Python adapter

Implement `windowrift.portal_api.ApplicationAdapter`:

- `capability`: `Capability` declaring `native_state`,
  `native_identity`, `remove_from_source`, `return_to_source`,
  available `kinds` and `interaction`.
- `objects()`: `ObjectState` with stable WindowRift ID and, where supported,
  the real application's native ID.
- `take(...)`: remove the object from its visible source, preserving game state.
- `put(object_id, destination)`: return the same object.
- `move(object_id, x, y)`: update independent desktop coordinate.
- `recover()`: safely resume interrupted transfers.

`AdapterRegistry.register_entrypoint(name)` explicitly imports a separately
installed Python adapter from the `windowrift.adapters` entry point group.
**Installing or loading unknown plugins executes code**; opt in to trusted ones.
No silent injection, proprietary code patching or anti-cheat bypass is performed.

## Local HTTP v1: enable support for another app

The other app implements an authenticated HTTP server bound ONLY to loopback.
The WindowRift client uses `WINDOWRIFT_APP_TOKEN` (16+ characters) as header
`X-WindowRift-Token`, never follows redirects, and ignores HTTP proxies.

- `GET /windowrift/v1/capabilities` returns `Capability` JSON.
- `GET /windowrift/v1/objects` returns `ObjectState[]`.
- `POST /windowrift/v1/take` takes `{"object_id":"original-app-id"}`.
- `POST /windowrift/v1/put` takes `{"object_id":"...","destination":{...}}`.
- `POST /windowrift/v1/move` takes `{"object_id":"...","screen_x":800,"screen_y":300}`.
- `POST /windowrift/v1/recover` takes `{}`, returns a list of recovered IDs.

The integration is rejected unless the app truthfully declares reversible
native-state mutation and identity. The app's own server performs and verifies
its domain-specific mutation and recovery. WindowRift is not a universal
state inspector, nor can it independently verify malicious third-party claims.

```bash
windowrift-portal adapters
export WINDOWRIFT_APP_TOKEN='your-long-private-session-token'
windowrift-portal --app local-http --url http://127.0.0.1:8791 list
```

The tests spin up a **separate opt-in task app mock** with a native object ID
to exercise take/move/put and persistence of identity across operations. This
proves protocol interoperability, **not** support for every pre-existing app.

## Proof bar for a real game crossover

A persuasive game demo must show all four:
1. Original game CLIENT renders the object, and the game world removes it.
2. It appears outside the real original game window with the real object's ID
   and adequate visual fidelity and player control.
3. Another independent app/window can be affected.
4. The **same** native game object returns, with identity, relevant state, and
   recovery semantics actually checked by the engine.

**The current Minecraft server integration addresses the native-world side,
but still lacks step 1's graphical client footage and seamless in-game
drag-to-extract, and the desktop avatar is not a running game-engine entity.**
Do not advertise full crossover until those requirements have been fulfilled.
