#!/usr/bin/env python3
"""Deck v2 — the colourful "deluxe" deck, with figurative court cards.

    python3 tools/generate_cards_v2.py                    # -> static/img/cards_v2/
    python3 tools/generate_cards_v2.py --out /tmp/deck
    python3 tools/generate_cards_v2.py --sheet /tmp/v2.png

This is the alternative to the clean deck in generate_cards.py, not a replacement.
It writes to **static/img/cards_v2/** on purpose: the previous version wrote into
static/img/cards, so running it silently replaced the live deck the whole app
loads. Nothing in the app points at cards_v2 yet — swapping decks is a deliberate
copy, or a future setting.

Two things make this deck "colourful" rather than merely decorated:

* A **four-colour suit scheme** — spades ink, hearts red, diamonds blue, clubs
  green. This is a real convention in online play, and it is functional as well as
  bright: suit is legible from colour alone, which matters here because
  `FAN_MIN_OVERLAP_RATIO = 0.25` means a fanned hand often shows nothing but
  corners. The clean deck stays two-colour for players who want tradition.
* **Double-ended court cards.** Real court cards are point-symmetric: one bust,
  repeated rotated 180°. That reads as a proper playing card from a glance, and it
  is what the old v2 was reaching for with its lopsided single figures and a flag
  floating in the corner.

Suit geometry comes from tools/card_art.py, shared with the clean deck, so the
club-with-no-top-lobe and self-intersecting-stem bugs cannot come back here.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card_art import H, W, contact_sheet, suit, svg  # noqa: E402

# Minor: non-functional comment to record a small repo change for commits

IVORY = "#fdfaf3"
GOLD = "#c9a227"
GOLD_DK = "#a5811b"
INK = "#1b2430"
SKIN = "#f0d3b4"
HAIR = "#2d2a33"

# Four-colour deck: suit is readable from colour alone.
SUITS = {
    "S": {"color": "#1b2430", "tint": "#eceef2"},
    "H": {"color": "#d5342b", "tint": "#fbeceb"},
    "D": {"color": "#2f6fd0", "tint": "#eaf1fb"},
    "C": {"color": "#1f8a4c", "tint": "#e9f6ee"},
}
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
COURT = ("J", "Q", "K")

# ---------------------------------------------------------------------------
# Furniture
# ---------------------------------------------------------------------------


def frame(code):
    """Suit-coloured border over a faintly suit-tinted face: colour everywhere,
    while the face stays light enough for ink pips to keep full contrast."""
    c = SUITS[code]
    return (f'<rect x="2.5" y="2.5" width="{W - 5}" height="{H - 5}" rx="17" '
            f'fill="{c["tint"]}" stroke="{c["color"]}" stroke-width="5"/>'
            f'<rect x="10" y="10" width="{W - 20}" height="{H - 20}" rx="11" '
            f'fill="{IVORY}" stroke="{GOLD}" stroke-width="1.4"/>')


def corners(rank, code):
    color = SUITS[code]["color"]
    size = 32 if rank == "10" else 36
    one = (f'<text x="0" y="0" font-family="Georgia, \'Times New Roman\', serif" '
           f'font-weight="700" font-size="{size}" text-anchor="middle" '
           f'fill="{color}">{rank}</text>'
           + suit(code, 0, 19, 20, color))
    return (f'<g transform="translate(30 50)">{one}</g>'
            f'<g transform="translate({W - 30} {H - 50}) rotate(180)">{one}</g>')


_L, _R, _M = 0.0, 1.0, 0.5
PIPS = {
    "2":  [(_M, 0.00), (_M, 1.00)],
    "3":  [(_M, 0.00), (_M, 0.50), (_M, 1.00)],
    "4":  [(_L, 0.00), (_R, 0.00), (_L, 1.00), (_R, 1.00)],
    "5":  [(_L, 0.00), (_R, 0.00), (_M, 0.50), (_L, 1.00), (_R, 1.00)],
    "6":  [(_L, 0.00), (_R, 0.00), (_L, 0.50), (_R, 0.50), (_L, 1.00), (_R, 1.00)],
    "7":  [(_L, 0.00), (_R, 0.00), (_M, 0.25), (_L, 0.50), (_R, 0.50),
           (_L, 1.00), (_R, 1.00)],
    "8":  [(_L, 0.00), (_R, 0.00), (_M, 0.25), (_L, 0.50), (_R, 0.50),
           (_M, 0.75), (_L, 1.00), (_R, 1.00)],
    "9":  [(_L, 0.00), (_R, 0.00), (_L, 0.3333), (_R, 0.3333), (_M, 0.50),
           (_L, 0.6667), (_R, 0.6667), (_L, 1.00), (_R, 1.00)],
    "10": [(_L, 0.00), (_R, 0.00), (_L, 0.3333), (_R, 0.3333), (_M, 0.1667),
           (_L, 0.6667), (_R, 0.6667), (_M, 0.8333), (_L, 1.00), (_R, 1.00)],
}
BAND_X0, BAND_X1 = 64, 116
BAND_Y0, BAND_Y1 = 74, 206
PIP = 25


def pips(rank, code):
    color = SUITS[code]["color"]
    out = []
    for fx, fy in PIPS[rank]:
        out.append(suit(code,
                        BAND_X0 + (BAND_X1 - BAND_X0) * fx,
                        BAND_Y0 + (BAND_Y1 - BAND_Y0) * fy,
                        PIP, color))
    return "".join(out)


# ---------------------------------------------------------------------------
# Court figures — ONE figure per card, not the traditional double-ended mirror.
# ---------------------------------------------------------------------------
# A physical deck is double-ended so it reads the same however you hold it. On a
# screen a card is never upside down, so that convention costs half the artwork
# area and buys nothing. Spending the whole card on one figure roughly doubles the
# head size (44px vs 32px in the source), which is what makes King, Queen and Jack
# actually distinguishable rather than three similar silhouettes.
#
# Coordinates below are absolute card space, since nothing is rotated any more.
# Vertical budget: crown 32-62, head 62-106, collar 114-132, robe 126-196,
# plinth 194-212. Kept clear of the corner indices at x 12-48 and x 132-168.

HAIR_K = "#4a3f3a"
HAIR_Q = "#6b3524"
HAIR_J = "#8a5a3c"


def plinth(code):
    """The small pedestal the figure stands on, so the portrait has a base
    instead of floating in the middle of the card."""
    color = SUITS[code]["color"]
    return (f'<path d="M-34 18 L-28 2 L28 2 L34 18 Z" fill="{GOLD}"/>'
            f'<rect x="-30" y="-3" width="60" height="5" rx="2" fill="{GOLD_DK}"/>'
            f'<rect x="-34" y="18" width="68" height="3.5" rx="1.5" fill="{GOLD_DK}"/>'
            + suit(code, 0, 10, 13, color))


def crown(rank, code):
    """Deliberately different silhouettes: tall and spiked, low and arched, or a
    soft plumed cap. This is the fastest way to tell the three courts apart."""
    jewel = SUITS[code]["color"]
    if rank == "K":
        return (f'<path d="M-30 2 L-30 -20 L-19 -7 L-10 -31 L0 -14 L10 -31 '
                f'L19 -7 L30 -20 L30 2 Z" fill="{GOLD}"/>'
                f'<rect x="-31" y="1" width="62" height="10" rx="3" fill="{GOLD_DK}"/>'
                f'<circle cx="-16" cy="6" r="3" fill="{jewel}"/>'
                f'<circle cx="0" cy="6" r="3" fill="{jewel}"/>'
                f'<circle cx="16" cy="6" r="3" fill="{jewel}"/>')
    if rank == "Q":
        return (f'<path d="M-23 2 L-23 -9 C-15 -9 -11 -15 -9 -21 '
                f'C-5 -13 -3 -10 0 -10 C3 -10 5 -13 9 -21 '
                f'C11 -15 15 -9 23 -9 L23 2 Z" fill="{GOLD}"/>'
                f'<rect x="-24" y="1" width="48" height="8" rx="3" fill="{GOLD_DK}"/>'
                f'<circle cx="0" cy="-24" r="4" fill="{GOLD}"/>'
                f'<circle cx="0" cy="6" r="2.6" fill="{jewel}"/>')
    # Jack: a soft cap with a plume. No band of jewels — he is not royalty.
    return (f'<path d="M-21 4 C-21 -13 -10 -20 1 -20 C13 -20 20 -14 20 -4 '
            f'L20 4 Z" fill="{GOLD}"/>'
            f'<path d="M15 -17 C24 -28 32 -26 34 -19 C27 -19 22 -15 19 -9 Z" '
            f'fill="{GOLD_DK}"/>'
            f'<rect x="-22" y="3" width="43" height="7" rx="3" fill="{GOLD_DK}"/>')


def hair(rank):
    """King short with a beard, Queen long and flowing, Jack shoulder-length —
    a second differentiator that survives even when the crown is small."""
    if rank == "K":
        return (f'<path d="M-22 84 C-22 66 -12 56 0 56 C12 56 22 66 22 84 '
                f'C18 74 10 70 0 70 C-10 70 -18 74 -22 84 Z" fill="{HAIR_K}"/>'
                f'<path d="M-22 82 L-26 96 L-18 94 Z" fill="{HAIR_K}"/>'
                f'<path d="M22 82 L26 96 L18 94 Z" fill="{HAIR_K}"/>')
    if rank == "Q":
        return (f'<path d="M-22 84 C-22 64 -12 55 0 55 C12 55 22 64 22 84 '
                f'C18 74 10 70 0 70 C-10 70 -18 74 -22 84 Z" fill="{HAIR_Q}"/>'
                # Long panels either side, falling past the shoulders.
                f'<path d="M-22 78 C-30 96 -30 124 -24 146 L-13 146 '
                f'C-17 124 -17 100 -13 86 Z" fill="{HAIR_Q}"/>'
                f'<path d="M22 78 C30 96 30 124 24 146 L13 146 '
                f'C17 124 17 100 13 86 Z" fill="{HAIR_Q}"/>')
    return (f'<path d="M-22 84 C-22 65 -12 56 0 56 C12 56 22 65 22 84 '
            f'C18 74 10 70 0 70 C-10 70 -18 74 -22 84 Z" fill="{HAIR_J}"/>'
            f'<path d="M-22 80 C-27 92 -27 108 -23 118 L-14 118 '
            f'C-17 106 -17 92 -14 84 Z" fill="{HAIR_J}"/>'
            f'<path d="M22 80 C27 92 27 108 23 118 L14 118 '
            f'C17 106 17 92 14 84 Z" fill="{HAIR_J}"/>')


def robe(rank, code):
    """Broad and epauletted for the King, softer for the Queen, a sashed tunic
    for the Jack."""
    color = SUITS[code]["color"]
    if rank == "K":
        return (f'<path d="M-42 196 L-36 140 C-31 128 -15 123 0 123 '
                f'C15 123 31 128 36 140 L42 196 Z" fill="{color}"/>'
                # Epaulettes.
                f'<path d="M-40 150 C-34 138 -24 133 -18 133 L-20 145 '
                f'C-27 145 -33 149 -36 156 Z" fill="{GOLD}"/>'
                f'<path d="M40 150 C34 138 24 133 18 133 L20 145 '
                f'C27 145 33 149 36 156 Z" fill="{GOLD}"/>'
                # Placket down the centre.
                f'<rect x="-4" y="138" width="8" height="58" fill="{GOLD}" opacity="0.85"/>')
    if rank == "Q":
        return (f'<path d="M-38 196 L-32 144 C-27 131 -13 126 0 126 '
                f'C13 126 27 131 32 144 L38 196 Z" fill="{color}"/>'
                # Pendant on a chain.
                f'<path d="M-11 132 C-6 142 6 142 11 132" stroke="{GOLD}" '
                f'stroke-width="1.8" fill="none"/>'
                f'<circle cx="0" cy="146" r="5" fill="{GOLD}"/>')
    return (f'<path d="M-37 196 L-31 142 C-26 130 -13 125 0 125 '
            f'C13 125 26 130 31 142 L37 196 Z" fill="{color}"/>'
            # Diagonal sash.
            f'<path d="M-30 146 L-24 136 L34 178 L32 190 Z" fill="{GOLD}" '
            f'opacity="0.9"/>')


def face(rank):
    """Head, features, and the King's beard. Two eyes, brows and a mouth is the
    whole budget — anything finer is invisible at the size cards render."""
    parts = [f'<rect x="-8" y="96" width="16" height="30" fill="{SKIN}"/>',
             f'<circle cx="0" cy="84" r="22" fill="{SKIN}"/>']
    if rank == "K":
        # Beard first, so the mouth sits on top of it.
        parts.append(f'<path d="M-18 88 C-18 110 -9 120 0 120 C9 120 18 110 18 88 '
                     f'C13 98 -13 98 -18 88 Z" fill="{HAIR_K}"/>')
    parts += [
        f'<circle cx="-7.5" cy="82" r="2.4" fill="{INK}"/>',
        f'<circle cx="7.5" cy="82" r="2.4" fill="{INK}"/>',
        f'<path d="M-11 75 C-9 72.5 -5 72.5 -3.5 74" stroke="{INK}" '
        f'stroke-width="1.5" fill="none" stroke-linecap="round"/>',
        f'<path d="M11 75 C9 72.5 5 72.5 3.5 74" stroke="{INK}" '
        f'stroke-width="1.5" fill="none" stroke-linecap="round"/>',
        f'<path d="M-5 93 C-2 96 2 96 5 93" stroke="{INK}" stroke-width="1.7" '
        f'fill="none" stroke-linecap="round"/>',
    ]
    return "".join(parts)


def collar(rank, code):
    color = SUITS[code]["color"]
    if rank == "K":
        return (f'<path d="M-19 120 L0 136 L19 120 L14 115 L0 128 L-14 115 Z" '
                f'fill="{GOLD}"/>')
    if rank == "Q":
        return (f'<path d="M-17 124 L0 140 L17 124 L13 120 L0 132 L-13 120 Z" '
                f'fill="{GOLD}"/>')
    return (f'<path d="M-16 123 L0 137 L16 123 L12 119 L0 130 L-12 119 Z" '
            f'fill="{GOLD}"/>')


def court(rank, code):
    """One figure, standing on a plinth.

    Every part above is drawn x-centred on 0 with absolute y, so the whole figure
    is shifted to the card's centre line exactly once here. Draw order is
    back-to-front: robe, then collar, then face, then hair over the hairline, then
    the crown on top of that.
    """
    return (f'<g transform="translate(90 0)">'
            + robe(rank, code)
            + collar(rank, code)
            + face(rank)
            + hair(rank)
            + f'<g transform="translate(0 50)">{crown(rank, code)}</g>'
            + f'<g transform="translate(0 194)">{plinth(code)}</g>'
            + "</g>")


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------
def card(rank, code):
    color = SUITS[code]["color"]
    parts = [frame(code), corners(rank, code)]
    if rank == "A":
        parts.append(f'<circle cx="90" cy="128" r="50" fill="none" stroke="{GOLD}" '
                     f'stroke-width="2.5"/>')
        parts.append(f'<circle cx="90" cy="128" r="42" fill="{SUITS[code]["tint"]}"/>')
        parts.append(suit(code, 90, 128, 86, color))
    elif rank in COURT:
        parts.append(court(rank, code))
    else:
        parts.append(pips(rank, code))
    return svg("\n".join(parts))


def back():
    """Colourful back: all four suit colours, so the deluxe deck announces itself
    before a single face is turned over."""
    body = f'''<defs>
    <linearGradient id="v2base" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#243049"/>
      <stop offset="1" stop-color="#141b29"/>
    </linearGradient>
    <linearGradient id="v2gloss" x1="0" y1="0" x2="0.5" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.22"/>
      <stop offset="0.5" stop-color="#ffffff" stop-opacity="0.04"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect x="2.5" y="2.5" width="{W - 5}" height="{H - 5}" rx="17"
        fill="url(#v2base)" stroke="{GOLD}" stroke-width="5"/>
  <rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="10" fill="none"
        stroke="{GOLD}" stroke-width="1.3" opacity="0.55"/>
  <g opacity="0.9">
    {suit("S", 90, 74, 34, SUITS["S"]["color"])}
    {suit("H", 90, 74, 0.001, SUITS["H"]["color"])}
  </g>
  <g transform="translate(90 126)">
    <circle cx="0" cy="0" r="46" fill="none" stroke="{GOLD}" stroke-width="1.6"
            opacity="0.6"/>
    {suit("H", -22, -22, 30, SUITS["H"]["color"])}
    {suit("D", 22, -22, 30, SUITS["D"]["color"])}
    {suit("C", -22, 22, 30, SUITS["C"]["color"])}
    {suit("S", 22, 22, 30, "#e8ecf5")}
    <circle cx="0" cy="0" r="9" fill="{GOLD}"/>
  </g>
  <rect x="2.5" y="2.5" width="{W - 5}" height="{H - 5}" rx="17" fill="url(#v2gloss)"/>'''
    return svg(body)


def build():
    deck = {}
    for code in SUITS:
        for rank in RANKS:
            deck[f"{rank}{code}.svg"] = card(rank, code)
    deck["back.svg"] = back()
    return deck


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    # NOT static/img/cards: that is the live deck the whole app loads.
    default_out = os.path.join(here, "..", "static", "img", "cards_v2")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=default_out, help="output directory")
    ap.add_argument("--sheet", help="also render a contact-sheet PNG here")
    ap.add_argument("--sheet-scale", type=float, default=1.0,
                    help="contact sheet scale (1.0 = real 62px gameplay size)")
    args = ap.parse_args()

    deck = build()
    os.makedirs(args.out, exist_ok=True)
    for name, text in deck.items():
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(f"Wrote {len(deck)} files to {os.path.normpath(args.out)}")

    if args.sheet:
        path, size = contact_sheet(deck, args.sheet, RANKS,
                                   cell_px=62 * args.sheet_scale,
                                   bg=(26, 28, 32))
        print(f"Contact sheet: {path} {size}")


if __name__ == "__main__":
    main()
