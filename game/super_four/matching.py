"""Super 4 table-match window — self-contained, first-throw-resolves logic.

Rules (rules.txt):
- Any card landing face-up on the center opens a match window. EVERYONE at the
  table, including the discarder, may react.
- A throw may contain any number of cards — own and/or opponents' — as long as
  every selected card matches the center rank (suit never matters).
- For each opponent card thrown, the thrower transfers one of their own cards
  into that exact opponent slot.
- Only the FIRST throw counts: right -> the cards leave; wrong -> the thrower
  takes a penalty card. Either way the window closes for everyone else.
- The window also ends when its timer expires or when the next player starts
  their turn, whichever comes first.

This module owns window state and request validation only; the Room applies the
actual slot/knowledge mutations so hidden-information bookkeeping stays in one
place.
"""
import time
from typing import List, Optional, Set, Tuple

Position = Tuple[str, int]  # (owner_uid, slot_index)

REJECT = "reject"   # malformed request — window unaffected, thrower may retry
WRONG = "wrong"     # well-formed but a card doesn't match — penalty, window closes
RIGHT = "right"     # fully correct — cards leave, window closes


class MatchThrow:
    """A validated parse of one throw request."""

    __slots__ = ("selections", "transfers")

    def __init__(self, selections: List[Position], transfers: List[Tuple[Position, int]]):
        self.selections = selections   # positions thrown to the center
        self.transfers = transfers     # ((target_owner, target_slot), from_slot)


class MatchWindow:
    """One open match window. Created on discard, discarded on close."""

    def __init__(self, card, discarder: str, seconds: int, next_player: Optional[str]):
        self.card = card                    # the face-up center card to match
        self.discarder = discarder
        self.next_player = next_player      # may end the window by acting
        self.deadline = time.time() + max(0, int(seconds))
        self.passed: Set[str] = set()       # players who explicitly declined

    # ---- timing ----
    def seconds_left(self) -> int:
        return max(0, int(self.deadline - time.time()))

    def is_expired(self) -> bool:
        return time.time() >= self.deadline

    # ---- participation ----
    def decline(self, user_id: str) -> None:
        self.passed.add(user_id)

    def may_throw(self, user_id: str) -> bool:
        return user_id not in self.passed

    # ---- validation ----
    def parse(self, slots: dict, user_id: str, selections, replacements):
        """Validate a raw client request against the current slots.

        Returns ``(verdict, MatchThrow | None)`` where verdict is REJECT
        (malformed; does not consume the window), WRONG (a selected card does
        not match the center rank) or RIGHT.
        """

        def occupied(owner, slot):
            cards = slots.get(owner)
            return cards is not None and 0 <= slot < len(cards) and cards[slot] is not None

        if not isinstance(selections, list) or not selections:
            return REJECT, None

        parsed_sel: List[Position] = []
        seen: Set[Position] = set()
        for item in selections:
            if not isinstance(item, dict):
                return REJECT, None
            owner = item.get("owner")
            try:
                slot = int(item.get("slot"))
            except (TypeError, ValueError):
                return REJECT, None
            key = (owner, slot)
            if key in seen or not occupied(owner, slot):
                return REJECT, None
            seen.add(key)
            parsed_sel.append(key)

        opponent_targets = [key for key in parsed_sel if key[0] != user_id]
        if not isinstance(replacements, list):
            return REJECT, None
        replacement_by_target = {}
        used_give_slots: Set[int] = set()
        for item in replacements:
            if not isinstance(item, dict):
                return REJECT, None
            try:
                target = (item.get("target_owner"), int(item.get("target_slot")))
                give_slot = int(item.get("from_slot"))
            except (TypeError, ValueError):
                return REJECT, None
            if target in replacement_by_target or give_slot in used_give_slots:
                return REJECT, None
            replacement_by_target[target] = give_slot
            used_give_slots.add(give_slot)
        if set(replacement_by_target) != set(opponent_targets):
            return REJECT, None
        for give_slot in used_give_slots:
            # A transfer card must be an occupied card of the thrower and cannot
            # itself be one of the cards thrown to the center.
            if not occupied(user_id, give_slot) or (user_id, give_slot) in seen:
                return REJECT, None

        throw = MatchThrow(
            parsed_sel,
            [(target, give) for target, give in replacement_by_target.items()],
        )
        if any(slots[o][s].rank != self.card.rank for o, s in parsed_sel):
            return WRONG, throw
        return RIGHT, throw

    # ---- public snapshot ----
    def public_state(self) -> dict:
        return {
            "card": self.card.to_dict() if self.card else None,
            "discarder": self.discarder,
            "seconds_left": self.seconds_left(),
            # Kept under the historical key: players who may no longer throw.
            "attempted": list(self.passed),
            "next_player": self.next_player,
        }
