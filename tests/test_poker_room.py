import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Poker room engine: blinds, betting rules, streets, showdown, pots, busts, game end.

Scenarios are taken from docs/poker_rules.md wherever the doc gives one, so the
doc's own worked example is executed rather than merely described.
"""
import random

from game.core.cards import Card, build_deck
from game.core.states import STATE_LOBBY, STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.poker.room import Room, PHASE_BETTING, PHASE_RUNOUT, PREFLOP, FLOP, TURN, RIVER
from game.poker.settings import DEFAULT_SETTINGS
from game.poker.visibility import public_card_ids

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)


def raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return True
    return False


_R = {"A": 1, "J": 11, "Q": 12, "K": 13}


def cards(text):
    out = []
    for tok in text.split():
        out.append(Card(_R.get(tok[:-1]) or int(tok[:-1]), tok[-1]))
    return out


def make_room(n=3, **settings):
    s = dict(DEFAULT_SETTINGS)
    s.update(settings)
    room = Room("TEST", "A", s)
    for uid in "ABCDEFGH"[:n]:
        room.register_player(uid, "P" + uid).connected = True
    room._pick_first_button = lambda eligible: eligible[0]   # A deals round 1
    return room


def rig(room, holes, board):
    """Replace the dealt cards: fixed hole cards and a fixed run of board cards."""
    room.hole = {u: cards(t) for u, t in holes.items()}
    b = cards(board)
    taken = {(c.rank, c.suit) for c in b} | {(c.rank, c.suit) for h in room.hole.values() for c in h}
    rest = [c for c in build_deck(1) if (c.rank, c.suit) not in taken]
    burns, filler = rest[:3], rest[3:]
    pops = [burns[0]] + b[0:3] + [burns[1], b[3], burns[2], b[4]]
    room.deck = filler + list(reversed(pops))


def total_coins(room):
    """Coins in stacks plus, mid-round, coins in the pot (once paid, the pot is in stacks)."""
    in_pot = sum(room.contributed.values()) if room.state == STATE_IN_TURN else 0
    return sum(room.chips.values()) + in_pot


S = DEFAULT_SETTINGS

# =====================================================================
# Blinds & positions
# =====================================================================
room = make_room(3)
room.start_round()
check(room.state == STATE_IN_TURN and room.street == PREFLOP and room.phase == PHASE_BETTING,
      "start: round 1 is in pre-flop betting")
check(room.blinds() == (5_000, 10_000), "default 1,000,000 coins -> blinds 5,000 / 10,000 (1%)")
check(room.button == "A" and room.sb_id == "B" and room.bb_id == "C",
      "3 players: SB and BB are the two seats left of the button")
check(room.bets == {"A": 0, "B": 5_000, "C": 10_000}, "blinds are posted")
check(room.current_turn_id() == "A", "pre-flop the player left of the big blind acts first")
check(all(len(room.hole[u]) == 2 for u in "ABC"), "everyone gets two hole cards")
check(room.round_number == 1 and room.chips["A"] == 1_000_000, "everyone starts with the starting coins")
legal = room.legal_actions("A")
check(legal["to_call"] == 10_000 and not legal["check"] and legal["min_to"] == 20_000,
      "facing the big blind: call 10,000, min raise to 20,000")
check(room.legal_actions("B") is None, "only the player on turn has actions")
check(raises(room.act, "B", "call"), "acting out of turn is refused")

# =====================================================================
# The rules doc's worked example, executed
# =====================================================================
room = make_room(3)
room.start_round()
rig(room, {"A": "AS KS", "B": "7D 7C", "C": "QH 9C"}, "KD 7H 2S 3C JS")
start_total = total_coins(room)

room.act("A", "raise", 30_000)
check(room.legal_actions("B")["min_to"] == 50_000, "after a raise to 30,000 the next min raise is to 50,000")
check(raises(room.act, "B", "raise", 40_000), "a raise to 40,000 (an increase of only 10,000) is refused")
room.act("B", "call")
room.act("C", "call")
check(room.street == FLOP and [c.face for c in room.board] == ["KD", "7H", "2S"],
      "everyone called -> the flop K-7-2 is dealt")
check(sum(room.contributed.values()) == 90_000, "pot is 90,000 after pre-flop")
check(room.current_turn_id() == "B", "post-flop the first live player left of the button acts first")
room.act("B", "check")
room.act("C", "check")
room.act("A", "bet", 50_000)
room.act("B", "raise", 150_000)
room.act("C", "fold")
room.act("A", "call")
check(room.street == TURN and sum(room.contributed.values()) == 390_000, "turn: pot is 390,000")
room.act("B", "bet", 200_000)
room.act("A", "call")
check(room.street == RIVER and sum(room.contributed.values()) == 790_000, "river: pot is 790,000")
room.act("B", "check")
room.act("A", "check")
check(room.state == STATE_ROUND_END, "after the river checks through, the round ends")
check(room.chips == {"A": 620_000, "B": 1_410_000, "C": 970_000},
      "showdown pays Ben 790,000: Asha 620,000 / Ben 1,410,000 / Chirag 970,000")
check(total_coins(room) == start_total, "no coin created or destroyed")
award = room.last_result["awards"][0]
check(award["winners"] == ["B"] and award["hand_name"] == "Three of a Kind, Sevens",
      "the summary names Ben's Three of a Kind, Sevens")
check(set(room.last_result["hands"]) == {"A", "B"}, "only hands that reached showdown are in the summary")
check(room.last_result["deltas"] == {"A": -380_000, "B": 410_000, "C": -30_000}, "per-player win/loss")
pub = public_card_ids(room)
check(all(c.id in pub for c in room.hole["A"] + room.hole["B"] + room.board),
      "showdown hands and the board are public")
check(not any(c.id in pub for c in room.hole["C"]), "Chirag folded: his cards stay hidden, even at round end")
payload = room.round_end_payload()
check([r["user_id"] for r in payload["rows"]] == ["B", "C", "A"] and payload["seconds_left"] == 30,
      "round summary lists coins left, most first, with the 30s auto-start countdown")
room.start_round()
check(room.button == "B" and room.round_number == 2, "the button moves one seat clockwise")

# =====================================================================
# Big blind option, check-through, and folding
# =====================================================================
room = make_room(3)
room.start_round()
room.act("A", "call")
room.act("B", "call")
legal = room.legal_actions("C")
check(legal["check"] and legal["raise"], "big blind's option: may check or raise when everyone just called")
room.act("C", "check")
check(room.street == FLOP and room.current_turn_id() == "B", "BB checks -> flop; SB acts first")
check(room.legal_actions("B")["min_to"] == 10_000 and room.legal_actions("B")["verb"] == "bet",
      "first bet of a street: minimum one big blind")
room.act("B", "check"); room.act("C", "check"); room.act("A", "check")
check(room.street == TURN, "everyone checks -> the next street")

# Everyone folds to the big blind: blinds go to the BB, nothing is revealed.
room = make_room(3)
room.start_round()
room.act("A", "fold")
room.act("B", "fold")
check(room.state == STATE_ROUND_END and room.last_result["fold_win"], "everyone folds -> round ends")
check(room.chips == {"A": 1_000_000, "B": 995_000, "C": 1_005_000}, "BB wins the small blind")
check(room.board == [] and room.shown == set() and room.last_result["hands"] == {},
      "uncontested: no more board, no cards shown")
check(public_card_ids(room) == set(), "nothing at all is public after a fold win")

# Uncalled bet is returned, never won.
room = make_room(3)
room.start_round()
room.act("A", "allin")
room.act("B", "fold")
room.act("C", "fold")
check(room.chips["A"] == 1_015_000, "an all-in nobody called returns; A wins just the blinds")

check(raises(make_room(3).act, "A", "fold"), "acting before the deal is refused")
room = make_room(3)
room.start_round()
check(raises(room.act, "A", "check"), "cannot check when facing a bet")
check(raises(room.act, "A", "raise", 5_000_000), "cannot raise more than your stack")
check(raises(room.act, "A", "dance"), "unknown actions are refused")

# =====================================================================
# Short all-in does not re-open the betting
# =====================================================================
room = make_room(3)
room.start_round()
room.chips["B"] = 35_000   # B has posted 5,000 of a 40,000 stack
room.act("A", "raise", 30_000)          # full raise of 20,000
room.act("B", "allin")                  # to 40,000: only +10,000, an incomplete raise
check(room.current_bet == 40_000 and room.min_raise == 20_000,
      "short all-in raises the bet but not the minimum raise")
room.act("C", "call")
legal = room.legal_actions("A")
check(legal["to_call"] == 10_000 and not legal["raise"],
      "A already acted and faces less than a full raise: call or fold only")
check(raises(room.act, "A", "raise", 80_000), "A's re-raise is refused")

# ... but a full raise after it does re-open the action.
room = make_room(4)
room.start_round()            # button A, SB B, BB C, first to act D
room.chips["A"] = 35_000      # A will be the short all-in
room.act("D", "raise", 30_000)
room.act("A", "allin")        # to 35,000: incomplete
room.act("B", "raise", 80_000)   # full raise
room.act("C", "fold")
check(room.legal_actions("D")["raise"], "a later full raise re-opens betting to D")

# =====================================================================
# Heads-up order
# =====================================================================
room = make_room(2)
room.start_round()
check(room.button == "A" and room.sb_id == "A" and room.bb_id == "B",
      "heads-up: the button posts the small blind")
check(room.current_turn_id() == "A", "heads-up: the button acts first pre-flop")
room.act("A", "call")
room.act("B", "check")
check(room.street == FLOP and room.current_turn_id() == "B", "heads-up: the big blind acts first after the flop")

# =====================================================================
# All-in runout and side pots
# =====================================================================
room = make_room(2)
room.start_round()
rig(room, {"A": "AS AD", "B": "KS KD"}, "2C 7H 9S 4D 3C")
room.act("A", "allin")
room.act("B", "call")
check(room.phase == PHASE_RUNOUT and room.current_turn_id() is None,
      "both all-in pre-flop -> runout, nobody's turn")
check(room.shown == {"A", "B"} and all(c.id in public_card_ids(room) for c in room.hole["B"]),
      "runout: both hands turn face up for everyone")
check(room.step_runout() and room.street == FLOP and len(room.board) == 3, "runout deals the flop")
room.step_runout(); room.step_runout()
check(room.state == STATE_GAME_END and room.chips["A"] == 2_000_000,
      "aces hold: A wins everything and the game ends (one player has all the coins)")
st = room.standings()
check([(r["user_id"], r["place"], r["net"]) for r in st] == [("A", 1, 1_000_000), ("B", 2, -1_000_000)],
      "standings: winner first with +1,000,000 net, the busted player second")
check(room.players["B"].eliminated and room.bust_log[0]["round"] == 1, "B busted in round 1")

# Three-way: a short all-in with the best hand wins only the main pot.
room = make_room(3)
room.start_round()      # A button, B SB, C BB
room.chips["A"] = 100_000
rig(room, {"A": "AS AD", "B": "KS KD", "C": "QS QD"}, "2C 7H 9S 4D 3C")
room.act("A", "allin")                  # A: 100,000
room.act("B", "raise", 300_000)
room.act("C", "call")
check(room.street == FLOP, "B and C still have coins: betting continues on the flop")
room.act("B", "check"); room.act("C", "check")
room.act("B", "check"); room.act("C", "check")
room.act("B", "check"); room.act("C", "check")
check(room.state == STATE_ROUND_END, "round over after the river")
awards = room.last_result["awards"]
check([(a["amount"], a["winners"]) for a in awards] == [(300_000, ["A"]), (400_000, ["B"])],
      "main pot 300,000 to A (best hand), side pot 400,000 to B (best of B and C)")
check(room.chips == {"A": 300_000, "B": 1_100_000, "C": 700_000}, "stacks after the side pot")

# Split pot: the board plays for both.
room = make_room(2)
room.start_round()
rig(room, {"A": "2C 3D", "B": "4H 5S"}, "AS KD QC JH 10S")
room.act("A", "call"); room.act("B", "check")
for _ in range(3):
    room.act("B", "check"); room.act("A", "check")
check(room.chips == {"A": 1_000_000, "B": 1_000_000} and len(room.last_result["awards"][0]["winners"]) == 2,
      "board straight for both -> the pot is split evenly")

# =====================================================================
# Game end, ranking, ties
# =====================================================================
room = make_room(3, rounds=1)
room.start_round()
room.act("A", "fold"); room.act("B", "fold")
check(room.state == STATE_GAME_END, "rounds=1: the game ends after one round")
st = room.standings()
check([r["user_id"] for r in st] == ["C", "A", "B"] and st[0]["net"] == 5_000,
      "ranked by coins: C (+5,000), A, B")
check(room.game_end_payload()["winner"] == "C", "game-end payload names the winner")

# Ties share a place. Rigged cards, not a random deal: an unrigged version of
# this check guessed at the outcome and failed ~3% of runs, when B and C split
# and all three players happened to finish on exactly the same coins.
def tie_game(holes, board):
    r = make_room(3, rounds=1)
    r.start_round()                       # A button (posts nothing), B SB, C BB
    rig(r, holes, board)
    r.act("A", "fold"); r.act("B", "call"); r.act("C", "check")
    for _ in range(3):
        r.act("B", "check"); r.act("C", "check")
    return r

room = tie_game({"A": "2C 3D", "B": "4H 5S", "C": "6C 7D"}, "AS KD QC JH 10S")
st = room.standings()
check(room.chips == {"A": 1_000_000, "B": 1_000_000, "C": 1_000_000}
      and [r["place"] for r in st] == [1, 1, 1],
      "the board plays for B and C: everyone ends level and all three share 1st")

room = tie_game({"A": "2C 3D", "B": "AH AD", "C": "7C 2H"}, "AS KD 9C 5H 4S")
st = room.standings()
check([(r["user_id"], r["place"]) for r in st] == [("B", 1), ("A", 2), ("C", 3)],
      "different coins, different places: B (won), A (folded, level), C (lost)")

room = tie_game({"A": "AH AD", "B": "KH KD", "C": "KC KS"}, "2S 7D 9C 4H 3S")
st = room.standings()
check(room.chips["B"] == room.chips["C"] == 1_000_000 and room.chips["A"] == 1_000_000
      and all(r["place"] == 1 for r in st),
      "B and C split with equal kings while A folded: all level, all share 1st")

# =====================================================================
# Blinds double
# =====================================================================
room = make_room(2, blind_up_every=2)
blinds = []
for _ in range(5):
    room.start_round()
    blinds.append(room.blinds()[1])
    room.act(room.current_turn_id(), "fold")
check(blinds == [10_000, 10_000, 20_000, 20_000, 40_000], "blinds double every 2 rounds")
check(make_room(2, starting_chips=12_345).blinds() == (61, 123), "blinds round down to whole coins")

# =====================================================================
# Timeouts, sitting out, coming back
# =====================================================================
room = make_room(3, timeout_limit=2)
room.start_round()
info = room.force_timeout("A")
check(info["action"] == "fold" and "A" in room.folded and not info["sat_out"],
      "timeout facing a bet folds")
room.act("B", "call")
info = room.force_timeout("C")
check(info["action"] == "check" and room.street == FLOP, "timeout with a free check checks")
room = make_room(3, timeout_limit=2)
room.start_round()
room.force_timeout("A"); room.act("B", "fold")     # A: 1 timeout
room.start_round()                                  # button B -> A is BB... rotate
cur = room.current_turn_id()
room.players[cur].timeout_count = 1
info = room.force_timeout(cur)
check(info["sat_out"] and cur in room.sitting_out, "timeouts in a row reach the limit -> sat out")
check(room.come_back(cur) and room.players[cur].timeout_count == 0 and cur not in room.sitting_out,
      "I'm back clears it")
room = make_room(3)
room.start_round()
room.players["A"].timeout_count = 2
room.act("A", "call")
check(room.players["A"].timeout_count == 0, "a real action resets the timeout count")

# =====================================================================
# Leaving mid-round
# =====================================================================
room = make_room(3)
room.start_round()
room.remove_participant("A")                       # A is on turn
check("A" not in room.players and room.current_turn_id() == "B", "current player quits -> turn moves on")
room.act("B", "fold")
check(room.state == STATE_ROUND_END and room.chips["C"] == 1_005_000, "the round still settles normally")
room.remove_participant("B")
check(room.state == STATE_GAME_END and room.winner == "C",
      "a quit that leaves one player with coins ends the game")

room = make_room(2)
room.start_round()
room.remove_participant("B")
check(room.state == STATE_GAME_END and room.chips["A"] == 1_010_000,
      "heads-up quit mid-round: the other player takes the pot and the game")

# =====================================================================
# Late joiners
# =====================================================================
room = make_room(3)
room.start_round()
room.act("A", "fold"); room.act("B", "fold")
late = room.register_player("Z", "Late")
late.connected = True
late.is_spectator = True
late.pending_join = True
late.join_penalty_pct = 20
room.start_round()
expected = (3_000_000 // 3) * 80 // 100
check("Z" in room.in_hand and room.chips["Z"] + room.bets["Z"] == expected and room.received["Z"] == expected,
      "admitted spectator joins next round with 80% of the average stack (20% penalty)")

# =====================================================================
# Rematch
# =====================================================================
room = make_room(2, rounds=1)
room.start_round()
room.act("A", "fold")
room.reset_for_rematch()
check(room.state == STATE_LOBBY and room.round_number == 0 and room.chips == {} and room.seats == [],
      "rematch resets to the lobby")
room.start_round()
check(room.chips["A"] + room.bets["A"] == 1_000_000, "a rematch re-deals the starting coins")

# =====================================================================
# Private view: your cards, the round they belong to, your hand's name
# =====================================================================
room = make_room(2)          # hand hints default OFF
room.start_round()
rig(room, {"A": "4S 4H", "B": "AS KH"}, "KD 7C 2S 9H 3D")
pv = room.private_view("A")
check(pv["round_number"] == 1 and [c["face"] for c in pv["cards"]] == ["4S", "4H"],
      "private view carries your two cards and the round they belong to")
check(pv["hand_name"] is None and pv["hand_rank"] is None,
      "hand hints off (the default): no hand name or row is sent at all")
room.settings["hand_hints"] = 1
pv = room.private_view("A")
check(pv["hand_name"] == "Pair of Fours" and pv["hand_rank"] == 8,
      "hints on, pre-flop: a pocket pair is named, on the One Pair row")
pvb = room.private_view("B")
check(pvb["hand_name"] == "High Card, Ace" and pvb["hand_rank"] == 9,
      "hints on, pre-flop: two unpaired cards are High Card (so hints never look switched off)")
room.act("A", "call"); room.act("B", "check")
check(room.hand_label("A") == "One Pair, Fours" and room.hand_label("B") == "One Pair, Kings",
      "from the flop on, the label is your best five with the board")

# Every category lands on its own row of the rankings card (0 = Royal Flush).
ROWS = [
    ("AS KS", "QS JS 10S 2D 3C", 0), ("9H 8H", "7H 6H 5H KD 2C", 1),
    ("QC QD", "QH QS 4D 2C 3H", 2), ("8S 8D", "8H KC KS 2D 3C", 3),
    ("AD JD", "9D 6D 2D KC 3S", 4), ("10C 9D", "8S 7H 6C 2D KS", 5),
    ("7C 7D", "7S KH 2D 9C 4S", 6), ("JH JC", "4S 4D AC 9H 2S", 7),
    ("10S 10H", "KD 6C 3S 2D 8H", 8), ("AC QD", "8S 5H 3C 2D 9S", 9),
]
bad_rows = []
for hole, board, want in ROWS:
    r = make_room(2, hand_hints=1)
    r.start_round()
    r.hole["A"] = cards(hole)
    r.board = cards(board)[:3]
    got3 = r.hand_rank_row("A")
    r.board = cards(board)
    got = r.hand_rank_row("A")
    if got != want:
        bad_rows.append("%s+%s -> %s (want %s)" % (hole, board, got, want))
check(not bad_rows, "every hand category maps to its rankings-card row%s"
      % ("" if not bad_rows else " (%s)" % bad_rows[0]))
check(room.private_view("Z")["cards"] == [] and room.hand_label("Z") is None,
      "someone not dealt in has nothing private")
check(all(p["received"] == 1_000_000 for p in room.public_players()),
      "public players carry what each was given (the seat gauge's full mark)")

# =====================================================================
# Random legal play: invariants hold and every game finishes
# =====================================================================
rng = random.Random(7)
bad = []
finished = 0
for game_no in range(150):
    n = rng.randint(2, 7)
    room = make_room(n, rounds=rng.randint(1, 12), starting_chips=rng.choice([10_000, 200_000, 1_000_000]))
    room._pick_first_button = lambda eligible: rng.choice(eligible)
    total = n * room.settings["starting_chips"]
    room.start_round()
    for _ in range(4000):
        if room.state == STATE_GAME_END:
            break
        if room.state == STATE_ROUND_END:
            room.start_round()
            continue
        if room.phase == PHASE_RUNOUT:
            room.step_runout()
            continue
        uid = room.current_turn_id()
        legal = room.legal_actions(uid)
        options = ["fold", "allin"] + (["check"] if legal["check"] else ["call"])
        if legal["raise"]:
            options += ["raise"] * 2
        action = rng.choice(options)
        amount = rng.randint(legal["min_to"], legal["max_to"]) if action == "raise" else None
        room.act(uid, action, amount)
        if total_coins(room) != total:
            bad.append("game %d: coins %d != %d" % (game_no, total_coins(room), total))
            break
        if any(v < 0 for v in room.chips.values()):
            bad.append("game %d: negative stack" % game_no)
            break
        pub = public_card_ids(room)
        folded_leak = [u for u in room.folded if any(c.id in pub for c in room.hole.get(u, []))]
        if folded_leak:
            bad.append("game %d: folded hand public" % game_no)
            break
    if room.state == STATE_GAME_END:
        finished += 1
        st = room.standings()
        if sum(r["chips"] for r in st) != total:
            bad.append("game %d: final chips do not add up" % game_no)
check(not bad, "random play: coins conserved, no negative stacks, folded hands never public%s"
      % ("" if not bad else " (%s)" % bad[0]))
check(finished == 150, "all 150 random games reached the end (%d/150)" % finished)

print("\n%d/%d room checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
