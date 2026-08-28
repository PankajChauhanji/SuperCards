import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""The "adding a game is just a registration" claim, made executable.

PLATFORM_PLAN.md promises that a new variant needs only a Room class, a settings
module and a table bundle — no shared-code surgery. Nothing checked that, so a
half-registered game failed silently and in a different place each time: a
missing rules file 404s only when someone opens the modal, a missing presenter
dealer means the round deals but nobody receives cards, and a game absent from
the picker simply never appears with no error at all.

This file *is* that checklist. It loops over every registered game_type and
asserts the whole contract, so an incomplete game #4 fails here — once, loudly,
with the exact missing piece named — instead of in production.

Registering the variant modules is what populates the presenter / director /
audience registries, so importing sockets.gameplay is part of the setup.
"""
import re

from game.core import registry
from game.core.room_base import RoomProtocol
from sockets import audience, director, presenter
import sockets.gameplay  # noqa: F401  — import side effect: registers all variants

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULE_LANGS = ("en", "hi")
TEMPLATE_PARTS = ("branding.html", "table.html", "scripts.html")

results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


games = registry.all_games()
check(bool(games), "the registry has at least one game")
print("registered: %s\n" % ", ".join(sorted(games)))

for key in sorted(games):
    spec = games[key]
    tag = "[%s]" % key

    # ---- spec sanity ----
    check(spec.key == key, "%s spec.key matches its registry key" % tag)
    check(bool(spec.display_name), "%s has a display_name for the picker" % tag)
    check(isinstance(spec.ready, bool), "%s declares readiness on the spec" % tag)
    check(2 <= spec.min_players <= spec.max_players,
          "%s player bounds are sane (%s..%s)" % (tag, spec.min_players, spec.max_players))

    # ---- Room contract ----
    # round_end_payload only applies to games that score discrete rounds; Bluff
    # is a single race and never enters STATE_ROUND_END, so requiring it there
    # would mean adding dead code to satisfy a checklist.
    conditional = set() if spec.has_rounds else {"round_end_payload"}
    room_cls = spec.room_class
    missing = [
        name for name in dir(RoomProtocol)
        if not name.startswith("_")
        and name not in conditional
        and callable(getattr(RoomProtocol, name, None))
        and not hasattr(room_cls, name)
    ]
    check(not missing, "%s Room implements the full RoomProtocol%s"
          % (tag, "" if not missing else " (missing: %s)" % ", ".join(sorted(missing))))

    # And the flag must not be a get-out-of-jail card: a game that claims rounds
    # has to actually provide the payload the shared lobby will ask it for.
    if spec.has_rounds:
        check(hasattr(room_cls, "round_end_payload"),
              "%s declares has_rounds and provides round_end_payload" % tag)
    else:
        check(not hasattr(room_cls, "round_end_payload"),
              "%s declares no rounds and indeed has no round_end_payload" % tag)

    # ---- settings / bounds parity ----
    # A default with no bound cannot be validated when a host edits it; a bound
    # with no default is a lobby field that renders empty.
    defaults = set(spec.default_settings)
    bounds = set(spec.settings_bounds)
    unbounded = sorted(defaults - bounds)
    orphaned = sorted(bounds - defaults)
    check(not unbounded, "%s every default setting has bounds%s"
          % (tag, "" if not unbounded else " (unbounded: %s)" % ", ".join(unbounded)))
    check(not orphaned, "%s every bound has a default%s"
          % (tag, "" if not orphaned else " (no default: %s)" % ", ".join(orphaned)))

    bad_bounds = []
    for name, bound in spec.settings_bounds.items():
        default = spec.default_settings.get(name)
        try:
            low, high = bound[0], bound[1]
        except (TypeError, IndexError, KeyError):
            bad_bounds.append("%s: unreadable bound %r" % (name, bound))
            continue
        if isinstance(default, bool) or not isinstance(default, (int, float)):
            continue
        if not (low <= default <= high):
            bad_bounds.append("%s: default %r outside [%r, %r]" % (name, default, low, high))
    check(not bad_bounds, "%s every default sits inside its own bounds%s"
          % (tag, "" if not bad_bounds else " (%s)" % "; ".join(bad_bounds)))

    # ---- shared-layer hooks ----
    check(key in presenter._DEALERS,
          "%s registers a presenter dealer (or the deal reaches nobody)" % tag)
    check(key in director._TICKERS,
          "%s registers a director ticker (or turns never time out)" % tag)
    # Without this the shared reconnect path has nothing to call, and a player
    # who drops mid-game comes back to a table that never repaints — the exact
    # failure that went unnoticed in Super 4, because the lobby used to fall back
    # to Super Seven's event names for every game.
    check(key in presenter._RESYNCERS,
          "%s registers a resync hook (or reconnecting shows a stale table)" % tag)
    check(key in audience._ORACLES,
          "%s registers a visibility oracle (or the leak guard is blind)" % tag)

    # ---- client assets ----
    for part in TEMPLATE_PARTS:
        path = os.path.join(REPO, "templates", "games", key, part)
        check(os.path.isfile(path), "%s templates/games/%s/%s exists" % (tag, key, part))

    for lang in RULE_LANGS:
        path = os.path.join(REPO, "static", "rules", key, "%s.html" % lang)
        check(os.path.isfile(path), "%s static/rules/%s/%s.html exists" % (tag, key, lang))

    # The JS bundle directory is not named after the game_type (super_seven ->
    # seven), so resolve it the way the browser does: through scripts.html.
    scripts = os.path.join(REPO, "templates", "games", key, "scripts.html")
    if os.path.isfile(scripts):
        with open(scripts, encoding="utf-8") as fh:
            markup = fh.read()
        refs = re.findall(r"filename=['\"]([^'\"]+\.js)['\"]", markup)
        refs += re.findall(r"src=['\"]/static/([^'\"]+\.js)['\"]", markup)
        check(bool(refs), "%s scripts.html references at least one JS bundle" % tag)
        broken = [r for r in refs if not os.path.isfile(os.path.join(REPO, "static", r))]
        check(not broken, "%s every JS file scripts.html loads exists%s"
              % (tag, "" if not broken else " (missing: %s)" % ", ".join(broken)))

print("\n%d/%d platform-contract checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
