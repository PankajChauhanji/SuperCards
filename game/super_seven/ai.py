"""AI move logic for the computer player.

Called from the bot-turn branch of sockets/gameplay/super_seven.py whenever a bot
holds the turn. A host can seat several bots alongside real people
(game/core/bots.py), so this runs in group games as well as solo ones. It is
stateless — every decision is derived from (room, bot_id) — which is what lets
several bots share it at one table without interfering.

Public information only
-----------------------
The bot used to read ``player.hand`` for every opponent when deciding whether to
call Stop, so it only ever called a Stop it already knew it would win. That is
information no human at the table has, and the project guards it everywhere else
(sockets/audience.py, tests/test_leak_fuzz.py) — but those guard the *socket*
layer, and a bot reading the room object walks straight past them.

The fix is structural rather than a promise: ``observe()`` is the only function
here that touches ``room``, and it returns an Observation carrying just what a
human sees — own hand, opponents' *card counts*, who is safe, cumulative scores,
the centre, every card thrown so far (all of which are broadcast to the whole
room already), and the deck size. Every strategy function below takes that
Observation. The bot cannot peek because it is never handed the data.

tests/test_s7_bot.py enforces it from the outside: opponents' hands are replaced
with completely different cards of the same count, and the decision must not
change.

Choosing a throw
----------------
Every legal throw is generated — all sets, every contiguous sub-run, every
combination of matching cards, every pair and single — rather than picked off a
fixed Set > Sequence > Match > Pair > Single ladder. That ladder compared only
*within* a tier, so three 2s (shedding 6) beat a 5-6-7 run (shedding 18), and it
never even considered the plays that turn out to win on shape.

Each candidate is then scored on the position it leaves, not on the points it
sheds, because the cards left behind matter as much as the ones thrown:

  * points, which are what actually score against you;
  * a standing cost per card held — one more card to shed before going out, and
    one more to be caught holding;
  * exit potential. A hand that is already a Set or Sequence goes out next turn
    for a flat 0, so most of its face value never scores; a hand one card short
    is worth less but still real. This is a *discount on its points* rather than
    a fixed bonus — a flat bonus overvalues a cheap ready hand, and would trade
    away a big free shed just to keep one;
  * the card you draw back, charged at the average unseen card;
  * what you hand the next player. Whatever you throw becomes the centre and
    they can match off it for nothing, so dumping a pair of Queens also gives
    them a free exit for their own. Heavily discounted — it helps one opponent
    rather than costing you, so it breaks ties rather than driving decisions.

This is what makes the bot throw QQ while holding an A-2-3 run: shedding 24 and
drawing an unknown card back beats a free run that sheds only 6 and leaves the
Queens sitting in hand.

Emptying the hand outranks everything because it scores a flat 0 for the round —
and it is only reachable on a no-draw play (Set / Sequence / free Match), since
Single and Pair draw a card back. See game/super_seven/room.py apply_throw.

Calling Stop
------------
"Is 18 a low hand?" has no answer on its own: it is terrible against a player
holding two cards and excellent against one holding seven. The old rule tested
an absolute total (``<= 8``), which is why the bot could never make the strongest
play in the game — calling early, while everyone still holds a full hand, so the
whole table banks a large score at once.

So the total is judged against what opponents are *likely* holding, estimated
from their card counts and the cards still unseen:

  * the unseen pool is the deck minus our hand minus everything thrown, which
    gives card counting for free — as high cards get discarded the pool's mean
    falls and the estimates fall with it;
  * an opponent holding n cards is modelled as n cards drawn from the *cheap
    end* of that pool, since players shed their high cards and sit on the low
    ones. Mean and spread both come from that same slice, which matters: an
    earlier version shifted the mean down but kept the full spread, leaving far
    too much probability at the very bottom, and the bot passed up Stops it
    should have called;
  * the chance each opponent is at or under us comes from a normal
    approximation, and the survivals multiply — five opponents is a far harder
    table to call on than one;
  * the confidence needed is derived from the room's own settings rather than
    invented, so a host who lowers the penalty gets a looser bot for free.

Randomised delay (human-feel):
  The caller (director) waits BOT_THINK_MIN .. BOT_THINK_MAX seconds before
  acting, so the bot does not answer instantly.
"""
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product
from typing import List, Optional, Tuple

from game.core.cards import RANKS
from game.super_seven.settings import MATCH_REQUIRES_DRAW
from game.super_seven.rules import (
    infer_action,
    COMBO_ACTIONS,
    DRAW_ACTIONS,
    ACTION_SINGLE,
    ACTION_MATCH,
)

# ---- tunables ----------------------------------------------------------------
BOT_THINK_MIN = 1.5         # minimum seconds before bot acts
BOT_THINK_MAX = 3.0         # maximum seconds before bot acts

# Players throw their high cards and keep their low ones, so an opponent's hand
# is modelled as cards from the cheaper end of what is still unseen — the lowest
# this fraction of the pool. On a full deck that is ranks A-9, averaging exactly
# 5 a card, the cautious estimate this model was tuned to.
#
# Deliberately a *subset* rather than a flat shift of the average. Shifting the
# mean and keeping the full spread leaves a normal curve with far too much mass
# at the very bottom: it put a three-card hand under 7 points about 12% of the
# time when the true figure is nearer 2%, so the bot declined Stops it should
# have called. Taking mean and spread from the same subset keeps them
# consistent, and still counts cards — as low cards are discarded the cheap end
# of the pool moves up on its own.
OPPONENT_POOL_FRACTION = 0.7

# Confidence demanded when being caught would not merely score badly but push us
# over max_score and out of the game.
ELIMINATION_CONFIDENCE = 0.98

# Emptying the hand scores a flat 0 for the round, which no amount of shedding
# can match. Large enough to dominate the points terms outright.
SAFE_BONUS = 1000.0

# What a held card costs beyond its face value: it is one more card to shed
# before going out, and one more chance to be caught holding it. Set so that
# two cards worth 16 are preferred to three worth 15.
CARD_COST = 2.0

# A hand that is already a Set or a Sequence goes out next turn for a flat 0, so
# most of its face value never gets scored — but not all of it, because the
# round can end before the turn comes back round. These discount a hand's points
# rather than granting a fixed bonus, which matters: a flat bonus overvalues a
# cheap ready hand and would trade away a large free shed to keep one.
READY_RESIDUAL = 0.35       # points still expected from a ready-to-go-out hand
NEAR_RESIDUAL = 0.75        # ...and from one that is a single card short

# Whatever we throw becomes the centre, and the next player may dump every card
# of those ranks onto it for free. Heavily discounted rather than counted in
# full: those points help one opponent rather than costing us any, they only
# help at all if matching beat whatever they were going to play anyway, and it
# is a tiebreaker between comparable plays — not a reason to keep points.
GIFT_WEIGHT = 0.3
# -----------------------------------------------------------------------------


def bot_delay() -> float:
    """Return a random human-like pause in seconds."""
    return random.uniform(BOT_THINK_MIN, BOT_THINK_MAX)


# ---- observation: the only view of the game the strategy functions get -------

@dataclass(frozen=True)
class Opponent:
    """One other player, described only by what the table can see."""
    user_id: str
    card_count: int
    is_safe: bool
    total_score: int


@dataclass(frozen=True)
class Observation:
    """A public-information snapshot of the game from one bot's seat.

    Everything here is already broadcast to every client: card counts and safe
    flags ride in ``public_players()``, thrown cards in ``cards_played``, the
    centre and deck count in ``public_round_state()``. Nothing in this object
    identifies a card in anyone else's hand.
    """
    hand: Tuple                      # our own cards (Card objects)
    center_ranks: frozenset          # ranks showing in the centre, matchable
    opponents: Tuple[Opponent, ...]
    unseen: Tuple[int, ...]          # values of every card not yet seen anywhere
    next_player_cards: int           # cards held by whoever throws after us
    first_orbit_complete: bool
    am_i_safe: bool
    my_total_score: int
    max_score: int
    stop_penalty: int
    win_discount: int


def observe(room, bot_id: str) -> Observation:
    """Build the public-information view. The ONLY function here reading `room`.

    Opponents contribute ``len(p.hand)`` and nothing else — the count is public
    (it is in every ``public_view()``), the faces never are.
    """
    me = room.players[bot_id]

    # Cards we can account for: our own hand, the visible centre, and every
    # throw that has been buried since. All were broadcast when played.
    seen = defaultdict(int)
    for card in list(me.hand) + list(room.discard_pile) + list(room.center_throw):
        seen[card.rank] += 1

    num_decks = max(1, int(room.settings.get("num_decks", 1)))
    per_rank = 4 * num_decks
    unseen: List[int] = []
    for rank in RANKS:
        unseen.extend([rank] * max(0, per_rank - seen[rank]))

    # Who is actually in the round — the same set score_round() will use, so the
    # Stop estimate is judged against exactly the players who can catch us.
    opponents = tuple(
        Opponent(
            user_id=uid,
            card_count=len(room.players[uid].hand),
            is_safe=room.players[uid].is_safe,
            total_score=room.players[uid].total_score,
        )
        for uid in room.turn_order
        if uid != bot_id and uid in room.players
    )

    # Who throws after us — they are the one who can match off whatever we put
    # in the centre. Safe and eliminated players are skipped, the same way
    # room.advance_turn() skips them.
    next_player_cards = 0
    if bot_id in room.turn_order:
        order = room.turn_order
        start = order.index(bot_id)
        # Stops one short of a full lap, so a bot alone in the turn order never
        # wraps back to itself and starts costing gifts against its own hand.
        for step in range(1, len(order)):
            candidate = room.players.get(order[(start + step) % len(order)])
            if candidate and not candidate.is_safe and not candidate.eliminated:
                next_player_cards = len(candidate.hand)
                break

    settings = room.settings
    return Observation(
        hand=tuple(me.hand),
        center_ranks=frozenset(room.center_rank_set()),
        opponents=opponents,
        unseen=tuple(unseen),
        next_player_cards=next_player_cards,
        first_orbit_complete=room.first_orbit_complete,
        am_i_safe=me.is_safe,
        my_total_score=me.total_score,
        max_score=int(settings["max_score"]),
        stop_penalty=int(settings["stop_penalty"]),
        win_discount=int(settings["win_discount"]),
    )


# ---- estimating what the opposition is holding ------------------------------

def _pool_stats(unseen) -> Tuple[float, float]:
    """Mean and standard deviation of the unseen cards' values."""
    count = len(unseen)
    if count == 0:
        return 0.0, 0.0
    mean = sum(unseen) / float(count)
    variance = sum((v - mean) ** 2 for v in unseen) / float(count)
    return mean, math.sqrt(variance)


def _opponent_card_stats(unseen) -> Tuple[float, float]:
    """Mean and spread of one card an opponent is likely to be holding.

    Both are taken from the same slice of the unseen pool (see
    OPPONENT_POOL_FRACTION), so they stay consistent with one another — which a
    flat shift of the average did not, and that inconsistency was what made the
    bot decline Stops it should have called.
    """
    if not unseen:
        return 0.0, 1.0
    ordered = sorted(unseen)
    keep = max(1, int(len(ordered) * OPPONENT_POOL_FRACTION))
    cheap = ordered[:keep]
    mean = sum(cheap) / float(len(cheap))
    variance = sum((v - mean) ** 2 for v in cheap) / float(len(cheap))
    # A pool with no spread left would otherwise divide by zero.
    return mean, math.sqrt(variance) or 1.0


def _normal_cdf(z: float) -> float:
    """P(Z <= z) for a standard normal, via the error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def hand_total(cards) -> int:
    """Sum of card values in a hand."""
    return sum(c.value for c in cards)


def p_strictly_lowest(obs: Observation, my_total: int) -> float:
    """Estimated chance our total beats every contesting opponent's.

    Safe players are skipped because score_round() ignores them when deciding
    whether a call was caught — they are out of the Stop race for the round.
    """
    per_card, per_card_sd = _opponent_card_stats(obs.unseen)
    probability = 1.0
    for opponent in obs.opponents:
        if opponent.is_safe or opponent.card_count <= 0:
            continue
        mean = opponent.card_count * per_card
        spread = per_card_sd * math.sqrt(opponent.card_count)
        # Being *caught* is any opponent total <= ours, so ties count against
        # us; the half-point shifts the continuity correction the same way.
        beats_us = _normal_cdf((my_total + 0.5 - mean) / spread)
        probability *= max(0.0, 1.0 - beats_us)
    return probability


def expected_total_after_play(obs: Observation) -> float:
    """What our hand is likely to total once we have taken this turn instead.

    This is what makes "should I call?" answerable, because the alternative to
    calling is not standing still — it is playing on. With six cards there is
    plenty left to shed, so waiting is cheap. With one or two there is nothing
    to improve: the only legal play is to throw and draw an unknown card back,
    which on average lands us right back where we started, or worse.
    """
    cards, action = best_play(obs)
    thrown = set(map(id, cards))
    total = hand_total([c for c in obs.hand if id(c) not in thrown])
    if _owes_draw(action):
        pool_mean, _ = _pool_stats(obs.unseen)
        total += pool_mean
    return total


def stop_confidence_required(obs: Observation, my_total: int) -> float:
    """How sure the bot must be before calling, derived from the room settings.

    Winning a call saves ``win_discount``; being caught costs ``stop_penalty``;
    and declining leaves us with whatever playing on is worth. Setting those
    equal gives

        p  =  (stop_penalty - drift) / (stop_penalty + win_discount)

    where ``drift`` is how much our total is expected to move by playing on
    instead. With drift zero this is the plain penalty/(penalty + discount) —
    about 0.89 on the defaults. A hand that can still be improved pushes the bar
    up, because waiting genuinely costs nothing; a hand that can only churn
    pushes it down, which is the case the bot used to get wrong. It adapts to
    the host's settings too, which a fixed constant cannot.
    """
    penalty = max(0, obs.stop_penalty)
    discount = max(0, obs.win_discount)
    if penalty + discount:
        drift = expected_total_after_play(obs) - my_total
        base = (penalty - drift) / float(penalty + discount)
        base = min(1.0, max(0.0, base))
    else:
        base = 0.0

    # If even a *winning* call takes us over the cap, the game ends for us
    # either way and there is nothing left to protect — play the odds.
    if obs.my_total_score + max(my_total - discount, 0) >= obs.max_score:
        return base
    # Otherwise, when being caught would eliminate us, demand near-certainty:
    # that is not a bad round, it is the end of the game.
    if obs.my_total_score + my_total + penalty >= obs.max_score:
        return max(base, ELIMINATION_CONFIDENCE)
    return base


def should_call_stop(obs: Observation) -> bool:
    """Whether to call Stop right now, judged on public information alone."""
    if not obs.first_orbit_complete or obs.am_i_safe or not obs.hand:
        return False

    my_total = hand_total(obs.hand)
    contenders = [o for o in obs.opponents if not o.is_safe and o.card_count > 0]
    if not contenders:
        # Nobody can contest: score_round() treats an uncontested call as a win.
        return True
    return p_strictly_lowest(obs, my_total) >= stop_confidence_required(obs, my_total)


# ---- choosing a throw --------------------------------------------------------

def _owes_draw(action: str) -> bool:
    """Whether an action leaves the player owing a draw (see room.apply_throw)."""
    if action == ACTION_MATCH and not MATCH_REQUIRES_DRAW:
        return False
    return action in DRAW_ACTIONS


def _goes_safe(cards, action: str, hand_size: int) -> bool:
    """Whether this throw empties the hand and locks the round score at 0.

    Only a no-draw play can do it: Single and Pair draw a card straight back.
    """
    return not _owes_draw(action) and hand_size - len(cards) == 0


def _exit_status(cards) -> int:
    """How close a hand is to going out: 2 = right now, 1 = one card away, 0 = no.

    Only Sets and Sequences count. A Match could also empty a hand, but it needs
    the centre to still be showing the right ranks when our turn comes round
    again, and by then some other player has thrown — so it is not something the
    hand can be shaped toward.
    """
    if not cards:
        return 2
    ranks = [c.rank for c in cards]
    if infer_action(ranks, frozenset()) in COMBO_ACTIONS:
        return 2
    if len(cards) >= 2:
        for rank in RANKS:
            if infer_action(ranks + [rank], frozenset()) in COMBO_ACTIONS:
                return 1
    return 0


def _hand_cost(cards) -> float:
    """What a hand costs to be holding — points, plus the shape it leaves us in.

    This is the heart of the "think a turn ahead" part. Shedding points is only
    half the job: a hand of 5-6-7 is far better than a hand of 4-9-K worth the
    same, because the first one goes out next turn for a flat 0 and the second
    can only ever be ground down a card at a time.
    """
    status = _exit_status(cards)
    residual = 1.0
    if status == 2:
        residual = READY_RESIDUAL
    elif status == 1:
        residual = NEAR_RESIDUAL
    return hand_total(cards) * residual + CARD_COST * len(cards)


def _gift_cost(thrown, obs: Observation, unseen_counts, unseen_total: int) -> float:
    """Expected points the next player can dump onto our throw for free.

    Whatever we put down becomes the centre, and matching off it costs them
    nothing (room.center_rank_set() is ungated — every throw is matchable, not
    just combos). Dumping a pair of Queens is therefore not purely a gain: it
    also hands the next player a free exit for any Queens of their own.
    """
    if not obs.next_player_cards or not unseen_total:
        return 0.0
    cost = 0.0
    for rank in {c.rank for c in thrown}:
        copies_loose = unseen_counts.get(rank, 0)
        expected_held = obs.next_player_cards * copies_loose / float(unseen_total)
        cost += expected_held * rank
    return cost


def _candidate_plays(hand, center_ranks) -> List[Tuple[List, str]]:
    """Every legal throw available, as (cards, action) pairs.

    Deliberately exhaustive rather than a shortlist: the scorer weighs shape and
    gifting as well as points, so plays that look obviously worse on points
    alone (a shorter run, only some of the matching cards) can genuinely win.
    Everything is filtered through infer_action, so nothing illegal reaches the
    scorer and the scorer never has to know the rules.
    """
    by_rank = defaultdict(list)
    for card in hand:
        by_rank[card.rank].append(card)

    candidates: List[Tuple[List, str]] = []

    def add(cards):
        if not cards:
            return
        action = infer_action([c.rank for c in cards], center_ranks)
        if action is not None:
            candidates.append((list(cards), action))

    # Sets — 3 or 4 of a rank. With four available, keeping one back leaves a
    # card that can still be paired or matched later.
    for cards in by_rank.values():
        if len(cards) >= 3:
            add(cards[:3])
        if len(cards) >= 4:
            add(cards[:4])

    # Sequences — every contiguous run of 3+, not just the maximal one. The
    # maximal run always sheds the most points, but a shorter one can leave a
    # better hand: from 4-5-6-7 with nothing else, throwing 5-6-7 keeps a lone
    # 4 while throwing all four goes out.
    ordered = sorted(by_rank)
    index = 0
    while index < len(ordered):
        run = [ordered[index]]
        step = index + 1
        while step < len(ordered) and ordered[step] == run[-1] + 1:
            run.append(ordered[step])
            step += 1
        for start in range(len(run)):
            for end in range(start + 3, len(run) + 1):
                add([by_rank[rank][0] for rank in run[start:end]])
        index = step

    # Match — any combination of our cards whose ranks are all showing in the
    # centre. Throwing every one sheds the most, but holding some back can keep
    # a set together, so all the combinations are offered.
    matched_ranks = [r for r in sorted(center_ranks) if by_rank.get(r)]
    if matched_ranks:
        counts = [range(len(by_rank[r]) + 1) for r in matched_ranks]
        for take in product(*counts):
            if not any(take):
                continue
            picked = []
            for rank, n in zip(matched_ranks, take):
                picked.extend(by_rank[rank][:n])
            add(picked)

    # Pairs, and every single card. infer_action promotes a single that matches
    # the centre into a free Match on its own.
    for cards in by_rank.values():
        if len(cards) >= 2:
            add(cards[:2])
    for card in hand:
        add([card])

    return candidates


def _score_play(cards, action: str, obs: Observation, pool_mean: float,
                unseen_counts, unseen_total: int) -> float:
    """What a throw is worth: how much better it leaves our position.

    Scored as the improvement in _hand_cost rather than as raw points shed, so
    the cards left behind count as much as the ones thrown — then charged for
    the card we draw back and for what we hand the next player.
    """
    owes_draw = _owes_draw(action)
    thrown = set(map(id, cards))
    remaining = [c for c in obs.hand if id(c) not in thrown]

    if not remaining and not owes_draw:
        return SAFE_BONUS

    after = _hand_cost(remaining)
    if owes_draw:
        # We do not know what comes back, so charge the average unseen card and
        # the standing cost of holding one more. A drawn card can complete a
        # combo, but that is not something to count on.
        after += pool_mean + CARD_COST

    improvement = _hand_cost(obs.hand) - after
    return improvement - GIFT_WEIGHT * _gift_cost(cards, obs, unseen_counts, unseen_total)


def best_play(obs: Observation) -> Tuple[List, str]:
    """Pick the highest-scoring legal throw. Returns (cards, action)."""
    candidates = _candidate_plays(obs.hand, obs.center_ranks)
    if not candidates:
        # A single card is always legal, so this is unreachable in practice.
        return [max(obs.hand, key=lambda c: c.value)], ACTION_SINGLE

    pool_mean, _ = _pool_stats(obs.unseen)
    unseen_counts = Counter(obs.unseen)
    unseen_total = len(obs.unseen)

    best = None
    best_score = None
    for cards, action in candidates:
        score = _score_play(cards, action, obs, pool_mean, unseen_counts, unseen_total)
        if best_score is None or score > best_score:
            best, best_score = (cards, action), score
    return best


# ---- entry point -------------------------------------------------------------

def decide_move(room, bot_id: str) -> Optional[dict]:
    """Top-level entry point called by the director.

    Returns one of:
        {"action": "stop"}
        {"action": "play",  "cards": [Card, ...], "action_type": str}
        {"action": "draw"}   — when awaiting_draw is True
        None                 — nothing to do (bot is safe / not its turn)
    """
    bot = room.players.get(bot_id)
    if bot is None or bot.is_safe:
        return None

    # If we owe a draw, just draw — there is no choice to make.
    if room.awaiting_draw and room.current_turn_id() == bot_id:
        return {"action": "draw"}

    if room.current_turn_id() != bot_id or not bot.hand:
        return None

    obs = observe(room, bot_id)
    cards, action_type = best_play(obs)

    # Going out scores a guaranteed 0 with no risk at all, which beats even a
    # winning Stop call — so never gamble on a turn where we can simply empty.
    if not _goes_safe(cards, action_type, len(obs.hand)) and should_call_stop(obs):
        return {"action": "stop"}

    return {"action": "play", "cards": cards, "action_type": action_type}
