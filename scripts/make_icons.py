#!/usr/bin/env python3
"""Рисует иконки PWA: золотой мяч и цифра 7, без чужих логотипов."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BG = (7, 8, 12)
GOLD = (232, 184, 74)
INK = (26, 20, 8)
FONT_CANDIDATES = [
    "/tmp/Oswald-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def curve(draw, cx, cy, radius, side, width):
    points = []
    steps = 36
    for index in range(steps + 1):
        t = -1 + 2 * index / steps
        y = cy + t * radius * 0.9
        x = cx + side * radius * (0.28 + 0.62 * (1 - t * t))
        points.append((x, y))
    draw.line(points, fill=INK, width=width, joint="curve")


def draw_icon(size, ball_ratio):
    image = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(image)
    radius = int(size * ball_ratio)
    cx = cy = size / 2
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=GOLD)
    width = max(2, radius // 22)
    draw.line((cx, cy - radius, cx, cy + radius), fill=INK, width=width)
    draw.line((cx - radius, cy, cx + radius, cy), fill=INK, width=width)
    curve(draw, cx, cy, radius, -1, width)
    curve(draw, cx, cy, radius, 1, width)
    face = font(int(radius * 0.92))
    draw.text((cx, cy + radius * 0.04), "7", font=face, fill=INK, anchor="mm")
    return image


def main():
    draw_icon(192, 0.44).save(ROOT / "icon-192.png", "PNG")
    draw_icon(512, 0.44).save(ROOT / "icon-512.png", "PNG")
    draw_icon(192, 0.31).save(ROOT / "icon-maskable-192.png", "PNG")
    draw_icon(512, 0.31).save(ROOT / "icon-maskable-512.png", "PNG")


if __name__ == "__main__":
    main()
