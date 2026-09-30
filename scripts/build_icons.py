"""Generate transparent PNG + multi-size ICO from source whale artwork."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "fishmate" / "resources" / "icons" / "whale_source.png"
OUT_DIR = ROOT / "fishmate" / "resources" / "icons"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def remove_outer_white(rgba: Image.Image, thresh: int = 28) -> Image.Image:
    """Flood-fill white background from corners; keep inner white (belly/eye)."""
    img = rgba.convert("RGBA")
    w, h = img.size
    px = img.load()
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    for x, y in seeds:
        r, g, b, a = px[x, y]
        if a == 0:
            continue
        if r > 235 and g > 235 and b > 235:
            ImageDraw.floodfill(img, (x, y), (0, 0, 0, 0), thresh=thresh)
    return img


def trim_transparent(img: Image.Image, pad: int = 8) -> Image.Image:
    bbox = img.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(img.width, right + pad)
    bottom = min(img.height, bottom + pad)
    return img.crop((left, top, right, bottom))


def square_canvas(img: Image.Image, size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    scale = min(size / img.width, size / img.height) * 0.88
    nw = max(1, int(img.width * scale))
    nh = max(1, int(img.height * scale))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    canvas.paste(resized, (ox, oy), resized)
    return canvas


def main() -> int:
    src_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    if not src_arg.is_file():
        print(f"Source not found: {src_arg}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = Image.open(src_arg)
    transparent = remove_outer_white(raw)
    transparent = trim_transparent(transparent, pad=12)
    master = square_canvas(transparent, 512)
    master.save(OUT_DIR / "app.png", optimize=True)

    frames: list[Image.Image] = []
    for s in SIZES:
        frame = square_canvas(transparent, s)
        frame.save(OUT_DIR / f"app_{s}.png")
        frames.append(frame)

    frames[-1].save(
        OUT_DIR / "app.ico",
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[:-1],
    )
    print(f"Wrote {OUT_DIR / 'app.ico'} and PNG sizes {SIZES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
