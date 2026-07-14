"""Super 4 single-player bot (Suryavanshi).

A memory-style heuristic player. It reasons only from what it legitimately knows
(room.known[bot]) plus the public drawn card — never from hidden state — so it
plays by the same information rules as a human. The socket director calls these
helpers to drive a bot turn; state mutation always goes through Room methods.
"""
import random

from game.super_four import powers
from game.super_four.scoring import card_value

# Tunables
STOP_THRESHOLD = 10        # call Stop when estimated total is at or below this
KEEP_MAX_VALUE = 5         # a drawn card this cheap is worth keeping
UNKNOWN_EST = 6.5          # assumed value of a slot the bot can't see


def bot_delay() -> float:
    """Human-feel pause before the bot acts."""
    return random.uniform(1.0, 2.2)


def _known_own(room, uid):
    """[(slot, card)] for the bot's own occupied slots it currently knows."""
    out = []
    cards = room.slots.get(uid, [])
    for (owner, slot) in room.known.get(uid, set()):
        if owner == uid and 0 <= slot < len(cards) and cards[slot] is not None:
            out.append((slot, cards[slot]))
    return out


def _occupied_slots(room, owner):
    return [i for i, c in enumerate(room.slots.get(owner, [])) if c is not None]


def estimate_total(room, uid) -> float:
    """Known card values summed; unknown occupied slots estimated."""
    cards = room.slots.get(uid, [])
    known_slots = {s for (o, s) in room.known.get(uid, set()) if o == uid}
    total = 0.0
    for i, c in enumerate(cards):
        if c is None:
            continue
        total += card_value(c) if i in known_slots else UNKNOWN_EST
    return total


def should_stop(room, uid) -> bool:
    if not room.first_orbit_complete or room.stop_caller is not None:
        return False
    return estimate_total(room, uid) <= STOP_THRESHOLD


def decide_after_draw(room, uid, drawn):
    """Return ('match_own', slot) | ('keep', slot) | ('discard', None)."""
    known = _known_own(room, uid)

    # 1) Known exact match -> shed a card.
    for slot, card in known:
        if card.rank == drawn.rank:
            return ("match_own", slot)

    dval = card_value(drawn)
    # 2) Cheap drawn card -> replace the worst known card if that helps.
    if dval <= KEEP_MAX_VALUE and known:
        worst_slot, worst_card = max(known, key=lambda sc: card_value(sc[1]))
        if card_value(worst_card) > dval:
            return ("keep", worst_slot)
    # 3) Very cheap and nothing known -> take the gamble into slot 0.
    if dval <= 1 and not known and _occupied_slots(room, uid):
        return ("keep", _occupied_slots(room, uid)[0])
    # 4) Otherwise discard (also fires a power if it's a power card).
    return ("discard", None)


def _an_opponent(room, uid):
    opps = room._opponents_with_cards(uid)
    return opps[0] if opps else None


def _unknown_slot(room, viewer, owner):
    """An occupied slot of `owner` that `viewer` does not know; else any occupied."""
    occ = _occupied_slots(room, owner)
    unknown = [s for s in occ if (owner, s) not in room.known.get(viewer, set())]
    if unknown:
        return unknown[0]
    return occ[0] if occ else None


def resolve_power(room, uid, rank):
    """Return the args tuple for the matching Room.power_* call, or None to skip.

    king is two-phase: returns ('king_look', own_slot, opp, opp_slot); the director
    then asks king_should_swap() after the look.
    """
    kind = powers.power_kind(rank)
    if kind == powers.PEEK_OWN:
        slot = _unknown_slot(room, uid, uid)
        return ("peek_own", slot) if slot is not None else None
    if kind == powers.PEEK_OPP:
        opp = _an_opponent(room, uid)
        if opp is None:
            return None
        return ("peek_opp", opp, _unknown_slot(room, uid, opp))
    if kind == powers.BLIND_SWAP:
        opp = _an_opponent(room, uid)
        if opp is None:
            return None
        known = _known_own(room, uid)
        # Dump our worst known card; fall back to slot 0.
        if known:
            own_slot = max(known, key=lambda sc: card_value(sc[1]))[0]
        else:
            occ = _occupied_slots(room, uid)
            own_slot = occ[0] if occ else 0
        return ("blind_swap", own_slot, opp, _unknown_slot(room, uid, opp))
    if kind == powers.KING:
        opp = _an_opponent(room, uid)
        if opp is None:
            return None
        known = _known_own(room, uid)
        if known:
            own_slot = max(known, key=lambda sc: card_value(sc[1]))[0]
        else:
            occ = _occupied_slots(room, uid)
            own_slot = occ[0] if occ else 0
        return ("king_look", own_slot, opp, _unknown_slot(room, uid, opp))
    return None


def king_should_swap(own_card, opp_card) -> bool:
    """After a King look, swap if the opponent's card is cheaper than ours."""
    return card_value(opp_card) < card_value(own_card)


def find_match(room, bot_id):
    """During a match window, return ('own', slot) | ('opp', owner, slot) | None.

    Bots only ever attempt matches they KNOW (from preview/peeks), so they never
    guess wrong — fair play by the same information rules as a human.
    """
    mc = room.match_card
    if mc is None:
        return None
    for (owner, slot) in room.known.get(bot_id, set()):
        cards = room.slots.get(owner, [])
        if slot < len(cards) and cards[slot] is not None and cards[slot].rank == mc.rank:
            return ("own", slot) if owner == bot_id else ("opp", owner, slot)
    return None
