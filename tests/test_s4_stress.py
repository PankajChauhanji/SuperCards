import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super 4 randomized stress: full games must always make progress.

Plays complete games through the Room API with randomized (sensible and
senseless) actions and asserts after every step that:
  * the number of physical cards is conserved (nothing duplicated or lost),
  * every phase always offers a way forward (no freezes / stuck states),
  * the game reaches GAME_END within a bounded number of steps.
"""
import random

from game.super_four.room import (
    Room, PHASE_DRAW, PHASE_DECIDE, PHASE_POWER, PHASE_MATCH, PHASE_PREVIEW,
)
from game.super_four.settings import DEFAULT_SETTINGS
from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)


def total_cards(r):
    n = len(r.draw_pile) + len(r.discard_pile)
    if r.center is not None:
        n += 1
    if r.drawn is not None:
        n += 1
    for cards in r.slots.values():
        n += sum(1 for c in cards if c is not None)
    return n


def occupied(r, owner):
    return [i for i, c in enumerate(r.slots.get(owner, [])) if c is not None]


def play_one_game(seed):
    random.seed(seed)
    players = ["P%d" % i for i in range(random.choice([2, 2, 3, 4, 5]))]
    s = dict(DEFAULT_SETTINGS)
    s["match_window"] = random.choice([0, 5, 10])
    s["rounds"] = 3
    s["exit_score"] = random.choice([6, 10])
    s["preview_seconds"] = 3
    r = Room("T", players[0], s)
    for u in players:
        r.register_player(u, u).connected = True
    r.start_round()

    steps = 0
    while r.state in (STATE_IN_TURN, STATE_ROUND_END):
        steps += 1
        if steps > 20000:
            return "no progress after 20000 steps (seed %d, phase %s)" % (seed, r.phase)
        if total_cards(r) != 52:
            return "card conservation broken: %d cards (seed %d, phase %s)" % (
                total_cards(r), seed, r.phase)

        if r.state == STATE_ROUND_END:
            r.start_round()
            continue
        if r.phase == PHASE_PREVIEW:
            r.begin_play()
            continue

        cur = r.current_turn_id()

        if r.phase == PHASE_MATCH:
            roll = random.random()
            if roll < 0.30:
                r.match_window.deadline = 0
                if not r.expire_match_window():
                    return "match window refused to expire (seed %d)" % seed
            elif roll < 0.55:
                # A genuine matching throw if one exists anywhere.
                target = None
                for owner in players:
                    for i in occupied(r, owner):
                        if r.slots[owner][i].rank == r.match_card.rank:
                            target = (owner, i)
                            break
                    if target:
                        break
                actor = random.choice(players)
                if target is None:
                    r.match_window.deadline = 0
                    r.expire_match_window()
                elif target[0] == actor:
                    r.react_match(actor, [{"owner": actor, "slot": target[1]}], [])
                else:
                    give = next((i for i in occupied(r, actor)), None)
                    if give is None:
                        r.match_window.deadline = 0
                        r.expire_match_window()
                    else:
                        r.react_match(
                            actor, [{"owner": target[0], "slot": target[1]}],
                            [{"target_owner": target[0], "target_slot": target[1],
                              "from_slot": give}])
            elif roll < 0.80:
                # A blind (often wrong) throw, plus some garbage requests.
                actor = random.choice(players)
                occ = occupied(r, actor)
                r.react_match(actor, [{"owner": actor, "slot": 99}], [])       # reject
                r.react_match(actor, "garbage", [])                            # reject
                if occ:
                    r.react_match(actor, [{"owner": actor, "slot": occ[0]}], [])
                else:
                    r.match_window.deadline = 0
                    r.expire_match_window()
            else:
                # The next player just starts their turn.
                r.draw(r.next_player_id())
            continue

        if r.phase == PHASE_POWER:
            by = r.pending_power["by"]
            rank = r.pending_power["rank"]
            own = occupied(r, by)
            opps = r._opponents_with_cards(by)
            resolved = False
            if rank in (7, 8) and own:
                resolved = r.power_peek_own(by, random.choice(own)) is not None
            elif rank in (9, 10) and opps:
                o = random.choice(opps)
                resolved = r.power_peek_opp(by, o, random.choice(occupied(r, o))) is not None
            elif rank in (11, 12) and own and opps:
                o = random.choice(opps)
                resolved = r.power_blind_swap(
                    by, random.choice(own), o, random.choice(occupied(r, o))) is not None
            elif rank == 13 and own and opps:
                o = random.choice(opps)
                look = r.power_king_look(by, random.choice(own), o, random.choice(occupied(r, o)))
                if look is not None:
                    resolved = r.power_king_decide(by, random.random() < 0.5) is not None
            if not resolved and not r.power_skip(by):
                return "power neither resolvable nor skippable (seed %d, rank %d)" % (seed, rank)
            continue

        if r.phase == PHASE_DRAW:
            if r.first_orbit_complete and r.stop_caller is None and random.random() < 0.06:
                if r.call_stop(cur) is not None:
                    continue
            if r.draw(cur) is None and r.state == STATE_IN_TURN and r.phase == PHASE_DRAW:
                return "draw impossible but the round kept going (seed %d)" % seed
            continue

        if r.phase == PHASE_DECIDE:
            roll = random.random()
            own = occupied(r, cur)
            if roll < 0.30 and own:
                r.keep(cur, random.choice(own))
            elif roll < 0.50 and own:
                r.match_own(cur, random.choice(own))
            else:
                r.discard(cur)
            continue

        return "unknown phase %r (seed %d)" % (r.phase, seed)

    if r.state != STATE_GAME_END:
        return "game ended in unexpected state %s (seed %d)" % (r.state, seed)
    return None


failures = []
for seed in range(30):
    err = play_one_game(seed)
    if err:
        failures.append(err)
check(not failures, "30 randomized full games complete without freezes or card leaks"
      + ("".join("\n       " + f for f in failures)))

print("\n%d/%d Super 4 stress checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
