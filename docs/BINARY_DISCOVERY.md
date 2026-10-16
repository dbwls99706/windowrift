# Executable discovery: from assembly evidence to a verified game portal

WindowRift now distinguishes **binary reconnaissance** from **runtime game-object transport**. It accepts a PE executable, ELF binary or Java archive, emits an evidence report, and can include a bounded disassembly excerpt where `objdump` is installed. The input executable is never executed, patched or modified. A running Linux process may optionally be inspected through read-only `/proc/<pid>/maps` metadata.

```bash
pip install -e .
windowrift-inspect /path/to/game.exe --assembly --output local-report.json
windowrift-inspect /path/to/game.jar --output local-report.json
windowrift-inspect --pid 12345 --output process-report.json
```

A report includes a SHA-256 fingerprint, container format, architecture, sections, ELF dependencies and symbol names where retained, engine indications with their **evidence quality**, and the exact reason the result is **not yet an authenticated object portal**. A stripped executable may have zero meaningful object symbols; absence of names is not proof of absent objects. Disassembly is raw instructions, not recovered game state.

## Real supported workflow

1. **Discover:** read original executable metadata (PE/ELF/JAR), adjacent files, imported libraries and bounded assembly.
2. **Investigate:** use a separate analyzer such as REA/Ghidra and runtime debugger on an authorized local copy to discover actual native object identity, serialization, spawn/despawn methods and game-thread ownership. Findings must be supported by repeatable evidence.
3. **Validate:** create one game-engine-specific adapter exposing native state and object identity through WindowRift's existing `ApplicationAdapter` protocol. Add tests proving take/move/put/recovery and rejection of unsafe destinations.
4. **Render:** use real game assets with applicable rights, and preserve the object's **actual state** while it exists outside the visible game world. A static sprite or duplicated block is not sufficient.
5. **Prove:** run original game **graphical client** alongside desktop avatar, show original object removed, desktop interaction on an unrelated app, then **same native object restored**. Screenshots must be actual process captures, not simulations or images from a headless server masquerading as gameplay.

There is no truthful single pattern that can patch arbitrary games and expose live objects. The Windows/ELF executable typically contains machine code, while entity ownership and lifecycle exist in running processes, scripting VMs, engine data structures or remote game servers. File patching is sometimes possible but isn't a universal or safe primary mechanism. Packed, anti-cheat-protected, DRM-protected, and remote-authoritative games require explicit limits; this tool does not bypass protections.

The `binary discovery` CI job inspects the genuine packaged **Chocolate Doom** executable read-only, saves structured evidence, and confirms the executable SHA-256 did not change. This is **not** evidence that WindowRift already moves DOOM monsters as native objects.

## Game support levels

| State | Meaning |
| --- | --- |
| `binary inspected` | Executable format, symbols, static clues and optional assembly identified. No object moved. |
| `adapter verified` | Actual game-owned object take/restore validated with game API or authorized runtime integration. |
| `visual proof` | Original graphical game client and unrelated desktop/window captured; true native identity shown on take and return. |

**Current release:** binary discovery only produces the first level. Minecraft Java's existing block and mob adapters separately reach some of the second level on a dedicated server. A completely universal game adapter and graphical live-object crossover are **not implemented**.
