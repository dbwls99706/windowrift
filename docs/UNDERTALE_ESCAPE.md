# UNDERTALE: character outside the game window (experimental)

Toby Fox publishes an official old Windows/Mac demo of **UNDERTALE** at
<https://undertale.com/demo/>. We do **not** bundle that demo or its sprites.

The WindowRift control panel can capture a user-selected character from the
*visible* game window and place it on the desktop as a keyboard-controlled
visual actor (`Take control`). This works only to the extent that foreground
extraction succeeds and the game remains visible. The running game's character
is **not removed** and its health, inventory and NPC state are **not linked**.

The demo's Windows executable requires a compatible Windows installation or
Wine for Linux; no full original UNDERTALE build or successful execution of
this particular demo has been verified by this repository yet.

Once a legally obtained copy is running, launch `windowrift`, select the game
window, crop around the visible pixel-art character, choose Pixel art / flat
background or GrabCut, then click Capture and Take Control. The actor can jump
and interact with desktop ledges according to WindowRift's own collision model.

**Do not** describe a cropped moving sprite as the actual game engine's
character escaping. That requires a game-specific mod/plugin and separately
verified state transfer, not screen capture alone.
