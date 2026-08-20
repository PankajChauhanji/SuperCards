
"""Super Cards v4 - clean, modern SVG playing-card generator.

Design principles
-----------------
1. Classic playing-card readability comes first.
2. Number cards use standard pip counts and spacing.
3. No filled red/green liquid blocks and no middle-crossing ribbons.
4. Modern styling comes from very subtle corner curves and gold details.
5. Every corner index is built independently; no suit glyphs overlap.
6. J/Q/K use distinct silhouettes, with a shared crown design.
   - Jack: young knight, cap + sword.
   - Queen: long hair, shared crown, jewelry, gown.
   - King: beard, shared crown, sword + mantle.
7. All artwork is SVG geometry; no external images or fonts are required.

Run from the project root:
    python3 tools/generate_cards.py
"""

from __future__ import annotations

import os
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
OUT = os.path.join(PROJECT_ROOT, "static", "img", "cards")

W, H = 180, 252

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

C = {
    "cream": "#FFF8EA",
    "cream2": "#F7EEDC",
    "ink": "#102B24",
    "green": "#1F5B48",
    "green2": "#2D765E",
    "red": "#C74639",
    "red2": "#D86250",
    "gold": "#D9AA3B",
    "gold2": "#F0D16A",
    "gold3": "#9A711D",
    "skin": "#E7B17C",
    "skin_shadow": "#CB8E58",
    "black": "#0C1714",
}

SUITS = {
    "S": {"color": C["ink"]},
    "H": {"color": C["red"]},
    "D": {"color": C["red"]},
    "C": {"color": C["ink"]},
}

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

# Coordinates are normalized to the central area of the card.
PIPS = {
    2:  [(0.50, 0.22), (0.50, 0.78)],
    3:  [(0.50, 0.18), (0.50, 0.50), (0.50, 0.82)],
    4:  [(0.30, 0.24), (0.70, 0.24), (0.30, 0.76), (0.70, 0.76)],
    5:  [(0.30, 0.20), (0.70, 0.20), (0.50, 0.50), (0.30, 0.80), (0.70, 0.80)],
    6:  [(0.30, 0.16), (0.70, 0.16), (0.30, 0.50), (0.70, 0.50), (0.30, 0.84), (0.70, 0.84)],
    7:  [(0.30, 0.13), (0.70, 0.13), (0.50, 0.30), (0.30, 0.50),
         (0.70, 0.50), (0.30, 0.87), (0.70, 0.87)],
    8:  [(0.30, 0.12), (0.70, 0.12), (0.30, 0.35), (0.70, 0.35),
         (0.30, 0.65), (0.70, 0.65), (0.30, 0.88), (0.70, 0.88)],
    9:  [(0.30, 0.11), (0.70, 0.11), (0.30, 0.33), (0.70, 0.33), (0.50, 0.50),
         (0.30, 0.67), (0.70, 0.67), (0.30, 0.89), (0.70, 0.89)],
    10: [(0.30, 0.10), (0.70, 0.10), (0.30, 0.30), (0.70, 0.30),
         (0.30, 0.50), (0.70, 0.50), (0.30, 0.70), (0.70, 0.70),
         (0.30, 0.90), (0.70, 0.90)],
}

# ---------------------------------------------------------------------------
# SVG primitives
# ---------------------------------------------------------------------------

def defs() -> str:
    return f"""
    <defs>
      <linearGradient id="cardSurface" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="{C["cream"]}"/>
        <stop offset="100%" stop-color="{C["cream2"]}"/>
      </linearGradient>

      <linearGradient id="goldMetal" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="{C["gold2"]}"/>
        <stop offset="50%" stop-color="{C["gold"]}"/>
        <stop offset="100%" stop-color="{C["gold3"]}"/>
      </linearGradient>

      <filter id="cardShadow" x="-15%" y="-15%" width="130%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="2.2"
                      flood-color="#000000" flood-opacity="0.17"/>
      </filter>

      <filter id="artShadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="1" stdDeviation="1.0"
                      flood-color="#000000" flood-opacity="0.12"/>
      </filter>
    </defs>
    """


def svg_start(label: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" aria-label="{escape(label)}">',
        defs(),
    ]


def card_frame(parts: list[str]) -> None:
    parts.extend([
        f'<rect x="3" y="3" width="174" height="246" rx="18" fill="url(#cardSurface)" '
        f'stroke="{C["gold3"]}" stroke-width="2.1" filter="url(#cardShadow)"/>',
        f'<rect x="8" y="8" width="164" height="236" rx="15" fill="none" '
        f'stroke="{C["gold"]}" stroke-width="1.15"/>',
        f'<rect x="13" y="13" width="154" height="226" rx="12" fill="none" '
        f'stroke="{C["gold2"]}" stroke-width="0.55" opacity="0.45"/>',
    ])


def vector_suit(suit: str, x: float, y: float, size: float, color: str) -> str:
    """Draw one clean, traditional-looking suit as standalone SVG geometry."""
    s = size / 40.0

    if suit == "H":
        # Heart with broad, even lobes and a clean pointed bottom.
        path = (
            "M0 17 "
            "C-4 12 -20 3 -21 -7 "
            "C-22 -17 -15 -22 -7 -22 "
            "C-3 -22 -1 -20 0 -16 "
            "C2 -20 4 -22 9 -22 "
            "C17 -22 22 -16 21 -7 "
            "C20 3 4 12 0 17 Z"
        )

    elif suit == "D":
        # Rounded diamond, closer in visual weight to the reference deck.
        path = (
            "M0 -20 "
            "C5 -14 13 -6 17 0 "
            "C13 6 5 14 0 20 "
            "C-5 14 -13 6 -17 0 "
            "C-13 -6 -5 -14 0 -20 Z"
        )

    elif suit == "S":
        # Classic spade with pointed crown, broad shoulders and a narrow stem.
        path = (
            "M0 -22 "
            "C-3 -16 -18 -5 -22 4 "
            "C-25 12 -20 20 -13 21 "
            "C-8 22 -4 19 0 14 "
            "C4 19 8 22 13 21 "
            "C20 20 25 12 22 4 "
            "C18 -5 3 -16 0 -22 Z "
            "M-5 12 L5 12 L2 25 L8 25 L8 29 "
            "L-8 29 L-8 25 L-2 25 Z"
        )

    elif suit == "C":
        # Cleaner three-lobed club with a separate tapered stem.
        path = (
            "M0 -5 "
            "C-3 -13 -9 -18 -16 -17 "
            "C-24 -16 -27 -8 -23 -2 "
            "C-21 2 -17 4 -13 4 "
            "C-19 11 -16 18 -9 20 "
            "C-5 21 -2 19 0 16 "
            "C2 19 5 21 9 20 "
            "C16 18 19 11 13 4 "
            "C17 4 21 2 23 -2 "
            "C27 -8 24 -16 16 -17 "
            "C9 -18 3 -13 0 -5 Z "
            "M-3 15 L3 15 L2 27 L7 27 L7 31 "
            "L-7 31 L-7 27 L-2 27 Z"
        )
    else:
        raise ValueError(f"Unknown suit: {suit}")

    return (
        f'<g transform="translate({x:.2f} {y:.2f}) scale({s:.5f})" '
        f'fill="{color}" stroke="none"><path d="{path}"/></g>'
    )


def corner_index(parts: list[str], rank: str, suit: str, color: str) -> None:
    """Draw clean top-left and bottom-right indices with isolated geometry."""
    rank_size = 30 if len(rank) == 1 else 25

    # Top-left: rank, then suit.
    parts.append(
        f'<text x="22" y="39" font-size="{rank_size}" text-anchor="middle" '
        f'fill="{color}" font-family="Georgia, Times New Roman, serif" font-weight="700">'
        f'{escape(rank)}</text>'
    )
    parts.append(vector_suit(suit, 22, 61, 15, color))

    # Bottom-right: exact visual mirror of the top index.
    # We build it in its final location, then rotate the two primitives in place.
    # Final upright positions before rotation are rank at y=213 and suit at y=193.
    # Using pivot (158, 203) maps them to the same lower-right footprint after 180°.
    pivot_x, pivot_y = 158, 203

    parts.append(
        f'<g transform="rotate(180 {pivot_x} {pivot_y})">'
        f'<text x="158" y="193" font-size="{rank_size}" text-anchor="middle" '
        f'fill="{color}" font-family="Georgia, Times New Roman, serif" font-weight="700">'
        f'{escape(rank)}</text>'
        f'</g>'
    )
    parts.append(
        f'<g transform="rotate(180 {pivot_x} {pivot_y})">'
        f'{vector_suit(suit, 158, 213, 15, color)}'
        f'</g>'
    )


def corner_curve(parts: list[str], suit: str) -> None:
    """Modern liquid-inspired corner ribbons, kept out of the play area."""
    fill_color = C["red2"] if suit in {"H", "D"} else C["green2"]

    # Upper-right filled corner.
    parts.append(
        f'<path d="M110 10 C128 17 149 11 169 22 L169 61 '
        f'C152 51 141 52 127 56 C116 59 109 55 104 48 '
        f'C112 36 115 22 110 10 Z" fill="{fill_color}" opacity="0.92"/>'
    )
    parts.append(
        f'<path d="M111 12 C130 18 150 14 168 23" fill="none" '
        f'stroke="{C["gold"]}" stroke-width="2.1" stroke-linecap="round" opacity="0.95"/>'
    )
    parts.append(
        f'<path d="M112 16 C131 22 150 18 168 27" fill="none" '
        f'stroke="#FFFFFF" stroke-width="0.65" stroke-linecap="round" opacity="0.22"/>'
    )

    # Lower-left filled corner, kept away from bottom-right index.
    parts.append(
        f'<path d="M11 191 C27 201 42 201 56 195 C68 190 78 186 91 191 '
        f'C104 196 114 204 130 207 C98 222 56 235 11 238 Z" '
        f'fill="{fill_color}" opacity="0.90"/>'
    )
    parts.append(
        f'<path d="M12 191 C28 202 42 202 57 196 C70 191 79 188 92 193 '
        f'C104 199 114 205 129 208" fill="none" '
        f'stroke="{C["gold"]}" stroke-width="2.0" stroke-linecap="round" opacity="0.95"/>'
    )


def tiny_sparkle(parts: list[str], x: float, y: float, scale: float = 1.0) -> None:
    parts.append(
        f'<path d="M{x} {y-3.5*scale} L{x+1*scale} {y-1*scale} '
        f'L{x+3.5*scale} {y} L{x+1*scale} {y+1*scale} '
        f'L{x} {y+3.5*scale} L{x-1*scale} {y+1*scale} '
        f'L{x-3.5*scale} {y} L{x-1*scale} {y-1*scale} Z" '
        f'fill="{C["gold"]}" opacity="0.55"/>'
    )


def pip_positions(rank: int):
    x0, x1 = 62, 118
    y0, y1 = 79, 202
    return [(x0 + (x1 - x0) * px, y0 + (y1 - y0) * py) for px, py in PIPS[rank]]


def add_pips(parts: list[str], rank: int, suit: str, color: str) -> None:
    for index, (x, y) in enumerate(pip_positions(rank)):
        parts.append(vector_suit(suit, x, y, 16.5, color))
        # Decorative dots sit well outside the pip itself.
        if rank >= 9 and index in {0, len(PIPS[rank]) - 1}:
            tiny_sparkle(parts, x + (7 if x < 90 else -7), y, 0.45)


# ---------------------------------------------------------------------------
# Number + Ace
# ---------------------------------------------------------------------------

def number_card(rank: int, suit: str) -> str:
    info = SUITS[suit]
    parts = svg_start(f"{rank} of {suit}")
    card_frame(parts)
    corner_curve(parts, suit)
    corner_index(parts, str(rank), suit, info["color"])

    # Faint decorative oval, intentionally below visibility threshold at gameplay size.
    parts.append(
        f'<ellipse cx="90" cy="141" rx="31" ry="61" fill="none" '
        f'stroke="{C["gold"]}" stroke-width="0.6" opacity="0.06"/>'
    )

    add_pips(parts, rank, suit, info["color"])

    tiny_sparkle(parts, 44, 91, 0.5)
    tiny_sparkle(parts, 136, 91, 0.45)

    parts.append("</svg>")
    return "\n".join(parts)


def ace_card(suit: str) -> str:
    info = SUITS[suit]
    parts = svg_start(f"Ace of {suit}")
    card_frame(parts)
    corner_curve(parts, suit)
    corner_index(parts, "A", suit, info["color"])

    parts.extend([
        f'<circle cx="90" cy="142" r="43" fill="none" stroke="{C["gold"]}" stroke-width="1.0" opacity="0.5"/>',
        f'<circle cx="90" cy="142" r="35" fill="none" stroke="{C["gold"]}" stroke-width="0.6" opacity="0.28"/>',
        f'<path d="M90 98 L96 132 L126 142 L96 152 L90 186 L84 152 L54 142 L84 132 Z" '
        f'fill="none" stroke="{C["gold"]}" stroke-width="1.1" opacity="0.7"/>',
        vector_suit(suit, 90, 142, 68, info["color"]),
    ])

    for x, y, scale in [(44, 105, .58), (136, 105, .48), (44, 180, .48), (136, 180, .58)]:
        tiny_sparkle(parts, x, y, scale)

    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Shared face-card components
# ---------------------------------------------------------------------------

def shared_crown() -> str:
    """One shared crown design for Queen and King."""
    return f"""
      <g>
        <path d="M-31 -52 L-25 -77 L-12 -58 L0 -80 L13 -58 L26 -77 L31 -52 Z"
              fill="url(#goldMetal)" stroke="{C["gold3"]}" stroke-width="1.2"/>
        <rect x="-31" y="-52" width="62" height="8" rx="2.2"
              fill="{C["gold"]}" stroke="{C["gold3"]}" stroke-width="1"/>
        <circle cx="-12" cy="-59" r="2.3" fill="{C["cream"]}"/>
        <circle cx="0" cy="-67" r="2.7" fill="{C["cream"]}"/>
        <circle cx="13" cy="-59" r="2.3" fill="{C["cream"]}"/>
      </g>
    """


def jack_art(parts: list[str], suit: str) -> None:
    color = SUITS[suit]["color"]
    parts.append(
        f"""
        <g transform="translate(90 139)" filter="url(#artShadow)">
          <!-- shield -->
          <path d="M-45 -41 Q0 -60 45 -41 L39 50 Q0 70 -39 50 Z"
                fill="none" stroke="{C["gold"]}" stroke-width="1.1" opacity="0.35"/>

          <!-- feathered cap -->
          <path d="M-14 -44 Q-9 -67 14 -77 Q13 -58 3 -43 Z"
                fill="{C["green2"]}" stroke="{C["gold3"]}" stroke-width="1"/>
          <path d="M-32 -42 Q-17 -60 10 -58 Q26 -54 31 -41 Q2 -49 -32 -42 Z"
                fill="{C["green"]}" stroke="{C["gold3"]}" stroke-width="1.2"/>
          <path d="M-31 -39 Q-2 -48 31 -39"
                fill="none" stroke="{C["gold"]}" stroke-width="1.8"/>

          <!-- face, clearly younger/profiled -->
          <path d="M-11 -31 Q-7 -49 10 -49 Q23 -45 23 -29 L32 -21
                   L23 -17 L21 1 Q9 14 -6 8 L-19 -5 Z"
                fill="{C["skin"]}" stroke="{C["gold3"]}" stroke-width="1.0"/>
          <path d="M20 -27 L31 -21" stroke="{C["black"]}" stroke-width="1.0" stroke-linecap="round"/>
          <circle cx="8" cy="-31" r="1.4" fill="{C["black"]}"/>

          <!-- neck + pointed collar -->
          <path d="M-7 7 L0 24 L8 7" fill="{C["skin"]}" stroke="{C["gold3"]}" stroke-width="1"/>
          <path d="M-10 8 L0 28 L10 8 L18 25 L0 38 L-18 25 Z"
                fill="{C["cream"]}" stroke="{C["gold"]}" stroke-width="1"/>

          <!-- tunic -->
          <path d="M-28 27 Q0 17 28 27 L41 59 Q0 73 -41 59 Z"
                fill="{C["green"]}" stroke="{C["gold3"]}" stroke-width="1.15"/>
          <path d="M-15 29 L0 43 L15 29" fill="none" stroke="{C["gold2"]}" stroke-width="1.5"/>

          <!-- sword -->
          <path d="M-37 55 L-31 55 L-2 -50 L4 -65 L1 -43 L-25 58 Z"
                fill="url(#goldMetal)" stroke="{C["gold3"]}" stroke-width="0.95"/>
          <path d="M-43 49 Q-34 43 -25 49" fill="none" stroke="{C["gold"]}" stroke-width="4.5" stroke-linecap="round"/>
          <circle cx="-34" cy="46" r="2.3" fill="{C["gold2"]}"/>

          <circle cx="0" cy="52" r="8.5" fill="{C["cream"]}" stroke="{C["gold"]}" stroke-width="1"/>
          {vector_suit(suit, 0, 52, 12, color)}
        </g>
        """
    )


def queen_art(parts: list[str], suit: str) -> None:
    color = SUITS[suit]["color"]
    parts.append(
        f"""
        <g transform="translate(90 141)" filter="url(#artShadow)">
          <!-- long flowing hair -->
          <path d="M-34 -17 Q-35 -56 5 -63 Q34 -55 35 -18
                   L50 48 Q27 66 0 68 Q-29 65 -48 46 Z"
                fill="{C["ink"]}" stroke="{C["gold3"]}" stroke-width="1.1"/>

          <!-- shared queen/king crown -->
          {shared_crown()}

          <!-- face -->
          <path d="M-17 -29 Q-11 -51 5 -54 Q21 -50 23 -30 L19 -7
                   Q9 8 -5 8 L-18 -5 Z"
                fill="{C["skin"]}" stroke="{C["gold3"]}" stroke-width="1"/>
          <path d="M-20 -31 Q-14 -55 8 -57 Q28 -52 31 -32
                   Q15 -37 6 -26 Q0 -16 -14 -10 Q-25 -17 -20 -31 Z"
                fill="{C["ink"]}" stroke="{C["gold3"]}" stroke-width="1"/>
          <circle cx="9" cy="-29" r="1.5" fill="{C["black"]}"/>

          <!-- queen jewelry -->
          <circle cx="29" cy="0" r="3.1" fill="{C["gold2"]}" stroke="{C["gold3"]}" stroke-width="0.7"/>
          <path d="M-11 3 Q0 12 11 3" fill="none" stroke="{C["gold2"]}" stroke-width="1.2"/>
          <circle cx="0" cy="12" r="3.1" fill="{C["gold2"]}" stroke="{C["gold3"]}" stroke-width="0.7"/>

          <!-- gown -->
          <path d="M-36 12 Q0 0 36 12 L49 62 Q0 76 -49 62 Z"
                fill="{C["red"]}" stroke="{C["gold3"]}" stroke-width="1.15"/>
          <path d="M-23 34 Q0 46 23 34" fill="none" stroke="{C["gold2"]}" stroke-width="1.6"/>
          <path d="M-11 14 L0 30 L11 14" fill="none" stroke="{C["gold2"]}" stroke-width="1.4"/>

          <circle cx="38" cy="10" r="8.5" fill="{C["cream"]}" stroke="{C["gold"]}" stroke-width="1"/>
          {vector_suit(suit, 38, 10, 12, color)}
        </g>
        """
    )


def king_art(parts: list[str], suit: str) -> None:
    color = SUITS[suit]["color"]
    parts.append(
        f"""
        <g transform="translate(90 141)" filter="url(#artShadow)">
          <!-- broad king mantle -->
          <path d="M-50 15 Q0 -1 50 15 L56 64 Q0 80 -56 64 Z"
                fill="{C["green"]}" stroke="{C["gold3"]}" stroke-width="1.25"/>
          <path d="M-40 42 Q0 55 40 42" fill="none" stroke="{C["gold2"]}" stroke-width="1.9"/>

          <!-- same crown used by Queen -->
          {shared_crown()}

          <!-- front-facing head -->
          <path d="M-22 -30 Q-18 -55 2 -58 Q22 -55 25 -30
                   L20 2 Q8 17 -7 13 L-22 1 Z"
                fill="{C["skin"]}" stroke="{C["gold3"]}" stroke-width="1"/>

          <!-- king's short hair -->
          <path d="M-23 -31 Q-18 -57 5 -60 Q27 -55 31 -33
                   L19 -29 L11 -44 L-4 -37 L-14 -21 Z"
                fill="{C["black"]}" stroke="{C["gold3"]}" stroke-width="1"/>

          <!-- eyes -->
          <circle cx="-8" cy="-28" r="1.5" fill="{C["black"]}"/>
          <circle cx="10" cy="-28" r="1.5" fill="{C["black"]}"/>
          <path d="M-5 -16 Q2 -12 8 -16" fill="none" stroke="{C["skin_shadow"]}"
                stroke-width="1" stroke-linecap="round"/>

          <!-- moustache + full beard: makes King clearly different from Queen -->
          <path d="M-2 -9 Q2 -13 7 -9 Q3 -5 -2 -9 Z" fill="{C["black"]}"/>
          <path d="M-13 -3 Q1 22 16 -3 L13 16 Q1 32 -11 15 Z" fill="{C["black"]}"/>

          <!-- KING SWORD -->
          <path d="M-44 58 L-38 58 L-7 -42 L-1 -63 L-3 -40 L-31 60 Z"
                fill="url(#goldMetal)" stroke="{C["gold3"]}" stroke-width="1"/>
          <path d="M-49 51 Q-40 45 -30 51" fill="none"
                stroke="{C["gold"]}" stroke-width="4.5" stroke-linecap="round"/>
          <circle cx="-39" cy="49" r="2.4" fill="{C["gold2"]}"/>

          <!-- suit medallion -->
          <circle cx="0" cy="41" r="9" fill="{C["cream"]}"
                  stroke="{C["gold"]}" stroke-width="1"/>
          {vector_suit(suit, 0, 41, 13, color)}
        </g>
        """
    )


def face_card(rank: str, suit: str) -> str:
    info = SUITS[suit]
    parts = svg_start(f"{rank} of {suit}")
    card_frame(parts)
    corner_curve(parts, suit)
    corner_index(parts, rank, suit, info["color"])

    if rank == "J":
        jack_art(parts, suit)
    elif rank == "Q":
        queen_art(parts, suit)
    elif rank == "K":
        king_art(parts, suit)
    else:
        raise ValueError(rank)

    for x, y, scale in [(50, 96, .40), (130, 96, .35), (50, 188, .35), (130, 188, .40)]:
        tiny_sparkle(parts, x, y, scale)

    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Back
# ---------------------------------------------------------------------------

def card_back() -> str:
    lattice = "".join(
        f'<line x1="{x}" y1="18" x2="{x+216}" y2="234"/>'
        f'<line x1="{x+216}" y1="18" x2="{x}" y2="234"/>'
        for x in range(-180, 200, 24)
    )

    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
      <defs>
        <linearGradient id="backBase" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#0B2A20"/>
          <stop offset="55%" stop-color="#174C3B"/>
          <stop offset="100%" stop-color="#082019"/>
        </linearGradient>
        <linearGradient id="backGold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="{C["gold2"]}"/>
          <stop offset="50%" stop-color="{C["gold"]}"/>
          <stop offset="100%" stop-color="{C["gold3"]}"/>
        </linearGradient>
      </defs>

      <rect x="3" y="3" width="174" height="246" rx="18" fill="url(#backBase)"
            stroke="{C["gold3"]}" stroke-width="2.2"/>
      <rect x="9" y="9" width="162" height="234" rx="15" fill="none"
            stroke="{C["gold"]}" stroke-width="1.2"/>
      <rect x="15" y="15" width="150" height="222" rx="11" fill="none"
            stroke="{C["green2"]}" stroke-width="1"/>

      <g stroke="{C["gold"]}" stroke-width="0.55" opacity="0.11">{lattice}</g>

      <path d="M16 62 C38 51 52 55 69 61 C86 67 101 68 118 59 C137 49 151 53 164 45"
            fill="none" stroke="{C["gold"]}" stroke-width="1.8" stroke-linecap="round" opacity="0.82"/>
      <path d="M16 190 C37 201 52 198 69 191 C86 184 101 188 118 196 C137 205 151 201 164 209"
            fill="none" stroke="{C["gold"]}" stroke-width="1.8" stroke-linecap="round" opacity="0.82"/>

      <circle cx="90" cy="126" r="46" fill="#0A261D" opacity="0.70"
              stroke="{C["gold3"]}" stroke-width="1"/>
      <circle cx="90" cy="126" r="38" fill="none"
              stroke="{C["gold"]}" stroke-width="1.15"/>
      <circle cx="90" cy="126" r="31" fill="none"
              stroke="{C["gold2"]}" stroke-width="0.6" opacity="0.55"/>

      <text x="90" y="131" font-size="61" font-family="Georgia, serif" font-weight="700"
            fill="url(#backGold)" text-anchor="middle" dominant-baseline="central">7</text>

      {vector_suit("S", 69, 49, 10, C["gold2"])}
      {vector_suit("H", 87, 49, 10, C["gold2"])}
      {vector_suit("D", 105, 49, 10, C["gold2"])}
      {vector_suit("C", 123, 49, 10, C["gold2"])}

      {vector_suit("C", 69, 203, 10, C["gold2"])}
      {vector_suit("D", 87, 203, 10, C["gold2"])}
      {vector_suit("H", 105, 203, 10, C["gold2"])}
      {vector_suit("S", 123, 203, 10, C["gold2"])}

      <path d="M90 77 L94 85 L103 89 L94 93 L90 101 L86 93 L77 89 L86 85 Z"
            fill="url(#backGold)"/>
      <path d="M90 151 L94 159 L103 163 L94 167 L90 175 L86 167 L77 163 L86 159 Z"
            fill="url(#backGold)"/>
    </svg>
    """


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

def write_card(filename: str, content: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, filename), "w", encoding="utf-8") as fh:
        fh.write(content)


def main() -> None:
    count = 0

    for suit in SUITS:
        for rank in RANKS:
            if rank == "A":
                svg = ace_card(suit)
            elif rank in {"J", "Q", "K"}:
                svg = face_card(rank, suit)
            else:
                svg = number_card(int(rank), suit)

            write_card(f"{rank}{suit}.svg", svg)
            count += 1

    write_card("back.svg", card_back())
    print(f"Wrote {count} card faces + back.svg to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()