#!/usr/bin/env python3
"""Regenerate assets/appicon.png (and .ico) for 3MF To AD5X.

    python3 assets/make_icon.py

Needs Pillow.  build_mac.sh turns the PNG into an .icns with macOS's own sips/iconutil, so this
script only has to produce the flat PNG.
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024                                   # macOS wants a 1024x1024 master
BG1 = (79, 70, 229)                        # indigo  - the app's LIGHT["accent"]
BG2 = (14, 165, 233)                       # sky     - the app's LIGHT["g2"]


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def squircle(draw, box, radius, fill):
    """macOS-ish rounded square: a plain rounded_rectangle reads close enough at every size."""
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def gradient(size, c1, c2):
    """Diagonal gradient, drawn on a small image and upscaled (fast and smooth)."""
    n = 256
    g = Image.new("RGB", (n, n))
    px = g.load()
    for y in range(n):
        for x in range(n):
            px[x, y] = lerp(c1, c2, (x + y) / (2 * n - 2))
    return g.resize((size, size), Image.BICUBIC)


def cube(draw, cx, cy, s, color, width):
    """An isometric open cube - the '3MF' half of the logo."""
    top = [(cx, cy - s), (cx + s, cy - s * 0.5), (cx, cy), (cx - s, cy - s * 0.5)]
    left = [(cx - s, cy - s * 0.5), (cx, cy), (cx, cy + s), (cx - s, cy + s * 0.5)]
    right = [(cx + s, cy - s * 0.5), (cx, cy), (cx, cy + s), (cx + s, cy + s * 0.5)]
    for poly in (top, left, right):
        draw.line(poly + [poly[0]], fill=color, width=width, joint="curve")
    draw.line([(cx - s, cy - s * 0.5), (cx + s, cy - s * 0.5)], fill=color, width=width)
    draw.line([(cx - s, cy - s * 0.5), (cx - s, cy + s * 0.5)], fill=color, width=width)
    draw.line([(cx + s, cy - s * 0.5), (cx + s, cy + s * 0.5)], fill=color, width=width)
    draw.line([(cx, cy), (cx, cy + s)], fill=color, width=width)


def arrow(draw, cx, cy, s, color, width):
    """Downward arrow - the 'convert to AD5X' half."""
    draw.line([(cx, cy - s), (cx, cy + s * 0.55)], fill=color, width=width)
    h = s * 0.62
    draw.line([(cx - h * 0.8, cy + s * 0.1), (cx, cy + s * 0.75), (cx + h * 0.8, cy + s * 0.1)],
              fill=color, width=width, joint="curve")


def main():
    img = gradient(S, BG1, BG2).convert("RGBA")

    # rounded-square mask so the badge is not a hard rectangle
    mask = Image.new("L", (S, S), 0)
    squircle(ImageDraw.Draw(mask), (0, 0, S - 1, S - 1), radius=int(S * 0.2237), fill=255)
    img.putalpha(mask)

    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    shadow = (255, 255, 255, 70)

    cube(d, S * 0.5, S * 0.40, S * 0.20, white, int(S * 0.026))
    d.line([(S * 0.24, S * 0.60), (S * 0.76, S * 0.60)], fill=shadow, width=int(S * 0.014))
    arrow(d, S * 0.5, S * 0.70, S * 0.085, white, int(S * 0.024))

    out = os.path.join(HERE, "appicon.png")
    img.save(out)
    print("wrote", out, img.size)

    ico = os.path.join(HERE, "appicon.ico")
    img.resize((256, 256), Image.LANCZOS).save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", ico)

    # GIF is the one image format Tk 8.5 can read, and macOS system Python still ships Tk 8.5.
    # Quantised to the two brand colours + white so the gradient survives the 256-colour limit.
    small = img.resize((256, 256), Image.LANCZOS)
    small.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT).save(os.path.join(HERE, "appicon.gif"))
    print("wrote", os.path.join(HERE, "appicon.gif"))


if __name__ == "__main__":
    main()
