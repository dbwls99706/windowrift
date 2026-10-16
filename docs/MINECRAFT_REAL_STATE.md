# Minecraft Java Edition: real block-state transfer

WindowRift's original Minecraft Classic experiments work by sampling pixels.
**This new adapter instead mutates an actual vanilla Minecraft Java Edition
1.21.1 world.** It is experimental and deliberately limited.

## Prerequisites

You must own Minecraft Java Edition and control a local dedicated vanilla
server; RCON is **not** enabled for ordinary unmodified single-player worlds.
Connect your real client to the server, e.g. at localhost:25565.

In server.properties, for a server accessed only from your own computer:

```properties
server-ip=127.0.0.1
enable-rcon=true
rcon.port=25575
rcon.password=CHOOSE_A_LONG_PRIVATE_PASSWORD
```

RCON may listen on all interfaces even when server-ip is set to 127.0.0.1.\nUse a host firewall to block inbound RCON connections; never expose the port to\nthe Internet. Do not expose this test server to the Internet. Use a new Creative
flat world, not a valuable survival world. The adapter is limited to one
dimension per ledger and a whitelist of ordinary blocks. It **rejects block
entities, chests, signs, inventories, players, entities and modded blocks**.

Reserve the area around (10000,300,10000) in the Overworld as the **vault**.
The 32 consecutive block positions from that point are used as escrow; they
must start empty and must not be edited manually. The chunks may remain force
loaded. Back up both the Minecraft world **and** the WindowRift ledger.

## Actual world round trip

Install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

read -rs -p 'Local RCON password: ' WINDOWRIFT_RCON_PASSWORD; echo
export WINDOWRIFT_RCON_PASSWORD
windowrift-mc ping
```

In the actual Minecraft game/server console, create an east-facing stair:

```mcfunction
/setblock 10 70 10 minecraft:oak_stairs[facing=east,half=bottom]
```

Take it physically out of the active game world:

```bash
windowrift-mc take --at 10,70,10 --material minecraft:oak_stairs
windowrift-mc list
```

The game block disappears from its source coordinate. A reserved
force-loaded block cell retains its exact Minecraft block state including
its direction. A durable ledger stores the WindowRift identity. Vanilla Minecraft blocks do\nnot natively have UUIDs; this stable ID belongs to WindowRift's recorded\nblock transfer and does not mean Minecraft creates a new persistent entity.

Open the native desktop block representation and move it by dragging:

```bash
windowrift-real --game-jar "$HOME/.minecraft/versions/1.21.1/1.21.1.jar"
```

The jar argument is optional but enables original local game textures.
Without it the app explicitly labels its procedural color placeholder.
The renderer is a simplified isometric cube; stairs and glass are not faithfully
rendered Minecraft geometry. Neither texture mode is a screenshot cutout.

Return the **same** identity into the real Minecraft world:

```bash
windowrift-mc put YOUR_OBJECT_UUID --at 14,70,10
windowrift-mc pick YOUR_OBJECT_UUID
windowrift-mc put YOUR_OBJECT_UUID --at 18,70,12
```

The world position, stair direction, and vault contents are checked by real
Minecraft commands. The original object UUID remains the same across cycles.

## Crash handling

Each mutation is preceded by an atomic local journal intent. If the desktop
client crashes in the middle of a transfer, inspect the world state and run:

```bash
windowrift-mc recover
```

Recovery compares the source, destination and vault through Minecraft
commands and removes **only verified duplicates**. Conflicting cells halt
without overwriting world data. A filesystem journal and the game world do
not share a distributed atomic transaction; extreme power-loss or manual
interference still requires restoring backups.

## Verification and non-goals

[Real Minecraft server CI](../.github/workflows/real-minecraft.yml) fetches
the Mojang 1.21.1 server jar at test time, verifies SHA-1 and starts it in a
temporary local environment. Its proof requires the original stair to become
air and later reappear with identical facing, while the same UUID is preserved.
No Minecraft game code, jar, world file or textures are committed or uploaded.

This does **not** work with Minecraft Classic, arbitrary games, or vanilla
single-player without a suitable server. It also does not automatically
translate screen pixels into block state, read private process memory,
synchronize client animation or implement full physics across unrelated apps.
