"""Computer player for Poker.

The bot sees what a human in its seat would see — its own two cards, the board,
stacks, bets and pots — and nothing else. It never reads ``room.deck``,
``room.burns`` or another player's ``hole``: its estimate of the cards still to
come is built from a fresh deck minus only the cards it can see. A bot that
peeked would be the hidden-information leak this platform guards against
everywhere else.

Decisions come from one number, the bot's estimated chance of winning (its
*equity*), found by dealing out random opponent hands and boards and counting
wins. That is compared with the price of continuing (pot odds), with a little
randomness so the bot is not perfectly predictable and sometimes bluffs.
"""
import random
from typing import Optional

from game.core.cards import build_deck
from game.poker.evaluator import evaluate

# Monte Carlo samples per decision. A few hundred gives a stable enough estimate
# for table play and takes a few milliseconds on the one-worker server.
SAMPLES = 240
# Opponents simulated at most; beyond this the equity barely moves and the cost
# keeps growing.
MAX_OPPONENTS = 4
BLUFF_CHANCE = 0.06


def bot_delay() -> float:
    """Human-feel thinking time before the bot acts."""
    return random.uniform(1.2, 3.0)


def equity(hole, board, opponents: int, samples: int = SAMPLES, rng=random) -> float:
    """Chance of winning (ties count as a share) against ``opponents`` random hands."""
    opponents = max(1, min(MAX_OPPONENTS, opponents))
    seen = {(c.rank, c.suit) for c in list(hole) + list(board)}
    unseen = [c for c in build_deck(1) if (c.rank, c.suit) not in seen]
    need_board = 5 - len(board)
    won = 0.0
    for _ in range(samples):
        draw = rng.sample(unseen, need_board + 2 * opponents)
        full_board = list(board) + draw[:need_board]
        mine = evaluate(list(hole) + full_board).value
        best_other = max(
            evaluate(draw[need_board + 2 * i: need_board + 2 * i + 2] + full_board).value
            for i in range(opponents)
        )
        if mine > best_other:
            won += 1.0
        elif mine == best_other:
            won += 0.5
    return won / samples


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def decide_move(room, bot_id: str, rng=random) -> Optional[dict]:
    """Return ``{"action": ..., "amount": raise_to_or_None}`` for the bot's turn."""
    legal = room.legal_actions(bot_id)
    if legal is None:
        return None

    hole = room.hole.get(bot_id, [])
    opponents = len([u for u in room.live() if u != bot_id])
    eq = equity(hole, room.board, opponents, rng=rng)

    pot = sum(room.contributed.values())
    to_call = legal["to_call"]
    pot_odds = to_call / float(pot + to_call) if to_call else 0.0
    # More opponents make the same raw equity less comfortable.
    strong = 0.78 - 0.04 * min(opponents - 1, 3)
    good = 0.55 - 0.05 * min(opponents - 1, 3)

    def raise_to(fraction_of_pot: float) -> dict:
        target = legal["bet"] + to_call + int(pot * fraction_of_pot)
        target = _clamp(target, legal["min_to"], legal["max_to"])
        return {"action": "raise", "amount": target}

    if legal["raise"]:
        if eq >= strong:
            if rng.random() < 0.25 or legal["max_to"] <= legal["min_to"]:
                return {"action": "allin", "amount": None}
            return raise_to(rng.choice((0.75, 1.0)))
        if eq >= good and rng.random() < 0.5:
            return raise_to(rng.choice((0.5, 0.66)))
        if to_call == 0 and rng.random() < BLUFF_CHANCE:
            return raise_to(0.5)

    if to_call == 0:
        return {"action": "check", "amount": None}
    # Call when the chance of winning beats the price, with a small margin so the
    # bot does not bleed coins on break-even calls.
    if eq >= pot_odds + 0.05 or (eq >= pot_odds and to_call <= legal["stack"] // 20):
        return {"action": "call", "amount": None}
    return {"action": "fold", "amount": None}
