"""
Draws the app icons (a solar panel under a sun, on the Dehlsen blue) into quotations/static/quotations/icons/.
Replace the PNG files there with your own logo if you prefer - keep the same names and sizes:
    icon-192.png (192x192)   icon-512.png (512x512)   icon-maskable-512.png (512x512, the picture inside the middle 60%)
    apple-touch-icon.png (180x180, no transparency)   favicon-32.png (32x32)
Run:  python tools/make_icons.py     (needs Pillow)
"""
import pathlib
from PIL import Image, ImageDraw

BLUE, GOLD, WHITE = (59, 115, 185), (212, 160, 60), (255, 255, 255)
OUT = pathlib.Path(__file__).resolve().parents[1] / "quotations" / "static" / "quotations" / "icons"
SS = 4                                              # draw 4x bigger, then shrink: smooth edges


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def glyph(draw, size, box):
    """The picture, scaled into box = (left, top, width) of a square area."""
    left, top, w = box
    P = lambda x, y: (left + x * w, top + y * w)
    # sun
    cx, cy = P(0.70, 0.27)
    import math
    for k in range(8):
        a = math.radians(k * 45)
        draw.line([(cx + math.cos(a) * 0.125 * w, cy + math.sin(a) * 0.125 * w), (cx + math.cos(a) * 0.185 * w, cy + math.sin(a) * 0.185 * w)], fill=GOLD, width=max(2, int(0.035 * w)))
    r = 0.085 * w
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GOLD)
    # panel: a slanted quadrilateral cut into 3 x 3 cells
    TL, TR, BR, BL = P(0.34, 0.47), P(0.86, 0.47), P(0.74, 0.76), P(0.16, 0.76)
    gap = 0.045
    for i in range(3):
        for j in range(3):
            def pt(u, v):
                top, bottom = lerp(TL, TR, u), lerp(BL, BR, u)
                return lerp(top, bottom, v)
            u0, u1, v0, v1 = i / 3 + gap / 2, (i + 1) / 3 - gap / 2, j / 3 + gap, (j + 1) / 3 - gap
            draw.polygon([pt(u0, v0), pt(u1, v0), pt(u1, v1), pt(u0, v1)], fill=WHITE)
    # stand
    draw.line([P(0.45, 0.78), P(0.45, 0.88)], fill=WHITE, width=max(2, int(0.04 * w)))
    draw.line([P(0.34, 0.885), P(0.56, 0.885)], fill=WHITE, width=max(2, int(0.04 * w)))


def make(size, name, rounded=False, content=1.0, transparent_corners=False):
    big = size * SS
    mode = "RGBA"
    img = Image.new(mode, (big, big), (0, 0, 0, 0) if transparent_corners else BLUE + (255,))
    d = ImageDraw.Draw(img)
    if transparent_corners:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * 0.22), fill=BLUE + (255,))
    side = big * content
    glyph(d, big, ((big - side) / 2, (big - side) / 2 + side * 0.02, side))
    img = img.resize((size, size), Image.LANCZOS)
    if not transparent_corners:
        img = img.convert("RGB")
    img.save(OUT / name, optimize=True)
    print("wrote", name, img.size, img.mode)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make(192, "icon-192.png", transparent_corners=True, content=0.92)
    make(512, "icon-512.png", transparent_corners=True, content=0.92)
    make(512, "icon-maskable-512.png", content=0.62)                 # full-bleed; the picture stays inside the safe middle area
    make(180, "apple-touch-icon.png", content=0.80)
    make(32, "favicon-32.png", transparent_corners=True, content=1.0)
