import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Every number stated in the docs must still be the number in the code.

Super 4's tunables live in one place (game/super_four/settings.py) but are
restated in prose in four others: the English rules, the Hindi rules, and
DESIGN.md. Four copies of one fact, kept in step by memory — and they had
already drifted once (DESIGN.md simultaneously described exit_score elimination
and claimed "no cumulative elimination cap in v1").

Prose is the right format for a rules page, so the fix is not to generate a
table and make the page worse; it is to make the duplication *checked*. Each
claim below pins a documented number to its registry default.

Two ways this fails, both intended:
  * a default changed and a doc was not updated  -> the number mismatches;
  * a doc was reworded so the anchor no longer matches -> the claim is reported
    as unmatched, and this table is what needs updating.

Anchors are kept short and structural so ordinary copy-editing does not trip
them. This is the convention the settings.py docstrings ask for, made executable.
"""
import re

from game.core import registry

# (game_type, path, setting_key, regex with exactly one capture group)
# The captured text is normalised (unicode minus, leading +) before comparison.
CLAIMS = [
    # ---- Super 4, English rules ----
    ("super_four", "static/rules/super_four/en.html", "preview_seconds",
     r"maximum of <strong>(\d+) seconds"),
    ("super_four", "static/rules/super_four/en.html", "match_window",
     r"up to (\d+) seconds"),
    ("super_four", "static/rules/super_four/en.html", "rounds",
     r"A game is <strong>(\d+) rounds"),
    ("super_four", "static/rules/super_four/en.html", "win_score",
     r"hand</strong> → <strong>(−?\d+)</strong>"),
    ("super_four", "static/rules/super_four/en.html", "stop_loss_score",
     r"everyone else takes \+(\d+)"),
    ("super_four", "static/rules/super_four/en.html", "penalty_score",
     r"<strong>\+(\d+) penalty"),
    ("super_four", "static/rules/super_four/en.html", "exit_score",
     r"exit score \((\d+)\)"),

    # ---- Super 4, Hindi rules (same numbers, different prose) ----
    ("super_four", "static/rules/super_four/hi.html", "match_window",
     r"अधिकतम (\d+)"),
    ("super_four", "static/rules/super_four/hi.html", "rounds",
     r"खेल <strong>(\d+) राउंड"),
    ("super_four", "static/rules/super_four/hi.html", "stop_loss_score",
     r"बाकी सबको \+(\d+)</strong>"),
    ("super_four", "static/rules/super_four/hi.html", "penalty_score",
     r"<strong>\+(\d+) पेनल्टी"),
    ("super_four", "static/rules/super_four/hi.html", "exit_score",
     r"स्कोर \((\d+)\)"),
    ("super_four", "static/rules/super_four/hi.html", "timeout_limit",
     r"<strong>(\d+) बार</strong>"),

    # ---- Super 4, DESIGN.md ----
    ("super_four", "game/super_four/DESIGN.md", "win_score",
     r"`win_score` \(default \*\*(−?-?\d+)\*\*\)"),
    ("super_four", "game/super_four/DESIGN.md", "stop_loss_score",
     r"`stop_loss_score` \(default \*\*\+?(\d+)\*\*\)"),
    ("super_four", "game/super_four/DESIGN.md", "penalty_score",
     r"`penalty_score` \(default \*\*\+?(\d+)\*\*\)"),
    ("super_four", "game/super_four/DESIGN.md", "loss_score",
     r"`loss_score` \(default \*\*\+?(\d+)\*\*\)"),
    ("super_four", "game/super_four/DESIGN.md", "exit_score",
     r"`exit_score` \(default \*\*(\d+)\*\*\)"),
    ("super_four", "game/super_four/DESIGN.md", "rounds",
     r"`rounds` rounds \(default \*\*(\d+)\*\*\)"),

    # ---- Super Seven / Bluff table limits quoted in DESIGN-style prose ----
    ("super_four", "game/super_four/DESIGN.md", "turn_timer",
     r"turn_timer=(\d+)s"),
]

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def normalise(text):
    """'−1' / '-1' / '+2' / '2' all reduce to a comparable int."""
    text = text.strip().replace("−", "-").replace("+", "")
    return int(text)


_cache = {}


def read(rel):
    if rel not in _cache:
        with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
            _cache[rel] = fh.read()
    return _cache[rel]


for game_type, rel, key, pattern in CLAIMS:
    spec = registry.get(game_type)
    expected = spec.default_settings.get(key)
    label = "%s: %s = %r" % (rel.split("/")[-1], key, expected)

    if expected is None:
        check(False, "%s — no such setting in %s defaults (stale claim)" % (label, game_type))
        continue

    path = os.path.join(REPO, rel)
    if not os.path.isfile(path):
        check(False, "%s — %s is missing" % (label, rel))
        continue

    found = re.search(pattern, read(rel))
    if not found:
        check(False, "%s — the doc no longer matches its anchor %r; reword the "
                     "claim in tests/test_settings_docs.py" % (label, pattern))
        continue

    try:
        documented = normalise(found.group(1))
    except ValueError:
        check(False, "%s — captured %r is not a number" % (label, found.group(1)))
        continue

    check(documented == expected,
          "%s — doc says %s%s" % (label, documented,
                                  "" if documented == expected else " (DRIFT)"))

# Guard the guard: a claim table that silently covers nothing is worthless.
covered = {(g, k) for g, _, k, _ in CLAIMS}
s4_numeric = {
    k for k, v in registry.get("super_four").default_settings.items()
    if isinstance(v, int) and not isinstance(v, bool)
}
documented_keys = {k for g, k in covered if g == "super_four"}
undocumented = sorted(s4_numeric - documented_keys)
# num_decks and preview/loss variants may legitimately not appear in every doc;
# report rather than fail, so the list stays informative instead of noisy.
if undocumented:
    print("\nnote: Super 4 settings not pinned to any doc: %s" % ", ".join(undocumented))

check(len(CLAIMS) >= 15, "the claim table is non-trivial (%d claims)" % len(CLAIMS))

print("\n%d/%d settings-doc checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
