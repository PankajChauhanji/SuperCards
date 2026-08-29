import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""The Bluff computer player: what it may see, when it challenges, what it throws.

The old bot was coin flips — challenge on a flat 20% roll, play honestly on 80%,
otherwise pass or bluff on a 50/50, always opening on a random rank. It never
looked at its own cards to judge a claim, which in Bluff is the entire game.

Two things are pinned here.

**It cannot see the face-down cards.** ``room.last_play["cards"]`` holds the real
cards of the play being challenged, and game/bluff/visibility.py puts Bluff's
public set at nothing at all, because a player who can see the pile wins every
Show. The test is behavioural: the same position is decided twice with those
face-down cards swapped for completely different ones, and the answer must not
move.

**It counts.** Holding two 7s means only two more exist, so a claim of three is
not suspicious but impossible — and that free Show is the single biggest thing
the old bot threw away.
"""
from game.bluff import ai
from game.bluff.room import Room
from game.bluff.settings import DEFAULT_SETTINGS
from game.core.cards import Card, rank_code
from game.core.states import STATE_IN_TURN

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


def build_room(bot_hand, opponent_counts, target=None, pile=0,
               last_cards=None, last_left=3, settings=None):
    """A table with the bot on turn and `opponent_counts` other live players."""
    cfg = dict(DEFAULT_SETTINGS)
    cfg.update(settings or {})
    room = Room("BLUF", "bot", cfg)
    room.register_player("bot", "Bot")
    room.players["bot"].hand = list(bot_hand)

    order = ["bot"]
    for i, count in enumerate(opponent_counts):
        uid = "opp%d" % i
        room.register_player(uid, uid.upper())
        room.players[uid].hand = hand_of(*([7] * count))
        order.append(uid)

    room.turn_order = order
    room.turn_index = 0
    room.state = STATE_IN_TURN
    room.target_rank = target
    room.center_pile = hand_of(*([2] * pile))
    if last_cards is not None:
        prev = order[-1]
        room.players[prev].hand = hand_of(*([7] * last_left))
        room.last_play = {"user_id": prev, "cards": list(last_cards),
                          "declared_rank": target}
    else:
        room.last_play = None
    return room


def summarise(move):
    if move is None:
        return None
    out = {"action": move["action"]}
    if move["action"] == "play":
        out["declared_rank"] = move["declared_rank"]
        out["cards"] = sorted(move["cards"])
    return out


# ---- the bot cannot see the face-down cards ----------------------------------
# Same claim, same counts, completely different cards underneath. A bot reading
# last_play["cards"] would answer differently; one on public information cannot
# tell the two tables apart.
for label, bot_hand, target, pile, left in (
    ("a claim it may want to challenge", hand_of(7, 7, 3, 4), "7", 6, 2),
    ("a claim it should let stand", hand_of(3, 4, 5, 6), "7", 2, 4),
):
    truth = build_room(bot_hand, [4, 4], target=target, pile=pile,
                       last_cards=hand_of(7, 7), last_left=left)
    lie = build_room(bot_hand, [4, 4], target=target, pile=pile,
                     last_cards=hand_of(2, 11), last_left=left)
    check(summarise(ai.decide_move(truth, "bot")) == summarise(ai.decide_move(lie, "bot")),
          "decision is identical whether the face-down cards are real or not — %s" % label,
          (summarise(ai.decide_move(truth, "bot")), summarise(ai.decide_move(lie, "bot"))))

obs = ai.observe(build_room(hand_of(7, 7, 3), [4], target="7", pile=5,
                            last_cards=hand_of(7, 7)), "bot")
check("Card(" not in repr(obs.opponents), "the observation holds no opponent cards")
check(obs.last_claim == 2 and obs.pile_size == 5,
      "it does carry the claim's size and the pile's, which are public")
check(not any(hasattr(v, "rank") for v in vars(obs).values() if not isinstance(v, tuple)),
      "no stray card object reaches the observation")


# ---- counting: an impossible claim is a free Show ----------------------------
# Holding two 7s leaves only two in the game, so three cannot be honest.
room = build_room(hand_of(7, 7, 3, 4), [4, 4], target="7", pile=6,
                  last_cards=hand_of(7, 7, 7))
obs = ai.observe(room, "bot")
check(ai.bluff_probability(obs) == 1.0,
      "a claim of three 7s while holding two is certain, not merely suspicious")
check(ai.decide_move(room, "bot")["action"] == "show", "and it is challenged")

# Holding all four makes any claim at all impossible.
room = build_room(hand_of(7, 7, 7, 7, 3), [4, 4], target="7", pile=4,
                  last_cards=hand_of(7))
check(ai.decide_move(room, "bot")["action"] == "show",
      "holding all four of a rank, even a claim of one is challenged")

# A plausible claim from a full hand is left alone at a crowded table.
room = build_room(hand_of(3, 4, 5, 6), [5, 5, 5], target="7", pile=2,
                  last_cards=hand_of(7), last_left=6)
check(ai.decide_move(room, "bot")["action"] != "show",
      "a single card claimed off a full hand is not challenged on spec")

# Chain arithmetic: more cards claimed as 7s than the deck holds.
obs = ai.observe(build_room(hand_of(7, 3), [4, 4], target="7", pile=8,
                            last_cards=hand_of(7, 7)), "bot")
check(ai.bluff_probability(obs) > 0.5,
      "an over-subscribed pile is strong evidence of lying in the chain",
      ai.bluff_probability(obs))


# ---- what a Show is priced on ------------------------------------------------
# A big hand makes the pile risk negligible, isolating the table-size term.
BIG = hand_of(*([3] * 40))
heads_up = ai.observe(build_room(BIG, [4], target="7", pile=1,
                                 last_cards=hand_of(7)), "bot")
crowded = ai.observe(build_room(BIG, [4, 4, 4, 4, 4], target="7", pile=1,
                                last_cards=hand_of(7)), "bot")
check(ai.show_threshold(heads_up) < ai.show_threshold(crowded),
      "the more opponents there are, the surer it must be to challenge",
      (ai.show_threshold(heads_up), ai.show_threshold(crowded)))
check(abs(ai.show_threshold(heads_up) - 0.5) < 0.05,
      "heads up, with nothing at stake, a Show pays at about even odds",
      ai.show_threshold(heads_up))

# Being wrong means swallowing the pile, so the bar has to climb as it grows.
small = ai.observe(build_room(hand_of(*([3] * 11)), [5, 6], target="7", pile=2,
                              last_cards=hand_of(7), last_left=6), "bot")
large = ai.observe(build_room(hand_of(*([3] * 11)), [5, 6], target="7", pile=16,
                              last_cards=hand_of(7), last_left=6), "bot")
check(ai.show_threshold(large) > ai.show_threshold(small),
      "a bigger pile demands more certainty, because a miss swallows all of it",
      (ai.show_threshold(small), ai.show_threshold(large)))
check(ai.show_threshold(large) <= 1.0,
      "but never past 1.0, so a proven-impossible claim is always challenged")

# Blocking a finish is worth far more than a pile of cards.
normal = ai.observe(build_room(hand_of(3, 4), [4, 4], target="7", pile=4,
                               last_cards=hand_of(7), last_left=3), "bot")
finishing = ai.observe(build_room(hand_of(3, 4), [4, 4], target="7", pile=4,
                                  last_cards=hand_of(7), last_left=0), "bot")
check(ai.show_threshold(finishing) < ai.show_threshold(normal),
      "it challenges far more readily when the claim would put someone out",
      (ai.show_threshold(finishing), ai.show_threshold(normal)))


# ---- what it throws ----------------------------------------------------------
# Opening a chain with no singletons to hide: lead honestly on the rank we hold
# most of. Fewest copies left out means later claims on it are likelier lies.
room = build_room(hand_of(9, 9, 9, 4, 4), [4, 4], target=None)
move = ai.decide_move(room, "bot")
check(move["action"] == "play" and move["declared_rank"] == "9" and len(move["cards"]) == 3,
      "opens on the rank it holds most of, throwing all of them", summarise(move))

# The cover bluff. Holding three 9s and two awkward singletons, it declares 9s —
# the rank nobody else can disprove, because it holds most of them — and throws
# the singletons instead. Leading is the cheapest lie in the game (the pile is
# empty, so being caught only hands back what was just thrown), and the real 9s
# stay in hand to play honestly later in the same chain.
room = build_room(hand_of(9, 9, 9, 4, 6), [4, 4], target=None)
move = ai.decide_move(room, "bot")
thrown_ranks = sorted(c.rank for c in room.players["bot"].hand if c.id in move["cards"])
check(move["declared_rank"] == "9" and thrown_ranks == [4, 6],
      "declares the rank it is rich in but throws the singletons under it",
      (move["declared_rank"], thrown_ranks))
check(all(c.rank == 9 for c in room.players["bot"].hand if c.id not in move["cards"]),
      "and keeps every real 9 back for an honest play later in the chain")

# An honest play is always taken — a challenger eats the pile instead. The
# claimant holds a lot of cards here, so their claim is plausible and there is
# no Show to make; the question is only play-versus-pass.
room = build_room(hand_of(7, 7, 3), [4, 20], target="7", pile=4,
                  last_cards=hand_of(7), last_left=20)
move = ai.decide_move(room, "bot")
check(move["action"] == "play" and len(move["cards"]) == 2,
      "plays its real 7s rather than passing", summarise(move))

# Nothing honest and the pile has grown past what a bluff can risk: pass.
room = build_room(hand_of(3, 4, 5), [4, 20], target="7", pile=6,
                  last_cards=hand_of(7), last_left=20)
check(ai.decide_move(room, "bot")["action"] == "pass",
      "passes rather than bluffing into a pile it cannot afford to eat")

# Nothing honest but the pile is cheap: bluff, with a single card.
room = build_room(hand_of(3, 4, 5), [4, 4], target="7", pile=1,
                  last_cards=hand_of(7), last_left=4)
move = ai.decide_move(room, "bot")
check(move["action"] == "play" and len(move["cards"]) == 1
      and move["declared_rank"] == "7",
      "bluffs a single card when the pile is small", summarise(move))

# It bluffs with a rank it holds only one of, keeping pairs it could play
# honestly later.
room = build_room(hand_of(5, 5, 8), [4, 4], target="7", pile=1,
                  last_cards=hand_of(7), last_left=4)
move = ai.decide_move(room, "bot")
thrown = {c.id for c in room.players["bot"].hand if c.id in move["cards"]}
check(move["cards"] == [c.id for c in room.players["bot"].hand if c.rank == 8],
      "bluffs away the singleton and keeps the pair", summarise(move))

# One card left and no honest play: worth more risk, because surviving the
# challenge wins the place outright.
big = build_room(hand_of(3), [4, 4], target="7", pile=10, last_cards=hand_of(7), last_left=4)
check(ai.decide_move(big, "bot")["action"] == "play",
      "takes a longer-odds bluff when it is the last card in hand")


# ---- degenerate positions ----------------------------------------------------
check(ai.decide_move(build_room([], [4], target="7", last_cards=hand_of(7)), "bot")["action"]
      == "pass", "an empty hand simply passes")
obs = ai.observe(build_room(hand_of(3, 4), [4], target=None), "bot")
check(ai.should_show(obs) is False, "there is nothing to challenge on a fresh chain")


# ---- table memory: what Shows revealed ---------------------------------------
# A Show flips cards face up for the whole room, so remembering them is what
# every human at the table does. The room keeps the record (so all players share
# one history, and it survives a reconnect), and the bot reads it.

def show_between(room, challenger, defender, cards, declared):
    """Drive a real Show through the room so the memory is built the live way."""
    room.last_play = {"user_id": defender, "cards": list(cards), "declared_rank": declared}
    room.center_pile = list(cards)
    room.target_rank = declared
    result = room.apply_show(challenger)
    room.resolve_show(result)
    return result


room = build_room(hand_of(7, 7, 3), [4, 4], target="7")
res = show_between(room, "bot", "opp0", hand_of(2, 5), "7")
check(res["is_bluff"] and len(room.reveal_log) == 1,
      "a caught bluff is recorded on the room")
check(room.reveal_log[0]["defender"] == "opp0" and room.reveal_log[0]["was_bluff"],
      "the record names who was caught")
check(sorted(room.known_cards.get("opp0", [])) == ["2", "5"],
      "the cards go to whoever picked the pile up, and are remembered there",
      room.known_cards)

# Honesty: no history is 0.5, a caught bluff drops it, an honest showing lifts it.
fresh = ai.observe(build_room(hand_of(3), [4], target="7", last_cards=hand_of(7)), "bot")
check(ai.honesty(fresh, "opp0") == 0.5, "a player nobody has challenged starts at 0.5")
obs = ai.observe(room, "bot")
check(ai.honesty(obs, "opp0") < 0.5, "being caught lying drops their honesty",
      ai.honesty(obs, "opp0"))

honest_room = build_room(hand_of(3, 4), [4, 4], target="7")
show_between(honest_room, "bot", "opp0", hand_of(7, 7), "7")
obs_h = ai.observe(honest_room, "bot")
check(ai.honesty(obs_h, "opp0") > 0.5, "being shown honest raises it",
      ai.honesty(obs_h, "opp0"))

# Reputation nudges a murky read, in the right direction and only so far.
base = build_room(hand_of(3, 4), [4, 4], target="7", pile=2,
                  last_cards=hand_of(7), last_left=6)
plain = ai.bluff_probability(ai.observe(base, "bot"))
liar = build_room(hand_of(3, 4), [4, 4], target="7", pile=2,
                  last_cards=hand_of(7), last_left=6)
liar.reveal_log = [{"defender": "opp1", "was_bluff": True} for _ in range(3)]
suspicious = ai.bluff_probability(ai.observe(liar, "bot"))
check(suspicious > plain, "a player caught lying three times is read as likelier to lie",
      (plain, suspicious))
check(suspicious < 1.0,
      "but reputation alone can never manufacture a certainty the cards deny",
      suspicious)

# Reputation acts on how readily we think they bluff, not on the verdict — the
# cards decide that, so an honest record makes the same claim more believable.
honest_rec = build_room(hand_of(3, 4), [4, 4], target="7", pile=2,
                        last_cards=hand_of(7), last_left=6)
honest_rec.reveal_log = [{"defender": "opp1", "was_bluff": False} for _ in range(3)]
check(ai.bluff_rate(ai.observe(honest_rec, "bot")) < ai.bluff_rate(ai.observe(liar, "bot")),
      "a player with an honest record is modelled as bluffing less often")

# Knowing where copies sit is what lets the bot take a chance: holding two 7s
# and knowing a third sits in another hand leaves only one unaccounted for, so
# a claim of two is impossible rather than merely unlikely.
room = build_room(hand_of(7, 7, 3), [4, 4], target="7", pile=2,
                  last_cards=hand_of(7, 7), last_left=5)
without = ai.bluff_probability(ai.observe(room, "bot"))
room.known_cards = {"opp0": ["7"]}
withmem = ai.bluff_probability(ai.observe(room, "bot"))
check(withmem == 1.0 and without < 1.0,
      "a remembered third 7 turns a likely bluff into a certain one",
      (without, withmem))

# ...and a claim by the very player known to hold them is believed, not accused.
room = build_room(hand_of(7, 3), [4, 4], target="7", pile=2,
                  last_cards=hand_of(7, 7), last_left=5)
room.known_cards = {"opp1": ["7", "7"]}
check(ai.bluff_probability(ai.observe(room, "bot")) < 0.5,
      "a claim from the player known to hold those cards is not challenged")

# Memory fades as soon as that player throws cards, because there is no telling
# which ones went down. Forgetting early is the safe direction.
room = build_room(hand_of(3, 4), [4, 4], target="7")
room.known_cards = {"opp0": ["7", "7"]}
room.apply_play("opp0", hand_of(7)[:1], "7")
check(room.known_cards.get("opp0", []) == ["7"],
      "one card played forgets one remembered card", room.known_cards)
room.apply_play("opp0", hand_of(9, 9)[:2], "9")
check("opp0" not in room.known_cards,
      "and the rest is forgotten once they have played past it", room.known_cards)

# A new deal wipes the table's memory — the cards are all somewhere else now.
room = build_room(hand_of(3, 4), [4, 4], target="7")
room.known_cards = {"opp0": ["7"]}
room.reveal_log = [{"defender": "opp0", "was_bluff": True}]
for uid in ("bot", "opp0", "opp1"):
    room.players[uid].connected = True
room.start_round()
check(not room.known_cards and not room.reveal_log,
      "dealing a fresh round clears the memory")


# ---- it does not hound an honest player ---------------------------------------
# Reported from a real 4-player game: the bot challenged the player ahead of it
# over and over while that player was telling the truth, so every Show fed their
# cards into the bot's own hand and handed them the lead to name the next rank.
# It finished on 36 cards. Three separate faults compounded:
#
#   * the chain-saturation term overrode the direct evidence, reading "most of
#     this pile is lies" as "this player lied" — when the lies were other
#     people's;
#   * the bar to challenge ignored what being wrong costs, staying flat at 0.667
#     whether the pile held two cards or eighteen;
#   * and the odds treated a play as forced, when passing is free — so choosing
#     to play is itself evidence of holding the rank.
#
# The last is the one that matters most, and this is the shape of the bug: as
# the pile grows the bot must get *less* eager, not more.
prev = None
for pile in (2, 6, 10, 14, 18):
    room = build_room(hand_of(*([3] * 9 + [7, 7])), [5, 6], target="7", pile=pile,
                      last_cards=hand_of(7), last_left=6)
    obs = ai.observe(room, "bot")
    check(not ai.should_show(obs, "bot"),
          "an honest opponent is left alone with %d cards in the pile" % pile,
          (ai.bluff_probability(obs), ai.show_threshold(obs)))
    if prev is not None:
        check(ai.show_threshold(obs) >= prev,
              "and the bar to challenge rises rather than falls as the pile grows")
    prev = ai.show_threshold(obs)

# The correction that does it: a volunteered play is evidence of holding, so the
# read must be gentler than the raw "do they even have one?" count.
room = build_room(hand_of(*([3] * 9 + [7, 7])), [5, 6], target="7", pile=2,
                  last_cards=hand_of(7), last_left=6)
obs = ai.observe(room, "bot")
raw = 1.0 - ai._p_at_least(2, obs.unseen_total, 7, 1)   # "probably has no 7"
check(ai.bluff_probability(obs) < raw,
      "playing when it could have passed makes the claim more credible, not less",
      (raw, ai.bluff_probability(obs)))

# None of which softens a claim the cards rule out.
room = build_room(hand_of(7, 7, 7, 3), [5, 6], target="7", pile=18,
                  last_cards=hand_of(7, 7), last_left=6)
check(ai.should_show(ai.observe(room, "bot"), "bot"),
      "an impossible claim is still challenged even on a huge pile")

# And it never challenges its own play, reachable if the turn wraps back round
# before the pile is swept.
room = build_room(hand_of(3, 4), [5, 6], target="7", pile=4, last_cards=hand_of(7))
room.last_play["user_id"] = "bot"
obs = ai.observe(room, "bot")
check(not ai.should_show(obs, "bot"), "it never calls Show on itself")


print("\n%d/%d bluff bot checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
