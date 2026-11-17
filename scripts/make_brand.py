"""Draw the integration icon (own design, not the Kermi logo). Run from the repo root."""

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path("custom_components/kermi_xcenter/brand")
S = 1024  # draw large, downsample for smooth edges


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # heat waves above the unit
    for i, x in enumerate((330, 512, 694)):
        # a smooth stroke: many overlapping discs along a sine curve
        for t in range(0, 401):
            y = 250 - t * 0.475
            px = x + 28 * math.sin(t / 400 * 2 * math.pi + i)
            d.ellipse((px - 23, y - 23, px + 23, y + 23), fill=(242, 140, 40, 255))
    # outdoor unit body
    d.rounded_rectangle((90, 300, 934, 900), radius=90, fill=(31, 111, 178, 255))
    # fan ring
    cx, cy, r = 400, 600, 215
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(235, 242, 250, 255))
    d.ellipse((cx - r + 30, cy - r + 30, cx + r - 30, cy + r - 30), fill=(31, 111, 178, 255))
    # three fan blades
    for k in range(3):
        a = k * 2 * math.pi / 3
        blade = [
            (cx, cy),
            (cx + 160 * math.cos(a - 0.35), cy + 160 * math.sin(a - 0.35)),
            (cx + 175 * math.cos(a + 0.25), cy + 175 * math.sin(a + 0.25)),
        ]
        d.polygon(blade, fill=(235, 242, 250, 255))
    d.ellipse((cx - 38, cy - 38, cx + 38, cy + 38), fill=(235, 242, 250, 255))
    # grille lines on the right
    for y in range(440, 780, 70):
        d.rounded_rectangle((680, y, 860, y + 28), radius=14, fill=(235, 242, 250, 255))
    return img


if __name__ == "__main__":
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png", optimize=True)
    big.resize((512, 512), Image.LANCZOS).save(OUT / "icon@2x.png", optimize=True)
