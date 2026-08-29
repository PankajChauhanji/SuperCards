import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Table themes: registered everywhere, and their artwork actually parses.

A theme lives in four places at once — the catalogue in static/js/core/themes.js,
a button in templates/partials/theme_selector.html, its look in
static/css/themes.css, and a `--bloom` for the page behind it. Nothing fails
loudly when one is missed: the theme simply never appears in the picker, or
appears and does nothing, or renders with the previous theme's bloom still
washed behind it. Same shape as tests/test_platform_contract.py, one layer down.

The artwork is checked too, because the ornamented themes draw their dragons,
arcades and sunbursts as inline SVG data URIs. A malformed one is the worst kind
of bug: the browser reports nothing at all and simply paints empty space, so it
survives every check short of looking at it.
"""
import re
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "static/js/core/themes.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "static/css/themes.css"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "templates/partials/theme_selector.html"), encoding="utf-8").read()

results = []


def check(ok, msg, extra=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg + (("  " + str(extra)) if not ok and extra else ""))


# ---- the four registries -----------------------------------------------------
catalogue_block = JS.split("THEME_MAP = {", 1)[1].split("};", 1)[0]
catalogue = re.findall(r"(\w+):\s*\{\s*icon:", catalogue_block)
buttons = re.findall(r'data-t="([^"]+)"', HTML)
blooms = re.findall(r"body\.theme-([\w-]+)\s*\{\s*--bloom:", CSS)
styled = set(re.findall(r"body\.theme-([\w-]+)\b", CSS))

check(len(catalogue) >= 17, "the catalogue lists every theme", len(catalogue))
check(len(catalogue) == len(set(catalogue)), "no theme is registered twice")

for name in catalogue:
    check(name in buttons, "%s has a button in the picker" % name)
    check(name in blooms, "%s declares a --bloom for the page behind it" % name)
    check(name in styled, "%s has styling of its own" % name)

# ...and nothing is registered that the catalogue does not know about, which is
# the direction that leaves a dead button in the menu.
for name in set(buttons):
    check(name in catalogue, "the picker's %r button is a real theme" % name)
for name in set(blooms):
    check(name in catalogue, "the %r bloom belongs to a real theme" % name)


# ---- the artwork -------------------------------------------------------------
uris = re.findall(r'url\("(data:image/svg\+xml,[^"]+)"\)', CSS)
check(len(uris) >= 18, "the ornamented themes ship their motifs as SVG", len(uris))

bad_xml, external = [], []
for uri in uris:
    markup = urllib.parse.unquote(uri.split(",", 1)[1])
    try:
        ET.fromstring(markup)
    except ET.ParseError as exc:
        bad_xml.append(str(exc))
    # A theme that reaches off-origin would be blocked or slow; everything must
    # be self-contained geometry. The SVG namespace declaration is a URI but
    # never a fetch, so it does not count.
    body = re.sub(r"xmlns(:\w+)?='[^']*'", "", markup)
    if "http" in body or "href" in body:
        external.append(body[:60])

check(not bad_xml, "every SVG motif is well-formed XML", bad_xml[:2])
check(not external, "no motif reaches for an external resource", external[:2])

# The point of drawing them: geometry, not glyphs. docs/todos.md §15 recorded
# what a font dependency cost the card deck — suits that rendered as tofu boxes
# on any machine without the right font. A dragon has no dependable glyph at
# all, so the motifs must be paths and shapes.
shapes = sum(1 for u in uris
             if re.search(r"<(path|circle|rect|polygon|ellipse)", urllib.parse.unquote(u)))
check(shapes == len(uris), "every motif is drawn from real geometry",
      "%d of %d" % (shapes, len(uris)))
check(not any(re.search(r"<text", urllib.parse.unquote(u)) for u in uris),
      "and none of them falls back to a text glyph")

# Non-ASCII inside a data URI would depend on the page's encoding surviving.
non_ascii = [u[:50] for u in uris if not urllib.parse.unquote(u).isascii()]
check(not non_ascii, "motif markup stays ASCII", non_ascii[:2])


# ---- the stylesheet still parses ---------------------------------------------
# Appending prose after a closing delimiter makes the parser discard the whole
# following rule, silently. docs/todos.md §14b lost .seat-plate that way, twice.
check(CSS.count("/*") == CSS.count("*/"),
      "comment delimiters balance", (CSS.count("/*"), CSS.count("*/")))
stripped = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
check(stripped.count("{") == stripped.count("}"),
      "braces balance once comments are stripped",
      (stripped.count("{"), stripped.count("}")))


print("\n%d/%d theme checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
