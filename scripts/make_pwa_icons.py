#!/usr/bin/env python3
"""Generate PWA icons from logo.png: emblem circle aligned to mask (radius 0.48 * size)."""

from __future__ import annotations

import base64
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "logo.png"
BG = (7, 8, 12)
# Outer black ring of circular emblem in logo.png (995×978), tuned to ring fit.
EMBLEM_CX = 511
EMBLEM_CY = 502
EMBLEM_R = 390
MASK_RADIUS_RATIO = 0.48
ARTIFACTS = Path("/opt/cursor/artifacts/screenshots")


def render_icon(size: int) -> Image.Image:
    logo = Image.open(LOGO).convert("RGBA")
    target_r = MASK_RADIUS_RATIO * size
    scale = target_r / EMBLEM_R
    scaled = logo.resize(
        (max(1, int(logo.width * scale)), max(1, int(logo.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), BG + (255,))
    paste_x = int(size / 2 - EMBLEM_CX * scale)
    paste_y = int(size / 2 - EMBLEM_CY * scale)
    canvas.alpha_composite(scaled, (paste_x, paste_y))
    return canvas.convert("RGB")


def write_png(path: Path, size: int) -> None:
    render_icon(size).save(path, format="PNG", optimize=True)


def write_favicon_svg(path: Path, size: int = 128) -> None:
    icon = render_icon(size)
    buf = io.BytesIO()
    icon.save(buf, format="PNG", optimize=True)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f'<image href="data:image/png;base64,{b64}" width="{size}" height="{size}"/></svg>\n',
        encoding="utf-8",
    )


def mask_preview(size: int = 512, out: Path | None = None) -> Path:
    """Circular mask preview (Android adaptive icon safe zone)."""
    icon = render_icon(size).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    masked = Image.new("RGBA", (size, size), BG + (255,))
    masked.paste(icon, (0, 0), mask)
    # Checkerboard outside mask for PR preview
    preview = Image.new("RGBA", (size, size))
    step = 16
    for y in range(0, size, step):
        for x in range(0, size, step):
            c = (90, 120, 180, 255) if ((x // step) + (y // step)) % 2 == 0 else (60, 90, 140, 255)
            for py in range(y, min(y + step, size)):
                for px in range(x, min(x + step, size)):
                    if mask.getpixel((px, py)) == 0:
                        preview.putpixel((px, py), c)
    preview.alpha_composite(masked)
    dest = out or (ARTIFACTS / "icon-maskable-v3-512-preview.png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    preview.save(dest, format="PNG", optimize=True)
    return dest


def main() -> None:
    outputs = {
        ROOT / "icon-v3-192.png": 192,
        ROOT / "icon-v3-512.png": 512,
        ROOT / "icon-maskable-v3-192.png": 192,
        ROOT / "icon-maskable-v3-512.png": 512,
        ROOT / "apple-touch-icon-v3-180.png": 180,
    }
    for path, px in outputs.items():
        write_png(path, px)
    write_favicon_svg(ROOT / "favicon.svg", 128)
    mask_preview(512)
    print("wrote", ", ".join(p.name for p in outputs), "favicon.svg")


if __name__ == "__main__":
    main()
