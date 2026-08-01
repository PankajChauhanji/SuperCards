#!/usr/bin/env python3
"""Generate PWA PNG icons from the SVG sources.

Usage:
    pip install cairosvg Pillow
    python3 tools/generate_pwa_icons.py

Produces:
    static/icons/icon-192.png
    static/icons/icon-512.png
"""

import os
import sys

try:
    import cairosvg
    from PIL import Image
    import io
except ImportError:
    print(
        "Missing dependencies. Install them with:\n"
        "  pip install cairosvg Pillow\n"
        "Then re-run this script.",
        file=sys.stderr,
    )
    sys.exit(1)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS_DIR = os.path.join(ROOT, "static", "icons")

SOURCES = {
    "icon": os.path.join(ICONS_DIR, "icon.svg"),
    "maskable": os.path.join(ICONS_DIR, "icon.svg"),
}

TARGETS = [
    # (source_key, filename, size)
    ("icon", "icon-192.png", 192),
    ("icon", "icon-512.png", 512),
    # ("maskable", "icon-192.png", 192),
    # ("maskable", "", 512),
    # ("icon", "icon-192.png", 180),
]


def svg_to_png(svg_path: str, size: int) -> bytes:
    """Render an SVG to a square PNG at the given pixel size."""
    png_bytes = cairosvg.svg2png(
        url=svg_path, output_width=size, output_height=size
    )
    # Re-encode through Pillow to ensure optimal compression.
    img = Image.open(io.BytesIO(png_bytes))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main():
    os.makedirs(ICONS_DIR, exist_ok=True)

    for source_key, filename, size in TARGETS:
        svg_path = SOURCES[source_key]
        if not os.path.isfile(svg_path):
            print(f"  ⚠  SVG source missing: {svg_path}", file=sys.stderr)
            continue

        out_path = os.path.join(ICONS_DIR, filename)
        data = svg_to_png(svg_path, size)
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"  ✓  {filename} ({size}×{size}, {len(data):,} bytes)")

    print("\nDone. Icons saved to static/icons/")


if __name__ == "__main__":
    main()
