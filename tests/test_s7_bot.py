import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""The Super Seven computer player: what it may see, what it throws, when it stops.

Three things are pinned here.

**It cannot see opponents' cards.** The bot used to read ``player.hand`` for
every opponent when deciding whether to call Stop, so it only ever called a Stop
it already knew it would win — information no human at the table has. The test
is behavioural rather than a code inspection: the same position is decided twice
with opponents holding wildly different cards *of the same count*, and the two
decisions must match. Card counts are public, so they are held equal; faces are
not, so they are made as different as possible.

**It scores every legal throw together.** The old chooser walked a fixed
Set > Sequence > Match > Pair > Single ladder and compared only within a tier, so
three 2s (shedding 6) beat a 5-6-7 run (shedding 18).

**Stop is judged relatively, not against a fixed total.** "Is 14 a low hand?" has
no answer without knowing what the opposition holds. The old rule required a
total <= 8, which blocked the strongest play in the game: calling early, while
everyone still holds a full hand, so the whole table banks a large score at once.
"""
from collections import Counter
from itertools import combinations

from game.core.cards import Card
from game.core.states import STATE_IN_TURN
from game.super_seven import ai
from game.super_seven.room import Room
from game.super_seven.rules import infer_action
from game.super_seven.settings import DEFAULT_SETTINGS

results = []

_SUITS = ("S", "H", "D", "C")


def check(ok, msg, extra=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg + (("  " + str(extra)) if not ok and extra else ""))


def hand_of(*ranks):
    """Cards for the given ranks, every one with a distinct id."""
    out, seen = [], {}
    for rank in ranks:
        n = seen.get(rank, 0)
        seen[rank] = n + 1
        out.append(Card(rank, _SUITS[n % 4], n // 4))
    return out


def build_room(bot_hand, opponent_hands, center=(), discard=(),
               first_orbit=True, settings=None, bot_score=0, safe_opponents=False):
    cfg = dict(DEFAULT_SETTINGS)
    cfg.update(settings or {})
    room = Room("BOTS", "bot", cfg)
    room.register_player("bot", "Bot")
    room.players["bot"].hand = list(bot_hand)
    room.players["bot"].total_score = bot_score

    order = ["bot"]
    for i, cards in enumerate(opponent_hands):
        uid = "opp%d" % i
        room.register_player(uid, uid.upper())
        room.players[uid].hand = list(cards)
        room.players[uid].is_safe = safe_opponents
        order.append(uid)

    room.turn_order = order
    room.turn_index = 0          # the bot is on turn
    room.state = STATE_IN_TURN
    room.first_orbit_complete = first_orbit
    room.center_throw = list(center)
    room.discard_pile = list(discard)
    room.awaiting_draw = False
    return room


def summarise(move):
    """A comparable form of a decision, so two runs can be checked identical."""
    if move is None:
        return None
    out = {"action": move["action"]}
    if move["action"] == "play":
        out["action_type"] = move["action_type"]
        out["cards"] = sorted(c.id for c in move["cards"])
    return out


# ---- the bot sees public information only -----------------------------------
# Same position, same card counts, completely different faces. If any decision
# below reads an opponent's cards, the two runs diverge.

def twin_rooms(bot_hand, counts, **kw):
    low = [hand_of(*([1] * n)) for n in counts]     # opponents holding aces
    high = [hand_of(*([13] * n)) for n in counts]   # opponents holding kings
    return build_room(bot_hand, low, **kw), build_room(bot_hand, high, **kw)

# A position where the bot throws.
a, b = twin_rooms(hand_of(2, 2, 2, 5, 6, 7), [7, 3], first_orbit=False)
check(summarise(ai.decide_move(a, "bot")) == summarise(ai.decide_move(b, "bot")),
      "the throw is identical whether opponents hold aces or kings",
      (summarise(ai.decide_move(a, "bot")), summarise(ai.decide_move(b, "bot"))))

# A position where the bot calls Stop. This is the discriminating case: holding
# 14 against three players on seven aces (7 points each) is a losing call, and
# against three on seven kings (91 each) a winning one. A bot that peeks would
# answer differently; one on public information cannot tell them apart.
a, b = twin_rooms(hand_of(1, 4, 9), [7, 7, 7])
move_a, move_b = ai.decide_move(a, "bot"), ai.decide_move(b, "bot")
check(summarise(move_a) == summarise(move_b),
      "the Stop decision is identical whether opponents hold aces or kings",
      (summarise(move_a), summarise(move_b)))

obs = ai.observe(a, "bot")
check("Card(" not in repr(obs.opponents),
      "the observation carries no card objects for opponents", repr(obs.opponents))
check([o.card_count for o in obs.opponents] == [7, 7, 7],
      "it does carry their card counts, which are public")
check(len(obs.hand) == 3, "and the bot's own hand in full")


# ---- choosing a throw --------------------------------------------------------
# Every legal play is scored together rather than ranked by category.

room = build_room(hand_of(2, 2, 2, 5, 6, 7), [hand_of(*([7] * 7))], first_orbit=False)
move = ai.decide_move(room, "bot")
check(sorted(c.rank for c in move["cards"]) == [5, 6, 7],
      "a 5-6-7 run (sheds 18) is chosen over three 2s (sheds 6)",
      [c.id for c in move["cards"]])

# A free Match beats a no-draw Set worth fewer points.
room = build_room(hand_of(10, 10, 2, 2, 2), [hand_of(*([7] * 7))],
                  center=hand_of(10), first_orbit=False)
move = ai.decide_move(room, "bot")
check(sorted(c.rank for c in move["cards"]) == [10, 10],
      "two matching 10s (sheds 20, free) beat a set of 2s (sheds 6)",
      [c.id for c in move["cards"]])

# A no-draw combo beats discarding a high single, because the single draws back.
room = build_room(hand_of(13, 5, 6, 7), [hand_of(*([7] * 7))], first_orbit=False)
move = ai.decide_move(room, "bot")
check(move["action_type"] == "sequence",
      "a run is preferred over throwing the King, which owes a draw",
      move["action_type"])

# Emptying the hand scores a flat 0, so it beats even a Stop the bot would win.
# The confidence model says so on its own: playing on ends the round at 0 here,
# so the bar to gamble instead goes to 1.0 and can never be met.
room = build_room(hand_of(5, 6, 7), [hand_of(*([7] * 7))])
obs = ai.observe(room, "bot")
check(ai.stop_confidence_required(obs, ai.hand_total(obs.hand)) == 1.0,
      "with a go-out available, no Stop is ever worth gambling on")
move = ai.decide_move(room, "bot")
check(move["action"] == "play" and len(move["cards"]) == 3,
      "going out is taken instead of calling Stop", summarise(move))


# ---- calling Stop ------------------------------------------------------------
# The headline case: three cards worth 14 while everyone else still holds seven.
# The old rule refused this outright, because 14 > 8.

room = build_room(hand_of(1, 4, 9), [hand_of(*([7] * 7)) for _ in range(3)])
check(ai.decide_move(room, "bot")["action"] == "stop",
      "calls Stop early on 14 points while three opponents hold seven cards")

# Same hand, same opponents, but they have shed down to two cards each — the
# moment has passed and the identical total is now a bad call.
room = build_room(hand_of(1, 4, 9), [hand_of(*([7] * 2)) for _ in range(3)])
check(ai.decide_move(room, "bot")["action"] != "stop",
      "does not call the same 14 once opponents are down to two cards each")

# More opponents means more chances somebody is under us.
few = build_room(hand_of(3, 6, 9), [hand_of(*([7] * 5))])
many = build_room(hand_of(3, 6, 9), [hand_of(*([7] * 5)) for _ in range(5)])
check(ai.p_strictly_lowest(ai.observe(few, "bot"), 18)
      > ai.p_strictly_lowest(ai.observe(many, "bot"), 18),
      "confidence falls as the table gets bigger")

# Stop is illegal during the first orbit, however good the position looks.
room = build_room(hand_of(1, 4, 9), [hand_of(*([7] * 7)) for _ in range(3)],
                  first_orbit=False)
check(ai.decide_move(room, "bot")["action"] != "stop",
      "never calls Stop before the first orbit completes")

# Nobody left to contest: score_round() treats an uncontested call as a win.
room = build_room(hand_of(13, 12, 11), [hand_of(*([1] * 2))], safe_opponents=True)
check(ai.should_call_stop(ai.observe(room, "bot")),
      "calls Stop on any hand when every opponent is already safe")


# ---- the confidence bar: settings, and what playing on is worth --------------
# A lone card worth about an average draw has nothing to gain by playing on
# (throw it, draw one back, land in the same place), so the bar sits at the
# plain break-even penalty / (penalty + discount).
def bar_for(cards, opponent_counts=(2,), **kw):
    obs = ai.observe(build_room(cards, [hand_of(*([7] * n)) for n in opponent_counts], **kw), "bot")
    return ai.stop_confidence_required(obs, ai.hand_total(obs.hand))


check(abs(bar_for(hand_of(7)) - 40 / 45.0) < 0.02,
      "with nothing to gain by playing on, the bar is the plain ~0.89 break-even",
      bar_for(hand_of(7)))
check(bar_for(hand_of(1)) < bar_for(hand_of(7)) < bar_for(hand_of(13)),
      "the bar falls when playing on can only make the hand worse, and rises "
      "when it can improve it",
      (bar_for(hand_of(1)), bar_for(hand_of(7)), bar_for(hand_of(13))))
check(bar_for(hand_of(13)) == 1.0,
      "holding a lone King it never calls — throwing it and redrawing is better")

# A host who removes the penalty gets a bot that calls freely — a position it
# declines on the defaults becomes correct when being caught costs nothing.
args = (hand_of(7), [hand_of(*([7] * 2))])
check(ai.decide_move(build_room(*args), "bot")["action"] != "stop",
      "(precondition) this position is declined on the default penalty")
check(ai.decide_move(build_room(*args, settings={"stop_penalty": 0}), "bot")["action"] == "stop",
      "with stop_penalty=0 it calls the same position")


# ---- elimination awareness ---------------------------------------------------
# A position deliberately between the two bars: good enough to call normally
# (p ~0.96 against the 0.89 break-even) but not the near-certainty demanded when
# a caught call would end the game. A position the bot is *sure* of stays a call
# at any score, which is correct — the guard raises the bar, it is not a veto.
GOOD_NOT_CERTAIN = (hand_of(1, 4, 6), [hand_of(*([7] * 4))])

room = build_room(*GOOD_NOT_CERTAIN)
check(ai.decide_move(room, "bot")["action"] == "stop",
      "(precondition) this call is worth making at a safe score")

# 60 + 11 + 40 crosses max_score, so being caught here is not a bad round but
# the end of the game, and near-certainty is demanded instead.
room = build_room(*GOOD_NOT_CERTAIN, bot_score=60)
check(ai.decide_move(room, "bot")["action"] != "stop",
      "declines the same call when being caught would eliminate it")

# But once even a *winning* call takes it over the cap there is nothing left to
# protect, so it plays the odds again rather than stalling.
room = build_room(*GOOD_NOT_CERTAIN, bot_score=95)
check(ai.decide_move(room, "bot")["action"] == "stop",
      "gambles again once even a winning call would eliminate it")


# ---- a safe bot has nothing to decide ----------------------------------------
room = build_room([], [hand_of(*([7] * 7))])
room.players["bot"].is_safe = True
check(ai.decide_move(room, "bot") is None, "a safe bot makes no move")


# ---- every legal throw is actually generated ---------------------------------
# "All possible throw options" taken literally: brute-force every subset of the
# hand, keep the ones infer_action calls legal, and require the generator to
# have offered each of them. Which physical copy of a rank gets used does not
# matter, so both sides are compared as rank multisets.

def legal_rank_sets(hand, center):
    out = set()
    for size in range(1, len(hand) + 1):
        for combo in combinations(hand, size):
            if infer_action([c.rank for c in combo], center) is not None:
                out.add(tuple(sorted(c.rank for c in combo)))
    return out


for label, cards, center in (
    ("sets, runs and singles", hand_of(2, 2, 2, 5, 6, 7), frozenset()),
    ("a long run with sub-runs", hand_of(4, 5, 6, 7, 8), frozenset()),
    ("matches off a two-rank centre", hand_of(9, 9, 10, 10, 3), frozenset({9, 10})),
):
    offered = {tuple(sorted(c.rank for c in play)) for play, _ in ai._candidate_plays(cards, center)}
    check(offered == legal_rank_sets(cards, center),
          "every legal throw is generated — %s" % label,
          sorted(legal_rank_sets(cards, center) - offered))


# ---- thinking a turn ahead ---------------------------------------------------
# The reported case: QQ alongside a small run. Shedding 24 points and drawing an
# unknown card back beats a free run that sheds only 6 and leaves the Queens.
room = build_room(hand_of(12, 12, 1, 2, 3), [hand_of(*([7] * 7))], first_orbit=False)
move = ai.decide_move(room, "bot")
check(sorted(c.rank for c in move["cards"]) == [12, 12],
      "throws QQ (sheds 24, owes a draw) rather than the free A-2-3 (sheds 6)",
      [c.rank for c in move["cards"]])

# Both plays here are free and both leave a ready-to-go-out hand, so the exit is
# a wash and the cheaper leftover decides it: keep 2-2-2 (6), not 5-6-7 (18).
room = build_room(hand_of(2, 2, 2, 5, 6, 7), [hand_of(*([7] * 7))], first_orbit=False)
move = ai.decide_move(room, "bot")
check(sorted(c.rank for c in move["cards"]) == [5, 6, 7],
      "between two equal exits it keeps the cheaper hand")

# But an exit is not worth paying a big free shed for: dumping 5-6-7 for nothing
# beats throwing the King to preserve a run, even though it leaves a lone card.
room = build_room(hand_of(13, 5, 6, 7), [hand_of(*([7] * 7))], first_orbit=False)
move = ai.decide_move(room, "bot")
check(sorted(c.rank for c in move["cards"]) == [5, 6, 7],
      "does not trade a large free shed for keeping an exit")

# Exit status, which the above all rest on.
check(ai._exit_status(hand_of(5, 6, 7)) == 2, "a run is ready to go out")
check(ai._exit_status(hand_of(4, 4, 4)) == 2, "so is a set")
check(ai._exit_status(hand_of(5, 6)) == 1, "two of a run are one card away")
check(ai._exit_status(hand_of(2, 9)) == 0, "unrelated cards have no exit")
check(ai._exit_status(hand_of(13)) == 0,
      "a lone card has none either — a single always draws one back")


# ---- it knows what it hands the next player ----------------------------------
# Same throw, different neighbour: gifting matters more when the next player is
# holding more cards, because they are likelier to hold the ranks we put down.
small = ai.observe(build_room(hand_of(12, 12, 1, 2, 3), [hand_of(*([7] * 1))]), "bot")
large = ai.observe(build_room(hand_of(12, 12, 1, 2, 3), [hand_of(*([7] * 7))]), "bot")
queens = hand_of(12, 12)
counts_s, counts_l = Counter(small.unseen), Counter(large.unseen)
check(ai._gift_cost(queens, large, counts_l, len(large.unseen))
      > ai._gift_cost(queens, small, counts_s, len(small.unseen)),
      "throwing into a full-handed neighbour costs more than into a near-empty one")
check(ai._gift_cost(queens, ai.observe(build_room(hand_of(12, 12, 1, 2, 3), []), "bot"),
                    counts_l, len(large.unseen)) == 0.0,
      "with nobody left to play after us, gifting costs nothing")


# ---- a very low hand is called, however few cards it is spread across --------
# Reported from play: holding a low total against an opponent already down to
# three cards, the bot threw instead of calling. The cause was the opponent
# model shifting its mean down while keeping the full spread, which left far too
# much probability at the bottom of the range — so a three-card opponent was
# credited with roughly a 12% chance of being under 7 points when the real
# figure is nearer 2%. Worse, the bot grew *less* willing as its own hand got
# smaller, which is backwards: the same points in fewer cards is a better hand.
for cards, label in ((hand_of(1, 2, 4), "three cards"),
                     (hand_of(3, 4), "two cards"),
                     (hand_of(7), "one card")):
    room = build_room(cards, [hand_of(*([7] * 3))])
    check(ai.decide_move(room, "bot")["action"] == "stop",
          "calls Stop on 7 points held as %s, against an opponent on three" % label)

# The mirror image, which must not become a false positive: the same three-card
# opponent while *we* are the one holding a full hand is not a Stop at all.
room = build_room(hand_of(2, 3, 4, 5, 6, 8, 9), [hand_of(*([7] * 3))])
check(ai.decide_move(room, "bot")["action"] != "stop",
      "does not call while holding seven cards against an opponent on three")


# ---- down to one or two cards, where playing on cannot help ------------------
# Reported from play: the bot was passing up Stops on tiny hands. The bar used
# to be a flat ~0.89 regardless, which quietly assumed declining was free — true
# holding six cards with plenty left to shed, false holding one, where the only
# legal play is to throw it and draw an unknown card back.

# One card against an opponent on two: call while the card is below an average
# draw, decline once it is above, because then throwing it is the better move.
for value, expected in ((1, "stop"), (3, "stop"), (5, "stop"),
                        (9, "play"), (11, "play"), (13, "play")):
    room = build_room(hand_of(value), [hand_of(*([7] * 2))])
    check(ai.decide_move(room, "bot")["action"] == expected,
          "one card worth %d against an opponent on two -> %s" % (value, expected))

# Two cards against an opponent on three, same shape.
for cards, expected in ((hand_of(1, 2), "stop"), (hand_of(2, 5), "stop"),
                        (hand_of(6, 8), "play")):
    room = build_room(cards, [hand_of(*([7] * 3))])
    check(ai.decide_move(room, "bot")["action"] == expected,
          "two cards worth %d against an opponent on three -> %s"
          % (ai.hand_total(cards), expected))

# The bar has to move with the hand, not sit at a constant.
check(len({round(bar_for(hand_of(v)), 4) for v in (1, 3, 5, 7, 9, 11, 13)}) == 7,
      "the confidence bar is derived per position, not a fixed threshold")


print("\n%d/%d bot AI checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
