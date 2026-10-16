"""Reduce only recorded and independently verified X11 desktop proof media."""
from __future__ import annotations

from pathlib import Path
from PIL import Image


def publish(source: Path, target: Path) -> list[Path]:
    shots = {
        "minecraft-blocks-on-wikipedia.png": "minecraft-anywhere-wikipedia.png",
        "minecraft-blocks-on-example-com.png": "minecraft-anywhere-example-com.png",
    }
    for path in [*shots, "real-game-desktop-build.gif",
                 "external-website.log", "second-website.log", "mouse-input.log"]:
        if not (source / path).is_file():
            raise FileNotFoundError(f"Missing actual X11 proof artifact: {path}")
    wiki = (source / "external-website.log").read_text(encoding="utf-8")
    example = (source / "second-website.log").read_text(encoding="utf-8")
    driver = (source / "mouse-input.log").read_text(encoding="utf-8")
    if ("en.wikipedia.org/wiki/Art" not in wiki
            or '"injectedOverlayNodes": 0' not in wiki
            or "example.com/" not in example
            or '"injectedOverlayNodes": 0' not in example
            or "NATIVE_DESKTOP_WORLD_VERIFIED=" not in driver):
        raise ValueError("Not a verified cross-website X11 Minecraft build")
    original = Image.open(source / "real-game-desktop-build.gif")
    if original.n_frames < 16:
        raise ValueError("The real desktop GIF contains too few frames")
    target.mkdir(parents=True, exist_ok=True)
    output = []
    for before, after in shots.items():
        image = Image.open(source / before)
        if image.size != (1600, 900):
            raise ValueError("Unexpected desktop screenshot dimensions")
        path = target / after
        image.save(path)
        output.append(path)
    frames = []
    for idx in range(original.n_frames):
        if idx % 2:
            continue
        original.seek(idx)
        frame = original.convert("RGB").resize((960, 540), Image.Resampling.LANCZOS)
        frames.append(frame.quantize(colors=64, method=Image.Quantize.FASTOCTREE))
    gif = target / "minecraft-anywhere-x11.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:],
                   duration=440, loop=0, optimize=True, disposal=2)
    output.append(gif)
    print("PUBLISHED_VERIFIED_DESKTOP_PROOF=" + ",".join(map(str, output)))
    return output


if __name__ == "__main__":
    publish(Path("artifacts/desktop-world"), Path("docs/media"))
