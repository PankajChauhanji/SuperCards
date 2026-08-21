import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""The card deck must be complete, valid, and self-contained.

The last point is the one that matters and the one that was broken: the previous
generator drew suits as Unicode text (`<text>♠</text>` in Georgia), so the shapes
came from the *viewer's* operating system. On a device without those fonts the
cards render tofu boxes, and several mobile browsers substitute the colour emoji
face instead — the deck looked correct only because the dev machine happened to
have the right fonts installed. Nothing caught it, because nothing looked.

So this asserts the deck is 53 valid SVGs, that suits are geometry rather than
glyphs, and that nothing reaches outside the file for artwork. Ranks are still
allowed as <text>: they are ASCII, so every fallback font has them.
"""
import re
import xml.etree.ElementTree as ET

from game.core.cards import RANKS, SUITS, rank_code

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# BOTH decks are required: core/deck.js lets each player pick between them, and
# "royal" (cards_v2) is the default, so a missing cards_v2 means broken card
# images for everyone who has not opted out. Same rules for both — an alternative
# deck is no excuse for shipping a font-dependent or broken one.
DECKS = [("cards", True), ("cards_v2", True)]

SUIT_GLYPHS = "♠♥♦♣"      # ♠ ♥ ♦ ♣
results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def audit(deck_name):
    """Run every rule against one deck directory."""
    cards_dir = os.path.join(REPO, "static", "img", deck_name)
    tag = "[%s]" % deck_name

    def c(ok, msg):
        """Name the deck in every message, so a failure is unambiguous."""
        check(ok, tag + " " + msg)

    # Every id the game can ask for, derived from the game's own card model rather
    # than a hardcoded list — so a rank or suit change here fails loudly.
    expected = {f"{rank_code(r)}{s}.svg" for r in RANKS for s in SUITS}
    expected.add("back.svg")

    present = {f for f in os.listdir(cards_dir) if f.endswith(".svg")}
    missing = sorted(expected - present)
    extra = sorted(present - expected)

    c(not missing, "every card the deck needs exists (%d)%s"
          % (len(expected), "" if not missing else " missing: %s" % ", ".join(missing)))
    c(not extra, "no stray files in the deck%s"
          % ("" if not extra else ": %s" % ", ".join(extra)))

    bad_xml, glyph_suits, external, no_geometry, wrong_box = [], [], [], [], []

    for name in sorted(expected & present):
        path = os.path.join(cards_dir, name)
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()

        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            bad_xml.append("%s (%s)" % (name, exc))
            continue

        if root.get("viewBox") != "0 0 180 252":
            wrong_box.append(name)

        # Suits must be drawn, not typed.
        for text_el in root.iter("{http://www.w3.org/2000/svg}text"):
            if text_el.text and any(g in text_el.text for g in SUIT_GLYPHS):
                glyph_suits.append(name)
                break

        # Nothing may pull artwork from outside the file. Internal gradient
        # references (url(#...)) are fine; anything else is not.
        for ref in re.findall(r'(?:href|xlink:href)="([^"]+)"', raw):
            if not ref.startswith("#"):
                external.append("%s -> %s" % (name, ref))
        for ref in re.findall(r"url\((?!#)([^)]+)\)", raw):
            external.append("%s -> url(%s)" % (name, ref))

        # A card that is only a frame would pass everything above.
        if name != "back.svg" and not re.search(r"<(path|circle|ellipse|polygon)\b", raw):
            no_geometry.append(name)

    c(not bad_xml, "every card is well-formed XML%s"
          % ("" if not bad_xml else " — %s" % "; ".join(bad_xml[:3])))
    c(not wrong_box, "every card uses the 180x252 viewBox%s"
          % ("" if not wrong_box else " — %s" % ", ".join(wrong_box[:5])))
    c(not glyph_suits,
          "no card draws a suit as a Unicode text glyph (the old font-dependency bug)%s"
          % ("" if not glyph_suits else " — %s" % ", ".join(glyph_suits[:5])))
    c(not external, "no card references artwork outside itself%s"
          % ("" if not external else " — %s" % "; ".join(external[:3])))
    c(not no_geometry, "every card carries actual drawn geometry%s"
          % ("" if not no_geometry else " — %s" % ", ".join(no_geometry[:5])))

    # The club is the shape that was previously wrong (it had no top lobe). Its three
    # lobes are drawn as literal circles precisely so this is checkable.
    with open(os.path.join(cards_dir, "AC.svg"), encoding="utf-8") as fh:
        ac = fh.read()
    circles = len(re.findall(r"<circle\b", ac))
    c(circles >= 3, "the club is built from at least 3 circles, so its lobes "
                        "cannot be wrong (found %d)" % circles)

    # Ranks are still text, and that is fine — assert it stays ASCII-only.
    non_ascii_text = []
    for name in sorted(expected & present):
        root = ET.parse(os.path.join(cards_dir, name)).getroot()
        for t in root.iter("{http://www.w3.org/2000/svg}text"):
            if t.text and any(ord(ch) > 127 for ch in t.text):
                non_ascii_text.append("%s (%r)" % (name, t.text))
    c(not non_ascii_text, "all card text is ASCII, so any fallback font renders it%s"
          % ("" if not non_ascii_text else " — %s" % "; ".join(non_ascii_text[:3])))


for deck_name, required in DECKS:
    path = os.path.join(REPO, "static", "img", deck_name)
    if not os.path.isdir(path):
        if required:
            check(False, "[%s] deck directory exists" % deck_name)
        else:
            print("SKIP [%s] not generated (optional deck)" % deck_name)
        continue
    audit(deck_name)

print("\n%d/%d card-asset checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
