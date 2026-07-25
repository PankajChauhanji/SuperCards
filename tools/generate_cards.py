"""Generate the card image set as SVG files.

Produces 52 faces (e.g. 7H.svg, AS.svg, 10C.svg, KD.svg) plus back.svg into
static/img/cards/. Faces are a clean minimal design: rank+suit in opposite
corners and a large central suit glyph (or custom illustrations for face cards J, Q, K and Ace).
The back uses the table's pine/gold palette so it sits naturally on the felt.

Run from the project root:  python tools/generate_cards.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "static", "img", "cards")

SUITS = {
    "S": ("\u2660", "#1c2b27"),  # ♠
    "H": ("\u2665", "#cf3b2e"),  # ♥
    "D": ("\u2666", "#cf3b2e"),  # ♦
    "C": ("\u2663", "#1c2b27"),  # ♣
}
RANKS = {1: "A", 11: "J", 12: "Q", 13: "K"}
for n in range(2, 11):
    RANKS[n] = str(n)

FACE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 252" width="180" height="252">
  <rect x="3" y="3" width="174" height="246" rx="16" fill="#fdfbf5" stroke="#d8cfb8" stroke-width="2"/>
  <g fill="{color}" font-family="Georgia, 'Times New Roman', serif" font-weight="700">
    <g>
      <text x="24" y="44" font-size="{rank_size}" text-anchor="middle">{rank}</text>
      <text x="24" y="72" font-size="24" text-anchor="middle">{suit}</text>
    </g>
    <g transform="rotate(180 90 126)">
      <text x="24" y="44" font-size="{rank_size}" text-anchor="middle">{rank}</text>
      <text x="24" y="72" font-size="24" text-anchor="middle">{suit}</text>
    </g>
    <text x="90" y="138" font-size="104" text-anchor="middle" dominant-baseline="central">{suit}</text>
  </g>
</svg>
"""

FACE_A = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 252" width="180" height="252">
  <rect x="3" y="3" width="174" height="246" rx="16" fill="#fdfbf5" stroke="#d8cfb8" stroke-width="2"/>
  <g fill="{color}" font-family="Georgia, 'Times New Roman', serif" font-weight="700">
    <g>
      <text x="24" y="44" font-size="34" text-anchor="middle">A</text>
      <text x="24" y="72" font-size="24" text-anchor="middle">{suit}</text>
    </g>
    <g transform="rotate(180 90 126)">
      <text x="24" y="44" font-size="34" text-anchor="middle">A</text>
      <text x="24" y="72" font-size="24" text-anchor="middle">{suit}</text>
    </g>
  </g>
  <!-- Grand Ornate Ace Design -->
  <g stroke="{color}" fill="none">
    <circle cx="90" cy="138" r="60" stroke-width="1.5" stroke-dasharray="3 3" opacity="0.65"/>
    <circle cx="90" cy="138" r="52" stroke-width="1.0" opacity="0.4"/>
    <path d="M 90,68 L 92,74 L 98,76 L 92,78 L 90,84 L 88,78 L 82,76 L 88,74 Z" fill="{color}" stroke="none"/>
    <path d="M 90,192 L 92,198 L 98,200 L 92,202 L 90,208 L 88,202 L 82,200 L 88,198 Z" fill="{color}" stroke="none"/>
    <path d="M 32,138 L 38,136 L 40,130 L 42,136 L 48,138 L 42,140 L 40,146 L 38,140 Z" fill="{color}" stroke="none"/>
    <path d="M 132,138 L 138,136 L 140,130 L 142,136 L 148,138 L 142,140 L 140,146 L 138,140 Z" fill="{color}" stroke="none"/>
  </g>
  <g fill="{color}" font-family="Georgia, 'Times New Roman', serif" font-weight="700">
    <text x="90" y="138" font-size="94" text-anchor="middle" dominant-baseline="central">{suit}</text>
  </g>
</svg>
"""

# Face cards: a clean GOLD emblem that says what the rank *is* — Jack = sword
# (the soldier/knave), Queen = tiara, King = crown+cross — over a large suit
# glyph in the suit colour. Reads clearly even at ~60px on the table, and stays
# consistent with the number cards' big central pip.
_FACE_TMPL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 252" width="180" height="252">
  <rect x="3" y="3" width="174" height="246" rx="16" fill="#fdfbf5" stroke="#d8cfb8" stroke-width="2"/>
  <!-- Corners -->
  <g fill="{color}" font-family="Georgia, 'Times New Roman', serif" font-weight="700">
    <g>
      <text x="26" y="46" font-size="32" text-anchor="middle">{rank}</text>
      <text x="26" y="76" font-size="26" text-anchor="middle">{suit}</text>
    </g>
    <g transform="rotate(180 90 126)">
      <text x="26" y="46" font-size="32" text-anchor="middle">{rank}</text>
      <text x="26" y="76" font-size="26" text-anchor="middle">{suit}</text>
    </g>
  </g>
  <!-- Royal emblem (gold) -->
  <g fill="#c99530" stroke="#8a6416" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round">
    {emblem}
  </g>
  <!-- Large suit glyph -->
  <text x="90" y="176" font-size="86" fill="{color}" text-anchor="middle" dominant-baseline="central"
        font-family="Georgia, 'Times New Roman', serif" font-weight="700">{suit}</text>
</svg>
"""

# Jack — an upright sword (the knave / soldier).
EMBLEM_J = """
    <circle cx="90" cy="54" r="5"/>
    <rect x="86.5" y="59" width="7" height="15" rx="2"/>
    <rect x="70" y="74" width="40" height="8" rx="3"/>
    <path d="M 82,82 L 98,82 L 90,126 Z"/>
"""

# Queen — a rounded tiara with gems (no cross).
EMBLEM_Q = """
    <path d="M 58,110 Q 58,78 74,94 Q 82,70 90,88 Q 98,70 106,94 Q 122,78 122,110 Z"/>
    <rect x="58" y="110" width="64" height="13" rx="3"/>
    <circle cx="74" cy="92" r="3.5" fill="#fdfbf5" stroke="none"/>
    <circle cx="90" cy="84" r="4" fill="#fdfbf5" stroke="none"/>
    <circle cx="106" cy="92" r="3.5" fill="#fdfbf5" stroke="none"/>
"""

# King — a tall crown topped with a cross.
EMBLEM_K = """
    <rect x="86.5" y="40" width="7" height="16" rx="1.5"/>
    <rect x="81" y="45" width="18" height="6" rx="1.5"/>
    <path d="M 56,110 L 60,74 L 74,94 L 90,62 L 106,94 L 120,74 L 124,110 Z"/>
    <rect x="56" y="110" width="68" height="13" rx="3"/>
    <circle cx="72" cy="116" r="3.5" fill="#fdfbf5" stroke="none"/>
    <circle cx="90" cy="116" r="3.5" fill="#fdfbf5" stroke="none"/>
    <circle cx="108" cy="116" r="3.5" fill="#fdfbf5" stroke="none"/>
"""

FACE_J = _FACE_TMPL.replace("{emblem}", EMBLEM_J).replace("{rank}", "J")
FACE_Q = _FACE_TMPL.replace("{emblem}", EMBLEM_Q).replace("{rank}", "Q")
FACE_K = _FACE_TMPL.replace("{emblem}", EMBLEM_K).replace("{rank}", "K")

BACK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 252" width="180" height="252">
  <rect x="3" y="3" width="174" height="246" rx="16" fill="#173029" stroke="#0e201c" stroke-width="2"/>
  <rect x="14" y="14" width="152" height="224" rx="10" fill="none" stroke="#e6b23c" stroke-width="2" opacity="0.85"/>
  <g stroke="#e6b23c" stroke-width="1" opacity="0.18">
    {lattice}
  </g>
  <circle cx="90" cy="126" r="46" fill="#0e201c" opacity="0.55"/>
  <text x="90" y="126" font-size="74" font-family="'Space Grotesk', Georgia, serif" font-weight="700"
        fill="#e6b23c" text-anchor="middle" dominant-baseline="central">7</text>
  <g fill="#e6b23c" font-family="Georgia, serif" font-size="16" opacity="0.9" text-anchor="middle">
    <text x="90" y="58" dominant-baseline="central">\u2660 \u2665 \u2666 \u2663</text>
    <text x="90" y="196" dominant-baseline="central">\u2663 \u2666 \u2665 \u2660</text>
  </g>
</svg>
"""


def lattice_lines():
    lines = []
    for x in range(-180, 200, 22):
        lines.append(f'<line x1="{x}" y1="14" x2="{x + 224}" y2="238"/>')
        lines.append(f'<line x1="{x + 224}" y1="14" x2="{x}" y2="238"/>')
    return "\n    ".join(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    count = 0
    for suit, (glyph, color) in SUITS.items():
        for rank, label in RANKS.items():
            if label == "A":
                svg = FACE_A.format(color=color, suit=glyph)
            elif label == "J":
                svg = FACE_J.format(color=color, suit=glyph)
            elif label == "Q":
                svg = FACE_Q.format(color=color, suit=glyph)
            elif label == "K":
                svg = FACE_K.format(color=color, suit=glyph)
            else:
                rank_size = 28 if len(label) > 1 else 34
                svg = FACE.format(color=color, rank=label, suit=glyph, rank_size=rank_size)
            
            with open(os.path.join(OUT, f"{label}{suit}.svg"), "w", encoding="utf-8") as f:
                f.write(svg)
            count += 1
    with open(os.path.join(OUT, "back.svg"), "w", encoding="utf-8") as f:
        f.write(BACK.format(lattice=lattice_lines()))
    print(f"Wrote {count} faces + back.svg to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
