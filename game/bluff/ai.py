"""AI move logic for the Bluff computer player.

Called from the bot-turn branch of sockets/gameplay/bluff.py. Stateless — every
decision is derived from (room, bot_id) — so several bots can share it at one
table without interfering.

Public information only
-----------------------
Bluff has the strictest visibility rules of the three games: game/bluff/
visibility.py puts the public set at *nothing*, because a player who could see
the centre pile would win every Show and that does not merely help them, it
solves the game. ``room.last_play["cards"]`` holds the actual face-down cards,
so a bot reading it would be unbeatable and worthless to play against.

``observe()`` is therefore the only function here that touches ``room``, and it
takes from ``last_play`` just the *count* and the *declared* rank — what every
player sees when cards go face down. Everything else works off the Observation.
tests/test_bluff_bot.py enforces it: the same position is decided twice with the
face-down cards swapped for completely different ones, and the answer must not
change.

What it reasons about
---------------------
The old bot was ~50 lines of coin flips: challenge on a flat 20% roll, play
truthfully on 80%, otherwise pass or bluff on a 50/50, always leading with a
random rank. It never once looked at its own cards to judge a claim, which is
the whole game.

  * **Counting.** Holding two 7s means only two more exist, so a claim of three
    7s is not suspicious, it is *impossible* — a free Show. The same arithmetic
    across the whole chain catches over-subscribed ranks: the pile is every card
    claimed as the target rank, so once it exceeds what the deck holds, somebody
    has lied.
  * **Plausibility.** Short of certainty, a claim of q cards from a player
    holding h is scored hypergeometrically against the copies unaccounted for.
    Claiming four of a rank is far less believable than claiming one.
  * **What a Show is worth.** Whoever loses picks up the pile, so the pile size
    cancels out of the comparison and what remains is the table size: with one
    opponent a Show pays at even odds, with five you want to be far surer.
  * **Blocking a finish.** A player throwing their last cards is out for good
    unless challenged, so the bar to Show them drops sharply. The old bot let
    people walk out on a 20% dice roll.
  * **When bluffing is affordable.** Getting caught means eating the whole pile,
    so bluffing is for small piles, with as few cards as possible, spending the
    ranks we hold only one of. On a big pile it passes instead.
  * **Truth is a trap.** Playing honestly onto a large pile is one of the best
    moves in the game: a challenger eats all of it. So it never passes up a
    truthful play.
"""
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from game.core.cards import rank_code

# ---- tunables ----------------------------------------------------------------
BOT_THINK_MIN = 1.8
BOT_THINK_MAX = 3.5

# Most cards this bot puts down in one play. The rules allow any number (even a
# whole hand); the bot keeps to four because bigger claims are easy to count out.
MAX_THROW = 4

# How much more willing to Show we are when the claim would otherwise put that
# player out for good. Blocking a finish is worth much more than the pile.
FINISH_BLOCK_BONUS = 2.5

# Getting caught bluffing means picking up the whole pile, so it is only worth
# it while the pile is small. Compared against pile size plus the cards thrown.
BLUFF_PILE_LIMIT = 5
# ...but a bluff that empties our hand wins the place outright if it survives,
# which justifies a good deal more risk.
GOING_OUT_PILE_TOLERANCE = 3.0

# How often a player who does NOT hold the target rank chooses to bluff rather
# than simply pass. This is the number that stops the bot seeing liars
# everywhere: passing is free and always available, so a player who *chose* to
# play is more likely to be holding than a blind count of the deck suggests.
BASE_BLUFF_RATE = 0.35

# A chain in which more cards have been claimed than the deck holds is a chain
# people are lying in, which lifts the odds that any given play in it is a lie.
# It lifts the *rate*, never the verdict — the lies may all have been other
# players', and reading it as a direct accusation is what made the bot challenge
# honest opponents over and over.
CHAIN_SATURATION_LIFT = 0.6

# Reputation shifts how often we think a particular player bluffs. Scaled by how
# many times they have actually been shown, so a player nobody has challenged
# yet moves the estimate not at all.
REPUTATION_EVIDENCE_HALFLIFE = 2.0   # shows needed before reputation counts half

# Being wrong means eating the whole pile. Weighed against the hand we already
# hold, because doubling a small hand loses the game outright while adding to a
# big one barely registers.
PILE_RISK_WEIGHT = 0.25
MIN_SHOW_THRESHOLD = 0.25

# Cover bluff: with this many of one rank in hand, declaring that rank while
# throwing something else is the safest lie in the game — see _lead_play.
COVER_BLUFF_MIN_GROUP = 3
COVER_BLUFF_MAX_CARDS = 2
# -----------------------------------------------------------------------------


def bot_delay() -> float:
    return random.uniform(BOT_THINK_MIN, BOT_THINK_MAX)


# ---- observation: the only view of the game the strategy functions get -------

@dataclass(frozen=True)
class Opponent:
    user_id: str
    card_count: int


@dataclass(frozen=True)
class Observation:
    """A public-information snapshot of the table from one bot's seat.

    Note what is absent: the faces of anything in the centre pile, the dead
    pile, or anyone's hand. `last_claim` is a *count* of face-down cards and
    `target_rank` is what was *declared* — both of which every player sees.
    """
    hand: Tuple                       # our own cards (Card objects)
    target_rank: Optional[str]        # rank code locked for this chain, or None
    pile_size: int                    # face-down cards in the centre
    last_claim: int                   # how many cards the previous player laid
    last_player_id: Optional[str]
    last_player_cards_left: int       # 0 => they are out unless challenged
    opponents: Tuple[Opponent, ...]   # everyone else still holding cards
    copies_per_rank: int              # 4 per deck
    unseen_total: int                 # every card that is not in our hand
    # Table memory, all of it from Shows that were flipped face up for everyone.
    known_cards: Tuple[Tuple[str, Tuple[str, ...]], ...]   # (user_id, rank codes)
    reveal_log: Tuple[dict, ...]


def observe(room, bot_id: str) -> Observation:
    """Build the public-information view. The ONLY function here reading `room`.

    From ``last_play`` it takes the count and the declared rank and nothing
    else — deliberately never ``last_play["cards"]``, which holds the real
    face-down cards and would make the bot omniscient.
    """
    me = room.players[bot_id]
    num_decks = max(1, int(room.settings.get("num_decks", 1)))

    last = room.last_play or None
    last_player_id = last["user_id"] if last else None
    last_claim = len(last["cards"]) if last else 0
    last_player = room.players.get(last_player_id) if last_player_id else None
    last_player_cards_left = len(last_player.hand) if last_player else 0

    opponents = tuple(
        Opponent(user_id=uid, card_count=len(room.players[uid].hand))
        for uid in room.turn_order
        if uid != bot_id and uid in room.players
        and not room.is_finished(uid) and room.players[uid].hand
    )

    known = getattr(room, "known_cards", {}) or {}
    return Observation(
        hand=tuple(me.hand),
        target_rank=room.target_rank,
        pile_size=len(room.center_pile),
        last_claim=last_claim,
        last_player_id=last_player_id,
        last_player_cards_left=last_player_cards_left,
        opponents=opponents,
        copies_per_rank=4 * num_decks,
        unseen_total=52 * num_decks - len(me.hand),
        known_cards=tuple(
            (uid, tuple(codes)) for uid, codes in known.items() if uid != bot_id
        ),
        reveal_log=tuple(getattr(room, "reveal_log", []) or []),
    )


# ---- counting and plausibility ----------------------------------------------

def _p_at_least(marked: int, population: int, drawn: int, wanted: int) -> float:
    """P(at least `wanted` marked items in `drawn` draws) — hypergeometric.

    Used to ask "could that player really have held the cards they claimed?".
    """
    if wanted <= 0:
        return 1.0
    if marked < wanted or drawn < wanted or population <= 0 or drawn > population:
        return 0.0 if (marked < wanted or drawn < wanted) else 1.0
    total = math.comb(population, drawn)
    if not total:
        return 0.0
    hit = 0
    for i in range(wanted, min(drawn, marked) + 1):
        hit += math.comb(marked, i) * math.comb(population - marked, drawn - i)
    return hit / float(total)


def copies_held(obs: Observation, code: Optional[str]) -> int:
    """How many of a rank we are holding ourselves."""
    if not code:
        return 0
    return sum(1 for c in obs.hand if rank_code(c.rank) == code)


def known_copies(obs: Observation, code: Optional[str], user_id: Optional[str] = None) -> int:
    """Copies of a rank known to sit in a given hand (or in anyone else's).

    Knowledge comes only from Shows, which flip cards face up for the whole
    table — so this is memory every player at the table has, not a peek.
    """
    if not code:
        return 0
    return sum(
        codes.count(code)
        for uid, codes in obs.known_cards
        if user_id is None or uid == user_id
    )


def honesty(obs: Observation, user_id: Optional[str]) -> float:
    """How often this player's claims have proved true when challenged.

    Laplace-smoothed, which gives exactly the 0.5 "no idea yet" starting point
    and moves off it gently: one caught bluff reads 0.33, one honest showing
    0.67, rather than lurching to 0 or 1 on a single data point.
    """
    if not user_id:
        return 0.5
    shows = [r for r in obs.reveal_log if r.get("defender") == user_id]
    honest = sum(1 for r in shows if not r.get("was_bluff"))
    return (honest + 1) / float(len(shows) + 2)


def bluff_rate(obs: Observation) -> float:
    """How often this player, in this spot, plays without holding the goods.

    Reputation belongs here rather than bolted onto the final answer: what a
    player's history tells you is how readily they lie, not whether this
    particular claim is false. The cards decide that.
    """
    rate = BASE_BLUFF_RATE

    user_id = obs.last_player_id
    shows = sum(1 for r in obs.reveal_log if r.get("defender") == user_id)
    if shows:
        weight = shows / float(shows + REPUTATION_EVIDENCE_HALFLIFE)
        # 1.0 at the neutral 0.5, above it for proven liars, below for players
        # whose claims have kept turning out true.
        factor = (1.0 - honesty(obs, user_id)) / 0.5
        rate *= (1.0 - weight) + weight * factor

    # More of this rank has been claimed than exists, so this is a chain in
    # which people are demonstrably lying.
    mine = copies_held(obs, obs.target_rank)
    if obs.pile_size > 0:
        saturation = max(0, obs.pile_size + mine - obs.copies_per_rank) / float(obs.pile_size)
        rate *= 1.0 + CHAIN_SATURATION_LIFT * min(1.0, saturation)

    return min(0.9, max(0.05, rate))


def bluff_probability(obs: Observation) -> float:
    """How likely the previous player's claim was a lie, on public evidence."""
    if not obs.last_claim or not obs.target_rank:
        return 0.0

    code = obs.target_rank
    mine = copies_held(obs, code)
    claimant = obs.last_player_id
    # Copies whose location we already know, sitting in hands other than ours
    # and other than the claimant's — those cannot be what they just played.
    spoken_for = known_copies(obs, code) - known_copies(obs, code, claimant)
    known_theirs = known_copies(obs, code, claimant)
    available = obs.copies_per_rank - mine - spoken_for

    # Certainty. They claimed more of the rank than can exist outside our hand
    # and the hands we have already accounted for. No reading required.
    if obs.last_claim > available:
        return 1.0

    # They are known to hold enough of it, so the claim needs no invention.
    needed = obs.last_claim - known_theirs
    if needed <= 0:
        return 0.0

    # Could a hand that size really have held the rest?
    hand_before = obs.last_player_cards_left + obs.last_claim
    p_holds = _p_at_least(
        max(0, available - known_theirs),
        obs.unseen_total,
        max(0, hand_before - known_theirs),
        needed,
    )

    # The correction that matters most, and the one this bot was missing.
    # Passing is free and always available, so a player only plays into a chain
    # when they want to — which means playing is itself evidence of holding.
    # Reading "they probably don't have it" straight off as "they are lying"
    # ignores that they could simply have passed, and it is what had the bot
    # challenging honest opponents over and over: every failed Show fed their
    # cards into our own hand and handed them the lead.
    #
    #     P(lying | played)  =        P(no cards) * P(bluffs anyway)
    #                          ------------------------------------------
    #                          P(holds) + P(no cards) * P(bluffs anyway)
    rate = bluff_rate(obs)
    lying = (1.0 - p_holds) * rate
    denominator = p_holds + lying
    if denominator <= 0.0:
        return 1.0
    return min(1.0, max(0.0, lying / denominator))


def show_threshold(obs: Observation) -> float:
    """How sure we need to be before calling Show.

    Two things set the bar.

    *Who benefits.* A hit costs one opponent out of several while a miss costs
    us outright, so the more players at the table the surer we must be. Heads up
    that is even odds; across five opponents it is closer to 0.83.

    *What a miss costs.* Getting it wrong is not merely neutral — we swallow the
    entire pile, the honest player sheds every card they put in it, and they win
    the lead to name the next rank. Weighed against the hand we are already
    holding, because eating fifteen cards on a hand of eleven loses the game
    while adding them to a hand of forty barely registers. Without this the bar
    stayed flat as the pile grew, and challenging a big pile became a runaway
    loop: each failed Show made the next one look even more attractive.
    """
    contenders = max(1, len(obs.opponents))
    threshold = contenders / float(1 + contenders)

    at_stake = obs.pile_size + obs.last_claim
    threshold += PILE_RISK_WEIGHT * (at_stake / float(max(1, len(obs.hand))))

    # Unless we challenge, a player who has just thrown their last cards is out
    # for good — a permanent loss, not a pile of cards. Worth far more risk.
    if obs.last_player_cards_left == 0:
        threshold /= FINISH_BLOCK_BONUS

    # Capped at 1.0 rather than above it, so a claim we have *proved* impossible
    # is always challenged no matter how frightening the pile.
    return min(1.0, max(MIN_SHOW_THRESHOLD, threshold))


def should_show(obs: Observation, my_id: Optional[str] = None) -> bool:
    """Whether to challenge the previous play."""
    if not obs.last_claim or obs.last_player_id is None:
        return False
    # Only the player after the claimant may challenge, and never ourselves —
    # reachable if the turn wraps back round before the pile is swept.
    if my_id is not None and obs.last_player_id == my_id:
        return False
    return bluff_probability(obs) >= show_threshold(obs)


# ---- choosing what to throw --------------------------------------------------

def _by_rank(hand) -> Dict[str, List]:
    groups: Dict[str, List] = {}
    for card in hand:
        groups.setdefault(rank_code(card.rank), []).append(card)
    return groups


def _singletons(obs: Observation) -> List:
    """Cards whose rank we hold exactly one of.

    These are the hard ones. A rank you hold three of sheds itself the moment
    that rank comes up; a lone card has to wait for its rank to be called, or
    be smuggled out under a lie.
    """
    groups = _by_rank(obs.hand)
    return [c for c in obs.hand if len(groups[rank_code(c.rank)]) == 1]


def _lead_play(obs: Observation) -> Dict[str, Any]:
    """Open a fresh chain.

    The rank is whatever we hold most of. That does double duty: it is the rank
    we can most easily keep playing honestly, and it leaves the fewest copies
    out on the table, so every later claim on it is likelier to be a lie we can
    catch. (The old bot picked the rank of a random card.)

    What we *throw* need not be that rank, though. Leading is the cheapest place
    in the game to lie: the pile is empty, so being caught hands back only the
    cards we just threw. And a lie is safest on a rank we hold most of, because
    everyone else holds few copies and so cannot rule it out by counting.

    Put together, that is the play this bot was missing: declare the rank we are
    rich in, throw the singletons we would otherwise be stuck with, and keep the
    real copies to play honestly later in the same chain — when the pile is big
    and an honest play is at its most dangerous to challenge.
    """
    groups = _by_rank(obs.hand)
    code = max(groups, key=lambda r: (len(groups[r]), r))
    biggest = groups[code]

    spare = _singletons(obs)
    if len(biggest) >= COVER_BLUFF_MIN_GROUP and spare:
        # Never claim more than we could actually be holding — a claim of three
        # while we hold four of the rank stays perfectly plausible to a counter.
        count = min(COVER_BLUFF_MAX_CARDS, len(spare), len(biggest))
        return {"action": "play",
                "cards": [c.id for c in spare[:count]],
                "declared_rank": code}

    return {"action": "play",
            "cards": [c.id for c in biggest[:MAX_THROW]],
            "declared_rank": code}


def _spare_cards(obs: Observation, count: int) -> List:
    """Cards to bluff with: the ranks we hold fewest of.

    A singleton is the cheapest thing to lose — holding two or more of a rank is
    what lets us play honestly later in a chain on it.
    """
    groups = _by_rank(obs.hand)
    ordered = sorted(obs.hand, key=lambda c: (len(groups[rank_code(c.rank)]), c.rank))
    return ordered[:count]


def _choose_play(obs: Observation) -> Dict[str, Any]:
    """Play, bluff, or pass, given that we are not challenging."""
    if not obs.hand:
        return {"action": "pass"}
    if obs.target_rank is None:
        return _lead_play(obs)

    held = [c for c in obs.hand if rank_code(c.rank) == obs.target_rank]
    if held:
        # Always take an honest play. It sheds cards, and it is a trap: anyone
        # who challenges it picks up the whole pile themselves — which is best
        # of all exactly when the pile is at its most frightening.
        chosen = held[:MAX_THROW]
        return {"action": "play",
                "cards": [c.id for c in chosen],
                "declared_rank": obs.target_rank}

    # Nothing honest to play: bluff only while being caught is survivable.
    # One card is both the cheapest to lose and the easiest claim to believe.
    going_out = len(obs.hand) == 1
    limit = BLUFF_PILE_LIMIT * (GOING_OUT_PILE_TOLERANCE if going_out else 1.0)
    if obs.pile_size + 1 <= limit:
        chosen = _spare_cards(obs, 1)
        return {"action": "play",
                "cards": [c.id for c in chosen],
                "declared_rank": obs.target_rank}

    return {"action": "pass"}


# ---- entry point -------------------------------------------------------------

def decide_move(room, bot_id: str) -> Dict[str, Any]:
    """Top-level entry point called by the director."""
    bot = room.players.get(bot_id)
    if bot is None or not bot.hand:
        return {"action": "pass"}

    obs = observe(room, bot_id)
    if should_show(obs, bot_id):
        return {"action": "show"}
    return _choose_play(obs)
