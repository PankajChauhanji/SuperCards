#!/usr/bin/env python3
"""Generate the playing-card SVGs used by every game.

    python3 tools/generate_cards.py                 # writes static/img/cards/
    python3 tools/generate_cards.py --out /tmp/deck # writes somewhere else
    python3 tools/generate_cards.py --sheet a.png   # also render a contact sheet

Design brief, derived from how the cards are actually drawn rather than from
taste:

* The source is 180x252, but the LARGEST a card is ever rendered in this app is
  **62px wide** (the centre pile). Hand cards are 58px, 46px on phones, and the
  round-end reveal is 38px. So the real canvas is ~62px and any detail finer than
  about a third scale cannot be perceived. The previous v2 deck carried
  decoration at `stroke-width="0.6" opacity="0.06"`, which is invisible by
  construction.
* `FAN_MIN_OVERLAP_RATIO = 0.25` in core/seats.js means a fanned hand always
  overlaps by at least a quarter, usually far more — so the **corner index does
  nearly all the work**. It gets the space it deserves.
* Fourteen table themes sit behind these cards, from Casino green to Red Casino
  to Hacker's near-black. The face is therefore opaque cream: a translucent card
  would change identity with the theme, and rank/suit is the one thing in this
  game that must never be ambiguous.

Suits are GEOMETRY, never text. The previous version drew them as Unicode glyphs
("♠") in Georgia, which meant the shapes came from the viewer's operating system:
missing fonts render tofu boxes, and several mobile browsers substitute the
colour emoji face instead. Clubs here are three real circles and the spade/club
feet are simple closed shapes, so the lobe topology and the winding cannot be
wrong the way hand-tuned bezier stems were.

Ranks stay as <text>, which is safe: they are ASCII, so every fallback font has
them.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Minor: non-functional comment to record a small repo change for commits

from card_art import H, W, contact_sheet, suit, svg

CREAM = "#fbf7ec"
INK = "#16211d"
RED = "#c2352b"
GOLD = "#c9a227"
EDGE = "#ddd3ba"          # quiet edge for number cards
BACK_BASE = "#132320"

SUITS = {
    "S": INK,
    "H": RED,
    "D": RED,
    "C": INK,
}
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
COURT = ("J", "Q", "K")

# ---------------------------------------------------------------------------
# Card furniture
# ---------------------------------------------------------------------------
def frame(royal):
    """Opaque cream face. Aces and court cards earn the gold edge; the rest get
    a quiet warm one, so rank hierarchy is legible before you read anything."""
    stroke, width = (GOLD, 3) if royal else (EDGE, 2)
    return (f'<rect x="3" y="3" width="{W - 6}" height="{H - 6}" rx="16" '
            f'fill="{CREAM}" stroke="{stroke}" stroke-width="{width}"/>')


def corners(rank, code, color):
    """The element that actually gets seen. Ranks are text (ASCII, so any font
    works); the suit beneath is geometry."""
    size = 34 if rank == "10" else 38
    one = (f'<text x="0" y="0" font-family="Georgia, \'Times New Roman\', serif" '
           f'font-weight="700" font-size="{size}" text-anchor="middle" '
           f'fill="{color}">{rank}</text>'
           + suit(code, 0, 20, 21, color))
    return (f'<g transform="translate(27 47)">{one}</g>'
            f'<g transform="translate({W - 27} {H - 47}) rotate(180)">{one}</g>')


# Standard English pip layouts, as fractions of the pip band.
_COL_L, _COL_R, _MID = 0.0, 1.0, 0.5
PIPS = {
    "2":  [(_MID, 0.00), (_MID, 1.00)],
    "3":  [(_MID, 0.00), (_MID, 0.50), (_MID, 1.00)],
    "4":  [(_COL_L, 0.00), (_COL_R, 0.00), (_COL_L, 1.00), (_COL_R, 1.00)],
    "5":  [(_COL_L, 0.00), (_COL_R, 0.00), (_MID, 0.50),
           (_COL_L, 1.00), (_COL_R, 1.00)],
    "6":  [(_COL_L, 0.00), (_COL_R, 0.00), (_COL_L, 0.50), (_COL_R, 0.50),
           (_COL_L, 1.00), (_COL_R, 1.00)],
    "7":  [(_COL_L, 0.00), (_COL_R, 0.00), (_MID, 0.25), (_COL_L, 0.50),
           (_COL_R, 0.50), (_COL_L, 1.00), (_COL_R, 1.00)],
    "8":  [(_COL_L, 0.00), (_COL_R, 0.00), (_MID, 0.25), (_COL_L, 0.50),
           (_COL_R, 0.50), (_MID, 0.75), (_COL_L, 1.00), (_COL_R, 1.00)],
    "9":  [(_COL_L, 0.00), (_COL_R, 0.00), (_COL_L, 0.3333), (_COL_R, 0.3333),
           (_MID, 0.50), (_COL_L, 0.6667), (_COL_R, 0.6667),
           (_COL_L, 1.00), (_COL_R, 1.00)],
    "10": [(_COL_L, 0.00), (_COL_R, 0.00), (_COL_L, 0.3333), (_COL_R, 0.3333),
           (_MID, 0.1667), (_COL_L, 0.6667), (_COL_R, 0.6667),
           (_MID, 0.8333), (_COL_L, 1.00), (_COL_R, 1.00)],
}

# The pip band, and one pip size for the whole deck so spacing can never drift.
BAND_X0, BAND_X1 = 62, 118
BAND_Y0, BAND_Y1 = 73, 207
PIP = 26


def pips(rank, code, color):
    out = []
    for fx, fy in PIPS[rank]:
        x = BAND_X0 + (BAND_X1 - BAND_X0) * fx
        y = BAND_Y0 + (BAND_Y1 - BAND_Y0) * fy
        out.append(suit(code, x, y, PIP, color))
    return "".join(out)


# ---------------------------------------------------------------------------
# Court emblems — gold, geometric, and legible at 46px, which no figurative
# court art is. Each is drawn in a box centred on (90, 122).
# ---------------------------------------------------------------------------
def emblem(rank):
    if rank == "K":
        # Five-point crown on a banded base.
        return (f'<g transform="translate(90 122)" fill="{GOLD}">'
                '<path d="M-32 12 L-32 -12 L-19 2 L-9.5 -18 L0 -4 L9.5 -18 '
                'L19 2 L32 -12 L32 12 Z"/>'
                '<rect x="-32" y="16" width="64" height="10" rx="3"/>'
                '<circle cx="-16" cy="21" r="2.6" fill="' + CREAM + '"/>'
                '<circle cx="0" cy="21" r="2.6" fill="' + CREAM + '"/>'
                '<circle cx="16" cy="21" r="2.6" fill="' + CREAM + '"/>'
                '</g>')
    if rank == "Q":
        # Three-lobed coronet with a centre pearl.
        return (f'<g transform="translate(90 122)" fill="{GOLD}">'
                '<path d="M-30 12 L-30 -6 C-22 -6 -18 -12 -17 -18 '
                'C-12 -10 -6 -6 0 -6 C6 -6 12 -10 17 -18 '
                'C18 -12 22 -6 30 -6 L30 12 Z"/>'
                '<rect x="-30" y="16" width="60" height="10" rx="3"/>'
                '<circle cx="0" cy="-14" r="4.4"/>'
                '</g>')
    # Jack: a knave's shield. Deliberately a different silhouette from the King's
    # crown and the Queen's coronet — pointed at the bottom rather than toothed at
    # the top — so the three courts are distinguishable at 46px by shape alone.
    return (f'<g transform="translate(90 120)" fill="{GOLD}">'
            '<path d="M-27 -22 L27 -22 L27 2 C27 18 13 28 0 33 '
            'C-13 28 -27 18 -27 2 Z"/>'
            f'<path d="M-16 -4 L0 -15 L16 -4 L16 8 L0 -3 L-16 8 Z" fill="{CREAM}"/>'
            '</g>')


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------
def svg(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}">\n' + body + "\n</svg>\n")


def card(rank, code):
    color = SUITS[code]
    royal = rank == "A" or rank in COURT
    parts = [frame(royal), corners(rank, code, color)]

    if rank == "A":
        # One large suit, ringed. Aces read as special at any size.
        parts.append(f'<circle cx="90" cy="130" r="52" fill="none" '
                     f'stroke="{GOLD}" stroke-width="2.5" opacity="0.85"/>')
        parts.append(suit(code, 90, 130, 92, color))
    elif rank in COURT:
        parts.append(emblem(rank))
        parts.append(suit(code, 90, 190, 34, color))
    else:
        parts.append(pips(rank, code, color))
    return svg("\n".join(parts))


def back():
    """The most-seen card in the game: every opponent's hand, and the deck.

    It carries no rank, so this is the one place a bolder, glossier treatment
    costs nothing in legibility — which is exactly where the "modern web" look
    belongs.
    """
    body = f'''<defs>
    <linearGradient id="gloss" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.20"/>
      <stop offset="0.45" stop-color="#ffffff" stop-opacity="0.05"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="base" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#1b3330"/>
      <stop offset="1" stop-color="{BACK_BASE}"/>
    </linearGradient>
  </defs>
  <rect x="3" y="3" width="{W - 6}" height="{H - 6}" rx="16" fill="url(#base)"
        stroke="{GOLD}" stroke-width="3"/>
  <rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="10" fill="none"
        stroke="{GOLD}" stroke-width="1.4" opacity="0.5"/>
  <g stroke="{GOLD}" stroke-width="1.1" opacity="0.28" fill="none">
    <path d="M90 34 L146 126 L90 218 L34 126 Z"/>
    <path d="M90 56 L128 126 L90 196 L52 126 Z"/>
  </g>
  <g transform="translate(90 126)" fill="{GOLD}">
    <path d="M0 -30 L9 -9 L30 0 L9 9 L0 30 L-9 9 L-30 0 L-9 -9 Z" opacity="0.95"/>
    <circle cx="0" cy="0" r="5.5" fill="{CREAM}"/>
  </g>
  <rect x="3" y="3" width="{W - 6}" height="{H - 6}" rx="16" fill="url(#gloss)"/>'''
    return svg(body)


# ---------------------------------------------------------------------------
def build():
    """Return {filename: svg text} for the whole deck."""
    deck = {}
    for code in SUITS:
        for rank in RANKS:
            deck[f"{rank}{code}.svg"] = card(rank, code)
    deck["back.svg"] = back()
    return deck


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.join(here, "..", "static", "img", "cards")
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
                                   cell_px=62 * args.sheet_scale)
        print(f"Contact sheet: {path} {size}")


if __name__ == "__main__":
    main()
