"""
make_ico.py — Generate all icon assets from build/logo.png

Outputs
-------
build/icons/favicon.ico          — browser favicon (all 6 sizes embedded)
build/icons/NNNxNNN.png          — electron-builder Linux icons (correct naming)
build/icon.ico                   — electron-builder Windows icon
build/icon.png                   — electron-builder macOS icon (512×512)
ui/icon.png                      — BrowserWindow taskbar icon in dev mode (512×512)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parent.parent
SRC     = ROOT / "build" / "icon.png"
OUT_DIR = ROOT / "build" / "icons"
ICO_OUT = OUT_DIR / "favicon.ico"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Sizes required by the spec ─────────────────────────────────────────────────
SIZES = [256, 128, 64, 48, 32, 16]

# ── Corner radius — expressed as a fraction of the icon size ──────────────────
RADIUS_FRACTION = 0.22


# ─────────────────────────────────────────────────────────────────────────────
def make_rounded_mask(size: int, radius_fraction: float = RADIUS_FRACTION) -> Image.Image:
    r     = int(size * radius_fraction)
    scale = 4
    big   = size * scale
    big_r = r * scale

    mask_big = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask_big)
    draw.rounded_rectangle([(0, 0), (big - 1, big - 1)], radius=big_r, fill=255)
    return mask_big.resize((size, size), Image.LANCZOS)


def apply_mask(img_rgba: Image.Image, mask: Image.Image) -> Image.Image:
    r, g, b, _ = img_rgba.split()
    return Image.merge("RGBA", (r, g, b, mask))


def resize_with_quality(img: Image.Image, size: int) -> Image.Image:
    out = img.resize((size, size), Image.LANCZOS)
    if size <= 32:
        rgb       = out.convert("RGB")
        sharpened = rgb.filter(ImageFilter.UnsharpMask(radius=0.6, percent=120, threshold=2))
        sharpened = sharpened.convert("RGBA")
        _, _, _, a = out.split()
        r2, g2, b2, _ = sharpened.split()
        out = Image.merge("RGBA", (r2, g2, b2, a))
    return out


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"Loading  : {SRC}")
    src = Image.open(SRC).convert("RGBA")
    print(f"Source   : {src.size[0]}×{src.size[1]}  mode={src.mode}")

    # Apply rounded-rectangle mask at full source resolution
    src_mask   = make_rounded_mask(src.size[0], RADIUS_FRACTION)
    src_masked = apply_mask(src, src_mask)

    # ── Build one icon image per required size ───────────────────────────────
    icon_images: list[Image.Image] = []

    for size in SIZES:
        icon = resize_with_quality(src_masked, size)

        # electron-builder Linux expects NNNxNNN.png  (e.g. 256x256.png)
        eb_path = OUT_DIR / f"{size}x{size}.png"
        icon.save(eb_path, "PNG", optimize=True)
        print(f"  Linux icon  : {eb_path.name}  ({size}×{size})")

        icon_images.append(icon)

    # ── favicon.ico (browser) ────────────────────────────────────────────────
    ico_sizes = [(s, s) for s in SIZES]
    icon_images[0].save(
        ICO_OUT,
        format        = "ICO",
        sizes         = ico_sizes,
        append_images = icon_images[1:],
    )
    print(f"\n  favicon.ico : {ICO_OUT}  ({ICO_OUT.stat().st_size:,} bytes)")

    # ── build/icon.ico  — Windows electron-builder icon ──────────────────────
    win_ico = ROOT / "build" / "icon.ico"
    shutil.copy2(ICO_OUT, win_ico)
    print(f"  Windows ico : {win_ico}")

    # ── 512×512 PNG for macOS and BrowserWindow (dev-mode taskbar) ───────────
    icon_512 = resize_with_quality(src_masked, 512)

    mac_icon = ROOT / "build" / "icon.png"
    icon_512.save(mac_icon, "PNG", optimize=True)
    print(f"  macOS  icon : {mac_icon}")

    ui_icon = ROOT / "ui" / "icon.png"
    icon_512.save(ui_icon, "PNG", optimize=True)
    print(f"  UI     icon : {ui_icon}  (BrowserWindow / dev taskbar)")

    # ── Copy favicon.ico to ui/ for the browser <link rel=icon> ─────────────
    shutil.copy2(ICO_OUT, ROOT / "ui" / "favicon.ico")
    print(f"  ui/favicon  : copied")

    print("\n✅  All icon assets generated successfully.")
    print(f"   Embedded ICO sizes : {', '.join(str(s)+'×'+str(s) for s in SIZES)}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
