"""AI move logic — SINGLE-PLAYER MODE ONLY.

This module is only imported / called by the bot-turn branch in
sockets/director.py.  Nothing in the normal multiplayer path touches it,
so it cannot break group games even if it raises an exception.

Strategy (roughly human-skill):
  1. No-draw combos (Set / Sequence) — shed the most cards with no draw.
  2. Free Match (when MATCH_REQUIRES_DRAW is False) — also costs nothing.
  3. Largest Match that owes a draw — still better than discarding one card.
  4. Pair — throw two of a kind, draw one (net -1 card).
  5. Discard the single highest-value card, draw one (net 0 cards, lowest pts).

Stop-calling:
  Call Stop only when ALL of:
    • first orbit is complete
    • bot's hand total ≤ BOT_STOP_THRESHOLD
    • no opponent is already safe (safe = 0 pts, can't be beaten)
    • bot's total is strictly less than the opponent's *current* hand total
      (defensive — never risk the penalty if it could be a tie)

Randomised delay (human-feel):
  The caller (director) waits BOT_THINK_MIN .. BOT_THINK_MAX seconds before
  acting.  Using random keeps it feeling natural rather than robotic.
"""
import random
from typing import List, Optional, Tuple

from config import MATCH_REQUIRES_DRAW
from game.super_seven.rules import (
    infer_action,
    ACTION_SET, ACTION_SEQUENCE, ACTION_PAIR, ACTION_MATCH, ACTION_SINGLE,
    COMBO_ACTIONS,
)

# ---- tunables ----------------------------------------------------------------
BOT_STOP_THRESHOLD = 8      # bot calls Stop when hand total ≤ this value
BOT_THINK_MIN = 1.5         # minimum seconds before bot acts
BOT_THINK_MAX = 3.0         # maximum seconds before bot acts
# -----------------------------------------------------------------------------


def bot_delay() -> float:
    """Return a random human-like pause in seconds."""
    return random.uniform(BOT_THINK_MIN, BOT_THINK_MAX)


def _hand_total(hand) -> int:
    """Sum of card values in a hand."""
    return sum(c.value for c in hand)


def _should_call_stop(room, bot_id: str) -> bool:
    """Return True if the bot should call Stop right now.

    Called at the START of the bot's turn, before any throw.
    """
    if not room.first_orbit_complete:
        return False
    bot = room.players[bot_id]
    if bot.is_safe:
        return False
    my_total = _hand_total(bot.hand)
    if my_total > BOT_STOP_THRESHOLD:
        return False

    # Only call if we are STRICTLY below every opponent's current hand total (ignoring safe and eliminated players).
    for uid, p in room.players.items():
        if uid == bot_id or p.eliminated or p.is_safe:
            continue
        if _hand_total(p.hand) <= my_total:
            return False  # tied or beaten — don't risk the penalty

    return True


def _best_play(hand, center_ranks) -> Tuple[List, str]:
    """Choose the best cards to play and return (card_list, action).

    Priority order:
      1. Set (3-4 of a kind) — pick the highest-rank set to shed most points.
      2. Sequence (3+ run) — pick the highest-value run.
      3. Free Match (no-draw) when MATCH_REQUIRES_DRAW is False.
      4. Match that owes a draw — best multi-card discard option left.
      5. Pair — two of a kind; keep the lower pair if multiple.
      6. Single — throw the highest-value card.
    """
    # Group cards by rank
    from collections import defaultdict
    by_rank = defaultdict(list)
    for c in hand:
        by_rank[c.rank].append(c)

    # 1. Set (3-4 of same rank) — prefer the highest rank to shed most points
    best_set = None
    best_set_rank = -1
    for rank, cards in by_rank.items():
        if len(cards) >= 3:
            group = cards[:4]  # max 4 in a set
            if rank > best_set_rank:
                best_set = group
                best_set_rank = rank
    if best_set:
        return best_set, ACTION_SET

    # 2. Sequence — find all runs of 3+; pick the one with the highest sum
    best_seq = None
    best_seq_val = -1
    ranks_available = sorted(by_rank.keys())
    # Enumerate all maximal runs then pick best sub-run of length ≥ 3
    for start_idx, start_rank in enumerate(ranks_available):
        run_ranks = [start_rank]
        for r in ranks_available[start_idx + 1:]:
            if r == run_ranks[-1] + 1:
                run_ranks.append(r)
            else:
                break
        if len(run_ranks) >= 3:
            # Use one card per rank (pick lowest copy to keep higher ones free)
            seq_cards = [by_rank[r][0] for r in run_ranks]
            val = sum(c.value for c in seq_cards)
            if val > best_seq_val:
                best_seq = seq_cards
                best_seq_val = val
    if best_seq:
        return best_seq, ACTION_SEQUENCE

    # 3 & 4. Match — throw as many matching cards as possible
    if center_ranks:
        match_cards = [c for c in hand if c.rank in center_ranks]
        if match_cards:
            action = ACTION_MATCH
            # Check if infer_action would upgrade to a combo (e.g. 3 matching same rank = set)
            inferred = infer_action([c.rank for c in match_cards], center_ranks)
            if inferred in COMBO_ACTIONS:
                return match_cards, inferred
            return match_cards, action

    # 5. Pair — find any pair; prefer highest rank to shed most points
    best_pair = None
    best_pair_rank = -1
    for rank, cards in by_rank.items():
        if len(cards) >= 2 and rank > best_pair_rank:
            best_pair = cards[:2]
            best_pair_rank = rank
    if best_pair:
        return best_pair, ACTION_PAIR

    # 6. Single — throw the highest-value card
    highest = max(hand, key=lambda c: c.value)
    return [highest], ACTION_SINGLE


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

    # If we owe a draw, just draw.
    if room.awaiting_draw and room.current_turn_id() == bot_id:
        return {"action": "draw"}

    if room.current_turn_id() != bot_id:
        return None

    # At the START of the turn: consider calling Stop.
    if _should_call_stop(room, bot_id):
        return {"action": "stop"}

    # Otherwise pick the best throw.
    if not bot.hand:
        return None  # already safe (hand emptied via combo earlier)

    center_ranks = room.center_rank_set()
    cards, action_type = _best_play(bot.hand, center_ranks)
    return {"action": "play", "cards": cards, "action_type": action_type}
