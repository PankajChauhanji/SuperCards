"""Shared card artwork primitives, used by BOTH deck generators.

One definition of a suit, imported by generate_cards.py (the clean deck) and
generate_cards_v2.py (the colourful deluxe deck). The previous versions each
carried their own hand-tuned bezier suits, and v2's were wrong in ways that are
easy to get wrong twice:

* its club had no top lobe — the path traced upper-left, lower-left, lower-right,
  upper-right, so it read as a butterfly;
* its spade and club stems were self-intersecting, which under `nonzero` fill
  produced an anvil-shaped pedestal with a notch bitten out of the blade.

Both classes of bug are prevented structurally here: club lobes are literal
circles, and every stem is one simple closed shape.

Suits are GEOMETRY, never text. Drawing them as Unicode glyphs (`<text>♠</text>`)
makes the shape come from the viewer's operating system — missing fonts render
tofu boxes, and several mobile browsers substitute the colour emoji face.
"""

# Suit outlines, centred on the origin, spanning roughly +/-21 units.
HEART = ("M0 18 C-3 13 -18 4 -19 -6 C-20 -15 -13 -20 -6.5 -20 "
         "C-2.5 -20 -0.8 -17.5 0 -14.5 C0.8 -17.5 2.5 -20 6.5 -20 "
         "C13 -20 20 -15 19 -6 C18 4 3 13 0 18 Z")
DIAMOND = "M0 -21 L15 0 L0 21 L-15 0 Z"
SPADE = ("M0 -21 C-2 -14 -17 -5 -19 4 C-21 12 -15 18 -9 18 "
         "C-4.5 18 -1.5 15 0 11 C1.5 15 4.5 18 9 18 "
         "C15 18 21 12 19 4 C17 -5 2 -14 0 -21 Z")
SPADE_FOOT = "M-7 21 C-3.2 18 -1.6 13.5 -1 9 L1 9 C1.6 13.5 3.2 18 7 21 Z"
CLUB_FOOT = "M-7 21 C-3.2 18 -1.6 13 -1 6 L1 6 C1.6 13 3.2 18 7 21 Z"

# One unit of suit artwork is 42 units tall, so `size` reads as pixels.
SUIT_UNITS = 42.0

# Card geometry shared by both decks, so a card from either is interchangeable.
W, H = 180, 252


def suit(code, x, y, size, color):
    """One suit symbol as standalone SVG geometry, centred on (x, y)."""
    k = size / SUIT_UNITS
    parts = [f'<g transform="translate({x:.2f} {y:.2f}) scale({k:.5f})" fill="{color}">']
    if code == "H":
        parts.append(f'<path d="{HEART}"/>')
    elif code == "D":
        parts.append(f'<path d="{DIAMOND}"/>')
    elif code == "S":
        parts.append(f'<path d="{SPADE}"/><path d="{SPADE_FOOT}"/>')
    elif code == "C":
        # Three real circles: a club cannot end up with the wrong lobes.
        parts.append('<circle cx="0" cy="-11" r="8.6"/>'
                     '<circle cx="-10.6" cy="3" r="8.6"/>'
                     '<circle cx="10.6" cy="3" r="8.6"/>'
                     f'<path d="{CLUB_FOOT}"/>')
    else:
        raise ValueError(f"unknown suit {code!r}")
    parts.append("</g>")
    return "".join(parts)


def svg(body, w=W, h=H):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}">\n' + body + "\n</svg>\n")


def contact_sheet(deck, path, ranks, cell_px=62, cols=13, bg=(18, 60, 47)):
    """Render a whole deck into one PNG so a change can be judged by eye.

    Deliberately defaults to 62px cells — the largest a card is ever drawn in
    this app — so decks are reviewed at the size they actually ship at.
    """
    import io
    import cairosvg
    from PIL import Image

    order = [f"{r}{s}.svg" for s in ("S", "H", "D", "C") for r in ranks]
    order = [n for n in order if n in deck] + (["back.svg"] if "back.svg" in deck else [])
    cw = int(cell_px)
    ch = int(cw * H / W)
    pad = 6
    rows = (len(order) + cols - 1) // cols
    img = Image.new("RGBA", (cols * (cw + pad) + pad, rows * (ch + pad) + pad), bg + (255,))
    for i, name in enumerate(order):
        png = cairosvg.svg2png(bytestring=deck[name].encode(),
                               output_width=cw, output_height=ch)
        tile = Image.open(io.BytesIO(png)).convert("RGBA")
        img.paste(tile, (pad + (i % cols) * (cw + pad), pad + (i // cols) * (ch + pad)), tile)
    img.save(path)
    return path, img.size
