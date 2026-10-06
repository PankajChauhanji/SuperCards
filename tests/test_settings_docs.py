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

    # ---- Poker, docs/poker_rules.md (the settings table) ----
    ("poker", "docs/poker_rules.md", "starting_chips",
     r"\| \*\*Starting coins\*\* \| \*\*([\d,]+)\*\*"),
    ("poker", "docs/poker_rules.md", "rounds",
     r"\| \*\*Rounds\*\* \| \*\*(\d+)\*\*"),
    ("poker", "docs/poker_rules.md", "turn_timer",
     r"\| \*\*Turn timer\*\* \| \*\*(\d+) s\*\*"),
    ("poker", "docs/poker_rules.md", "timeout_limit",
     r"\| \*\*Timeout limit\*\* \| \*\*(\d+)\*\*"),
    ("poker", "docs/poker_rules.md", "blind_up_every",
     r"\| \*\*Blinds double every\*\* \| \*\*(\d+)\*\*"),

    # ---- Poker, English rules ----
    ("poker", "static/rules/poker/en.html", "starting_chips",
     r"starting coins</b> \(default <strong>([\d,]+)</strong>"),
    ("poker", "static/rules/poker/en.html", "rounds",
     r"default <strong>(\d+) rounds</strong>"),
    ("poker", "static/rules/poker/en.html", "turn_timer",
     r"You have <strong>(\d+) seconds</strong> per turn"),
    ("poker", "static/rules/poker/en.html", "timeout_limit",
     r"Miss <strong>(\d+) turns</strong>"),

    # ---- Poker, Hindi rules ----
    ("poker", "static/rules/poker/hi.html", "rounds",
     r"<strong>(\d+) राउंड</strong>"),
    ("poker", "static/rules/poker/hi.html", "turn_timer",
     r"हर चाल के लिए <strong>(\d+) सेकंड</strong>"),
    ("poker", "static/rules/poker/hi.html", "timeout_limit",
     r"लगातार <strong>(\d+) बार</strong>"),
]

# Some documented numbers are rule constants rather than host-selectable
# settings, so they live on the variant's settings *module* instead of in its
# DEFAULT_SETTINGS. They restate into prose exactly the same way and drift
# exactly the same way, so they are checked the same way.
# (import path, attribute, doc path, regex with one capture group)
CONSTANT_CLAIMS = [
    ("game.bluff.settings", "PODIUM_PLACES", "static/rules/bluff/en.html",
     r"<b>(\d+) players have finished</b>"),
    ("game.bluff.settings", "PODIUM_PLACES", "static/rules/bluff/hi.html",
     r"<b>(\d+) खिलाड़ी खत्म कर लें</b>"),
    ("game.bluff.settings", "PODIUM_PLACES", "docs/bluff_rules.md",
     r"\*\*(\d+) players have finished\*\*"),

    # ---- Poker: table size and the round-summary auto-start ----
    ("game.poker.settings", "MAX_PLAYERS", "docs/poker_rules.md",
     r"\*\*Players:\*\* 2 to \*\*(\d+)\*\*"),
    ("game.poker.settings", "MAX_PLAYERS", "static/rules/poker/en.html",
     r"<b>2 to (\d+) players</b>"),
    ("game.poker.settings", "MAX_PLAYERS", "static/rules/poker/hi.html",
     r"<b>2 से (\d+) खिलाड़ी</b>"),
    ("game.poker.settings", "ROUND_END_SECONDS", "docs/poker_rules.md",
     r"automatically after \*\*(\d+) seconds\*\*"),
    ("game.poker.settings", "ROUND_END_SECONDS", "static/rules/poker/en.html",
     r"by itself after <strong>(\d+) seconds</strong>"),
    ("game.poker.settings", "ROUND_END_SECONDS", "static/rules/poker/hi.html",
     r"वह <strong>(\d+) सेकंड</strong> बाद"),
]

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def normalise(text):
    """'−1' / '-1' / '+2' / '2' / '1,000,000' all reduce to a comparable int."""
    text = text.strip().replace("−", "-").replace("+", "").replace(",", "")
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

for module_path, attr, rel, pattern in CONSTANT_CLAIMS:
    import importlib
    module = importlib.import_module(module_path)
    expected = getattr(module, attr, None)
    label = "%s: %s = %r" % (rel.split("/")[-1], attr, expected)

    if expected is None:
        check(False, "%s — %s has no %s (stale claim)" % (label, module_path, attr))
        continue
    if not os.path.isfile(os.path.join(REPO, rel)):
        check(False, "%s — %s is missing" % (label, rel))
        continue

    found = re.search(pattern, read(rel))
    if not found:
        check(False, "%s — the doc no longer matches its anchor %r; reword the "
                     "claim in tests/test_settings_docs.py" % (label, pattern))
        continue

    documented = normalise(found.group(1))
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
