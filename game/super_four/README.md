# Super 4

## Objective

The objective of the game is to finish with the **lowest total card value** among all players.

At any point during **your own turn**, if you believe your total is the lowest, you may declare **"Stop."**

Once Stop is declared:

* Every remaining player gets **one final turn** until play comes back to the player who declared Stop.
* After that, all cards are revealed.
* If the player who declared Stop has the **lowest total**, they win.
* Otherwise, they lose.

## Setup
* Each player is dealt **4 face-down cards**.
* Each card position is fixed and labeled **1, 2, 3, and 4**.
* Players may look at **only their first two cards** before the game officially begins. Memory is key!

## Normal Turn
1. Draw the top card from the deck (visible to all).
2. Choose to **Keep** the card or **Discard** it.
3. If discarded, and it is a power card (7-13), the power triggers.

## Matching Mechanics
A player can match a discarded card with their own hand or an opponent's hand. This is a real-time reaction. If correct, the matched card is removed (or swapped). If incorrect, the player receives a penalty card.

## Card Powers
Powers activate ONLY when a drawn card is discarded immediately.
* **7 or 8**: Look at any one of your own cards.
* **9 or 10**: Look at one of any opponent's cards.
* **11 or 12**: Blind swap one of your cards with one of an opponent's.
* **13 (King)**: Look at one of your cards and one opponent's card, then optionally swap them.

## Planned Implementation Structure
*   `room.py`: Handles the specific game state (face-down cards, fixed slots, penalty cards, final orbit phase).
*   `powers.py`: Handlers for card powers and targeting logic.
*   `scoring.py`: Specific score evaluation for Super 4 (e.g. Red King is -1).
