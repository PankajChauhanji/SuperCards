# Bluff (Same-Rank / Pass Variation) — Rules & Gameplay Guide

A highly strategic, fast-paced card game of deception, psychological warfare, and deduction. In this variation (frequently played in South Asia), a single rank is locked in for an entire round. Players must either match the declared rank, bluff, or strategically pass to survive.

---

## 📋 Table of Contents
1. [Objective](#-objective)
2. [Setup](#%EF%B8%8F-setup)
3. [Core Gameplay Mechanics](#-core-gameplay-mechanics)
4. [The Actions: Play vs. Pass](#-the-actions-play-vs-pass)
5. [The "Show" (Challenging)](#-the-show-challenging)
6. [Clearing the Table (The Full Pass)](#-clearing-the-table-the-full-pass)
7. [Winning the Game](#-winning-the-game)
8. [Advanced Strategy Tips](#-advanced-strategy-tips)
9. [Development Plan (Implementation Steps)](#-development-plan-implementation-steps)

---

## 🎯 Objective
The primary goal is to be the **first player to successfully discard all cards** from your hand.

---

## ⚙️ Setup
*   **Players:** Optimal for 3 to 6 players.
*   **The Deck:** A standard 52-card deck (Jokers are removed).
*   **The Deal:** Deal all cards out clockwise as evenly as possible. It is perfectly fine if some players end up with one card more than others.

---

## 🔄 Core Gameplay Mechanics

The game is played in **Rounds**. 
*   Unlike standard "Cheat/BS" where the rank shifts sequentially (Aces, 2s, 3s...), in this version, **one rank is locked for the entire round** (e.g., everyone must play "7s").
*   A round begins when a player sets a "target rank" and ends only when a challenge (**"Show"**) occurs, or when all players consecutively pass.

---

## 🃏 The Actions: Play vs. Pass

### 1. Starting a Round (The Lead-Off)
The active player initiates the round by choosing any rank from their hand. They place 1 to 4 cards **face down** in the center pile and declare the quantity and the rank.
> **Example:** Player A throws 2 cards face down and announces: *"Two 7s."*

### 2. Succeeding Turns (The Same-Rank Lock)
Play moves clockwise. The next player must play the exact same rank (in this case, 7s). On your turn, you have two options:

#### **Option A: Play Cards**
*   Place 1 to 4 cards face down on the center pile.
*   Declare that they match the current target rank (e.g., *"One 7"* or *"Two 7s"*). 
*   **The Deception:** You do *not* have to tell the truth. You can throw random cards (like a Jack and a 3) while claiming they are 7s.

#### **Option B: Pass**
*   If you do not have cards of the target rank, or if you do not want to risk bluffing, you can declare **"Pass"**.
*   Your turn is skipped, and the action moves to the next player clockwise.
*   *Note:* Passing does **not** knock you out of the round permanently. If the turn circle comes back to you and the pile hasn't been cleared or challenged, you can play or pass again.

---

## 🔍 The "Show" (Challenging)

If a player suspects that the person who *just* played lied about their cards, they can call **"Show"** before the next action is taken.

*   **Who can call?** Only the **immediate next active player** has the power to call "Show" on the player who just laid down cards.
*   **How is it resolved?** Only the **exact cards that the active player just threw** are flipped over and revealed to everyone. The rest of the table pile remains face down.

### Challenge Outcomes:

| Scenario | Outcome | Penalty / Reward | Next Lead-Off |
| :--- | :--- | :--- | :--- |
| **Player was lying** *(Bluff caught)* | **Challenger Wins** | The bluffing player must pick up **their thrown cards PLUS the entire table pile**. | The **Challenger** starts the next round with a new rank. |
| **Player told the truth** *(False accusation)* | **Defender Wins** | The challenger must pick up **the defender's cards PLUS the entire table pile**. | The **Defender** starts the next round with a new rank. |

---

## 🧹 Clearing the Table (The Full Pass)

If a player starts a rank and the turn rotates all the way around the table back to them with **every other player passing in succession**:
1.  The round ends immediately.
2.  All cards currently on the table are **swept away and discarded face down** into a "dead pile". These cards are permanently out of play.
3.  The active player who initiated the round (or the player whose turn it is now) gets to **start a completely fresh round** by declaring any new rank of their choice.

---

## 🏆 Winning the Game
The first player to discard their last card wins! 
*   *Crucial Rule:* A player's final cards can still be challenged. If they throw their last cards and the next player calls **"Show"**, the game is not over until the challenge is resolved. 
*   If the winner lied, they pick up the pile and must keep playing. If they told the truth (or if no one calls "Show"), they are officially declared the winner.

---

## 💡 Advanced Strategy Tips

*   **The Strategic Pass:** You don't have to play even if you have the target rank. If the pile is dangerously large, passing is a safe way to let other players take the risk of bluffing and getting caught.
*   **The "Accidental" Truth:** Occasionally play honestly on your lead-off turns. Establishing yourself as an honest player makes it significantly easier to pull off a 4-card bluff later in the game.
*   **Card Counting:** Keep track of how many cards of a specific rank have already been played or are in your own hand. If you hold three 9s and someone claims to play three 9s, they are mathematically guaranteed to be bluffing.

---

## 🛠️ Development Plan (Implementation Steps)

Because the underlying shared platform (Lobby, Socket connection, Player management, basic UI, and Deck dealing) is already fully operational, adding the Bluff game simply requires hooking a new logic module into the existing registry.

### Step 1: Registry and Configurations
*   **Action:** Add `bluff` to `game/core/registry.py`.
*   **Action:** Create `game/bluff/settings.py` (define default timers, timeouts, etc.).
*   **Action:** Create the static HTML rule files (`static/rules/bluff/en.html`).

### Step 2: Backend Game Engine (`game/bluff/room.py`)
*   **State Required:** 
    *   `target_rank`: The locked rank for the current round (1-13, or `None` if starting fresh).
    *   `center_pile`: List of all cards currently in the center.
    *   `last_play`: Details of the immediately preceding play (who threw, which exact cards, claimed quantity).
    *   `pass_count`: Counter tracking consecutive passes.
    *   `dead_pile`: Cards permanently removed from the game after a full table pass.
*   **Core Methods to Implement:**
    *   `apply_play(user_id, card_ids, declared_rank)`: Process a player throwing 1-4 cards. Updates `last_play`, resets `pass_count`, advances turn.
    *   `apply_pass(user_id)`: Skip turn. Increment `pass_count`. If `pass_count == active_players - 1`, sweep the `center_pile` to `dead_pile` and grant the next turn a fresh start.
    *   `apply_show(user_id)`: The challenger triggers a reveal of `last_play`. Verify truthfulness. Assign the `center_pile` to the loser as a penalty. Set the winner as the next turn leader. Reset round state.
    *   `public_view(user_id)`: Return the sanitized state (center pile count, current target rank, whose turn it is, but hide other players' cards and the center pile's true faces).

### Step 3: Backend Socket Layer (`sockets/gameplay/bluff.py`)
*   **Action:** Register new event handlers:
    *   `on("bluff_play")`: Call `room.apply_play()`.
    *   `on("bluff_pass")`: Call `room.apply_pass()`.
    *   `on("bluff_show")`: Call `room.apply_show()`.
*   **Action:** Handle broadcasting the resulting `state` updates back to the room. Broadcast transient events (like `toast` messages for "Player X called Show! It was a Bluff!").

### Step 4: Frontend UI (`static/js/bluff/game.js` & `templates/bluff.html`)
*   **UI Components:**
    *   **Action Panel:** 
        *   If it's a fresh round: Show a rank selector (dropdown or 13 buttons) so the player can choose the `target_rank`. Show a [Throw Cards] button.
        *   If the round is active: Show the current `target_rank`. Show [Throw Cards], [Pass], and [Show] (if applicable to the current player).
    *   **Table View:** Render the center pile as a stack of face-down cards. Display the declared rank prominently.
    *   **Show Animation:** When a "Show" is called, animate flipping the `last_play` cards face up for a few seconds before sweeping the pile to the loser.
*   **Integration:** Bind UI buttons to emit the corresponding `bluff_play`, `bluff_pass`, and `bluff_show` socket events.

### Step 5: Testing
*   **Action:** Write unit tests for `game/bluff/room.py` to ensure "Show" resolves correctly and "Pass" clears the table accurately. Ensure no information leaks in `public_view`.