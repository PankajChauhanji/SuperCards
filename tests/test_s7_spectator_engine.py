import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game.super_seven.room import Room, STATE_LOBBY, STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.super_seven.settings import DEFAULT_SETTINGS

def test_spectator():
    print("Initializing Room...")
    settings = dict(DEFAULT_SETTINGS)
    settings["max_score"] = 50
    room = Room("TEST", "host", settings)
    
    # Register host and player 1
    room.register_player("host", "HostPlayer")
    room.attach("host", "sid1")
    room.register_player("p1", "Player1")
    room.attach("p1", "sid2")
    
    print("Starting Round...")
    room.start_round()
    
    print(f"Room State: {room.state}")
    print(f"Active Players: {[p.name for p in room.players.values() if not p.is_spectator]}")
    
    # A spectator joins mid-game
    print("Spectator joins...")
    p2 = room.register_player("spec1", "Spectator1")
    if room.state != STATE_LOBBY:
        p2.is_spectator = True
    room.attach("spec1", "sid3")
    
    print(f"Spectator added: {p2.name}, is_spectator={p2.is_spectator}")
    
    # Verify spectator is not in turn order
    assert "spec1" not in room.turn_order
    
    # Admit spectator for next round
    print("Admitting spectator with 10% penalty...")
    p2.pending_join = True
    p2.join_penalty_pct = 10
    
    # Host and P1 play and round ends
    print("Ending Round...")
    room.players["host"].total_score = 10
    room.players["p1"].total_score = 30
    room.players["host"].hand = []
    room.players["p1"].hand = []
    
    room.end_round(None)
    
    print(f"Room State after round: {room.state}")
    print(f"Spectator total score: {p2.total_score} (Expected: ~22 -> avg is 20, +10% = 22)")
    assert p2.total_score == 22
    assert not p2.is_spectator
    assert not p2.pending_join
    
    # Rematch scenario
    print("Resetting for rematch...")
    room.reset_for_rematch()
    print(f"Room State: {room.state}")
    for p in room.players.values():
        assert not p.is_spectator
        assert not p.pending_join
    
    print("All backend logic checks passed successfully!")

if __name__ == '__main__':
    test_spectator()
