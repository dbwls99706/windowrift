# Minecraft Java 1.21.1: one real mob UUID outside the visible world

This implementation is for an **operator-owned, backed-up, private** vanilla
Minecraft 1.21.1 dedicated server with RCON restricted by a local firewall.
It is not a Universal Minecraft mod, cannot access arbitrary games and should
not be used on public/multiplayer worlds or with somebody else's creatures.

## What is really transferred?

The selected tagged mob **remains the same Minecraft entity with the same
native UUID and NBT state**. The server teleports it to a force-loaded
reserved vault at (10300, 300, 10300) and temporarily sets flags such as
`NoAI`, `NoGravity`, `Invulnerable`, and `Silent`. The mob disappears
from the playing map but is not killed, cloned, or re-summoned. Health and
other native data remain held by the real game server.

A draggable transparent Qt avatar is rendered separately using pixels from
the local official Minecraft client JAR when available. **This avatar is an
approximation: the original Minecraft renderer and AI do not run on the
desktop.** On return, the server moves the SAME mob UUID to the requested
safe in-world position, restores its original flags, and verifies identity.

## Run on a TEST world

Create a fresh 1.21.1 vanilla dedicated server, connect with your legitimate
Minecraft Java client, set a firewall to block any inbound RCON port, and
restrict it to your private machine. Don't use an important survival world.
The vault region must stay empty and unused.

From an authorized in-game Creative/admin session:

```mcfunction
/time set midnight
/summon minecraft:zombie ~ ~ ~ {Tags:["windowrift_demo"],PersistenceRequired:1b}
```

In your terminal:

```bash
python -m pip install -e .
export WINDOWRIFT_RCON_PASSWORD='YOUR_LOCAL_SECRET'
windowrift-portal adapters
windowrift-portal --app minecraft-java:mob take --tag windowrift_demo
windowrift-portal --app minecraft-java:mob list
windowrift-mob --game-jar "$HOME/.minecraft/versions/1.21.1/1.21.1.jar"
# Replace this with the WindowRift transfer ID printed by 'list':
windowrift-portal --app minecraft-java:mob put YOUR_WINDOWRIFT_ID --at 20,70,20
windowrift-portal --app minecraft-java:mob recover
```

Only one explicitly tagged mob may match. Supported safe types:
zombie, skeleton, creeper, cow, pig and chicken. Players, bosses, passengers
and complex equipment integrations are not supported. Use a clear, solid
floor under any return coordinate, and keep the two blocks occupied by the
mob empty. A persistent ledger stores intent and desktop position.
Interrupted handoffs can be recovered conservatively; a missing or changed
UUID is a **hard error**. A local scoreboard objective named `wr_mobs`
is used to measure the exact number of matching entities because Minecraft
1.21.1's RCON returns only `Test passed` for entity existence tests.

## What was actually verified?

`.github/workflows/real-mob.yml` runs an original Mojang-verified 1.21.1
headless server and checks same-UUID stasis, return, health and original AI
flags. The official client JAR is downloaded and checksum-verified solely
for authentic local texture extraction. The JAR and world are NOT committed.

Screenshots from the headless server's desktop control panel are **not
original Minecraft graphical-client screenshots**. A full real-gameplay
clip, seamless mouse drag from inside the running game, and real off-process
mob physics remain unsolved and must not be represented as implemented.
