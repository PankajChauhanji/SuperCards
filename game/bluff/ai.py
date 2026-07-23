import random
from typing import Dict, Any
from game.core.cards import rank_code

def bot_delay() -> float:
    return random.uniform(1.8, 3.5)

def decide_move(room, bot_id: str) -> Dict[str, Any]:
    bot = room.players[bot_id]
    hand = bot.hand
    
    if not hand:
        return {"action": "pass"}
    
    # 1. Start a new chain
    if not room.last_play:
        # Truthful start
        c = random.choice(hand)
        target_rank = c.rank
        declared = rank_code(target_rank)
        
        play_cards = [card for card in hand if card.rank == target_rank][:4]
        return {
            "action": "play",
            "cards": [card.id for card in play_cards],
            "declared_rank": declared
        }
        
    # 2. Respond to an existing chain
    target_rank_code = room.target_rank
    
    # 20% chance to challenge right away
    if random.random() < 0.2:
        return {"action": "show"}
        
    matching_cards = [c for c in hand if rank_code(c.rank) == target_rank_code]
    
    if matching_cards:
        # 80% chance to play truth if we have the cards
        if random.random() < 0.8:
            return {
                "action": "play",
                "cards": [c.id for c in matching_cards][:random.randint(1, min(4, len(matching_cards)))],
                "declared_rank": target_rank_code
            }
            
    # Otherwise, pass or bluff
    if random.random() < 0.5:
        return {"action": "pass"}
        
    # Bluff
    bluff_cards = random.sample(hand, random.randint(1, min(3, len(hand))))
    return {
        "action": "play",
        "cards": [c.id for c in bluff_cards],
        "declared_rank": target_rank_code
    }
