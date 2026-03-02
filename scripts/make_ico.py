"""
make_ico.py — Generate a production-quality favicon.ico from build/logo.png

Steps
-----
1. Load the source PNG (expected 1024×1024, any mode)
2. Convert to RGBA so we have a proper alpha channel
3. Draw a rounded-rectangle mask at full resolution — this gives smooth edges
   before we downsample, avoiding jagged corners at small sizes
4. Resize to each required icon size using high-quality Lanczos resampling
5. Save all six images into a single .ico container

Output: build/icons/favicon.ico
        build/icons/icon_<size>.png  (debug previews)
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT   = Path(__file__).resolve().parent.parent
SRC    = ROOT / "build" / "logo.png"
OUT_DIR = ROOT / "build" / "icons"
ICO_OUT = OUT_DIR / "favicon.ico"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Sizes required by the spec ─────────────────────────────────────────────────
SIZES = [256, 128, 64, 48, 32, 16]

# ── Corner radius — expressed as a fraction of the icon size ──────────────────
# 0.22 ≈ iOS-style "squircle" feel.  Tweak freely (0.0 = square, 0.5 = circle).
RADIUS_FRACTION = 0.22


# ─────────────────────────────────────────────────────────────────────────────
def make_rounded_mask(size: int, radius_fraction: float = RADIUS_FRACTION) -> Image.Image:
    """
    Return a square RGBA image that is white/opaque inside the rounded rect
    and fully transparent outside.  Works at any scale.
    """
    r = int(size * radius_fraction)          # corner radius in pixels

    # Work at 4× for antialiasing, then shrink
    scale = 4
    big   = size * scale
    big_r = r * scale

    mask_big = Image.new("L", (big, big), 0)   # L = 8-bit greyscale (used as alpha)
    draw = ImageDraw.Draw(mask_big)

    # rounded_rectangle is available in Pillow ≥ 8.2
    draw.rounded_rectangle([(0, 0), (big - 1, big - 1)], radius=big_r, fill=255)

    # Downsample with antialiasing
    mask = mask_big.resize((size, size), Image.LANCZOS)
    return mask


def apply_mask(img_rgba: Image.Image, mask: Image.Image) -> Image.Image:
    """Replace the alpha channel of img_rgba with mask."""
    r, g, b, _ = img_rgba.split()
    return Image.merge("RGBA", (r, g, b, mask))


def resize_with_quality(img: Image.Image, size: int) -> Image.Image:
    """
    Resize img to size×size.
    • Large → small: use LANCZOS (best downsampling quality)
    • Tiny sizes (≤ 32): sharpen slightly so detail isn't lost
    """
    from PIL import ImageFilter

    out = img.resize((size, size), Image.LANCZOS)

    # Very small icons benefit from a gentle unsharp mask
    if size <= 32:
        # Apply only to the RGB channels, not the alpha
        rgb  = out.convert("RGB")
        sharpened = rgb.filter(ImageFilter.UnsharpMask(radius=0.6, percent=120, threshold=2))
        sharpened = sharpened.convert("RGBA")
        # Restore alpha from the resized image
        _, _, _, a = out.split()
        r2, g2, b2, _ = sharpened.split()
        out = Image.merge("RGBA", (r2, g2, b2, a))

    return out


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    # 1. Load source
    print(f"Loading  : {SRC}")
    src = Image.open(SRC).convert("RGBA")
    print(f"Source   : {src.size[0]}×{src.size[1]}  mode={src.mode}")

    # 2. Apply rounded-rectangle mask at full source resolution
    src_size   = src.size[0]                          # assume square
    src_mask   = make_rounded_mask(src_size, RADIUS_FRACTION)
    src_masked = apply_mask(src, src_mask)

    # 3. Build one icon image per required size
    icon_images: list[Image.Image] = []

    for size in SIZES:
        icon = resize_with_quality(src_masked, size)

        # Save a PNG preview for visual inspection
        preview_path = OUT_DIR / f"icon_{size}.png"
        icon.save(preview_path, "PNG", optimize=True)
        print(f"  Wrote preview : {preview_path.name}  ({size}×{size})")

        icon_images.append(icon)

    # 4. Write the .ico file
    # Pillow's ICO encoder needs the images sorted largest→smallest
    # and wants a list of (w, h) tuples in `sizes` kwarg.
    ico_sizes = [(s, s) for s in SIZES]

    icon_images[0].save(
        ICO_OUT,
        format   = "ICO",
        sizes    = ico_sizes,
        append_images = icon_images[1:],
    )

    ico_bytes = ICO_OUT.stat().st_size
    print(f"\n✅  favicon.ico written → {ICO_OUT}")
    print(f"   File size : {ico_bytes:,} bytes")
    print(f"   Embedded  : {', '.join(str(s)+'×'+str(s) for s in SIZES)}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
