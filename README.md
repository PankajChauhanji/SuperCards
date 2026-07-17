# 🃏 Super Seven Cards

A real-time multiplayer card-game platform built with **Flask-SocketIO** and **vanilla JS**. Create one room, choose a game, and play with friends from the same site.

Currently included:

- **Super Seven** — a face-up shedding game of sets, sequences, matching, and Stop.
- **Super Four** — a hidden-information memory game with fixed card slots, powers, fast table matches, and Stop.

---

### 🚀 Play it Live

[![Live Demo](https://img.shields.io/badge/PLAY_NOW-Live_on_Render-6706ce?style=for-the-badge&logo=render&logoColor=white)](https://super-cards.onrender.com)

> This is the **multi-game platform** deployment (Super Seven + Super Four). The original
> Super-Seven-only game remains live at [super-seven.onrender.com](https://super-seven.onrender.com),
> deployed from `master`.

> **💡 Feedback welcome!** If you find a bug or have a feature idea, open an **Issue** — the game is actively evolving.

---

## 📸 Gameplay Preview

| Welcome Lobby | Live Game Session |
| :---: | :---: |
| ![Game Lobby](static/img/game_images/super_seven_lobby.png) | ![Game Table](static/img/game_images/super_seven_game_table.png) |

---
## 📖 Super Seven rule book

### 🎯 1. Game Objective
The goal is to shed the points in your hand. When you believe your remaining cards have a lower total value than every other active opponent, call **Stop** to end the round. If your cumulative score across multiple rounds exceeds the score cap, you are eliminated. The last player standing wins!

### 🃏 2. Card Values & Deck
In Super Seven, **suits do not matter**. Only the rank of the card is used for gameplay and scoring.
| Card | Point Value |
|---|---|
| **Ace** | 1 (Ace is strictly low) |
| **2 – 10** | Face value |
| **Jack** | 11 |
| **Queen** | 12 |
| **King** | 13 |

### 📜 3. General Game Rules
- Every player is dealt **7 cards** at the start of a round.
- Turns proceed in order. You have a **40-second timer** to make your move, or the game will auto-play for you.
- Three consecutive timeouts will result in you being kicked from the game.

### 🖐️ 4. Player Options on a Turn
When it is your turn, you must select one of the following actions. (No-draw actions are always highly strategic!)

- **Single Discard:** Throw any 1 card, then **draw 1 card** from the deck.
- **Pair:** Throw 2 cards of the *exact same rank*, then **draw 1 card** from the deck.
- **Set (No Draw):** Throw 3 or 4 cards of the *exact same rank*. You do **not** need to draw a card.
- **Sequence (No Draw):** Throw 3 or more cards in a consecutive run (e.g., 3-4-5). Ace is strictly low (A-2-3 is valid, but Q-K-A is not). You do **not** need to draw a card.
- **Match (Free Play):** You may throw any cards that *match* the rank of the cards currently visible in the center pile from the previous player's throw. You can match *any* previous throw (even a single card). You do **not** need to draw a card. *(Note: This behavior is configurable in `config.py` via `MATCH_REQUIRES_DRAW`).*

### 🛡️ 5. Going Safe (The Zero-Point Zone)
If you manage to empty your hand entirely using a Set, Sequence, or Match, your round score locks at **0 points**. You are now completely **Safe** and sit out for the remainder of the round. 

### 🛑 6. Calling Stop (Ending the Round)
You can call **Stop** to immediately end the round, but it comes with strict conditions:
- **Timing:** You can *only* call Stop at the **start** of your turn, and you **cannot** call it during the very first orbit of the round (everyone must have played at least once).
- **Winning:** To successfully call Stop, your hand total must be **strictly lower** than the hand totals of all other *active* players. If successful, you win the round and receive a score discount (default: -5 points).
- **The Trap (Penalty):** If any active player ties or beats your hand total, you are **caught**. You will absorb your hand total *plus* a heavy penalty (default: +40 points).
- **The Safe Player Exemption:** Players who are **Safe (0 points)** are completely ignored when determining if a Stop caller wins or gets caught. You only compete against players who are still holding cards!

### ☠️ 7. Elimination & Winning the Game
Round scores accumulate over time. Once your cumulative total crosses the **Score Cap (default: 100 points)**, you are eliminated. If multiple players cross the cap on the same round, the one with the lowest total score survives. The last player standing wins the entire game.

---

## 🧠 Super Four rule book

### Objective and setup

Finish with the lowest total of card values. Each player starts with **four face-down cards** in fixed slots. At the beginning of a round, each player may privately memorise slots 1 and 2 until the host starts play, with a server-enforced maximum of **30 seconds**.

### Card values

Ace is 1; number cards use their face value; Jack, Queen, and King are 11, 12, and 13. Both red Kings — **King of Hearts** and **King of Diamonds** — are worth **−1**.

### Turn flow

1. **Draw privately.** Only the active player sees the drawn card.
2. Choose one action:
   - **Keep:** replace one of your slots. The new card stays hidden; the replaced card is discarded face-up.
   - **Discard:** put the drawn card face-up on the center. A 7–King power activates only when the drawn card is directly discarded.
   - **Match your own card:** if a chosen slot matches the drawn rank, both are discarded; a wrong guess gives you a hidden penalty card.
3. Every face-up table discard opens a **table-match window** (up to 10 seconds; it closes early
   as soon as the next player starts their turn).

### Table matches

Any player, including the discarder, may react during the match window. Suit does not matter — only rank must match.

- Only the FIRST throw received by the server counts — right or wrong, it resolves the window and everyone else is too late.
- A player may throw multiple matching cards from their own and/or opponents' slots.
- For each opponent card removed, the reactor chooses one of their own cards to transfer into that exact opponent slot.
- A wrong first throw returns all selected cards to their original slots, adds a hidden penalty card to the reactor's last slot/index, and closes the window.

### Powers

Powers occur only when the card drawn from the deck is immediately discarded:

- **7 or 8:** privately peek at one of your own cards.
- **9 or 10:** privately peek at one opponent card.
- **Jack or Queen (11 or 12):** blind-swap one of your cards with an opponent card.
- **King (13):** privately look at one of your cards and one opponent card, then optionally swap them.

### Stop, rounds, and scoring

Call **Stop** only at the start of your turn and only after every player has taken one turn. Each other player receives one final turn, then cards are revealed.

- Lowest hand each round: `win_score` (default **−3**).
- Other players: `loss_score` (default **+1**).
- A Stop caller who is not lowest: `penalty_score` (default **+3**).
- At `exit_score` (default **10**) a player is eliminated to spectator status.
- Missing `timeout_limit` turns (default **2**) benches a player to spectator; the host can admit them back for a later round, like any spectator.
- The game normally lasts `rounds` (default **5**); the lowest cumulative score wins.

Super Four is server-authoritative: hidden card faces are never broadcast in public state, and preview/peek faces are delivered only to the eligible player.

---

## ✨ Features

- **Real-time multiplayer** — WebSocket-powered with Flask-SocketIO, all actions sync instantly across all players
- **Game picker** — rooms choose Super Seven or Super Four at creation time
- **Variant isolation** — shared platform services, with rules and UI bundles owned by each game
- **Complete game loops** — lobby, dealing, turn play, Stop, scoring, elimination, and multi-round rotation
- **Server-authoritative rules** — validation, timers, private state, and race arbitration run on the server
- **Super Four memory mechanics** — private draws, host-controlled preview, card powers, penalties, and real-time matching
- **Automatic turn timer** — per-game turn timers with auto-play; players can be removed after repeated timeouts
- **Elimination & tiebreaker** — players eliminated at the score cap; survivor tiebreaker when multiple players hit it simultaneously
- **Reconnection support** — players rejoin seamlessly at any stage using stable client-generated identities
- **Host migration** — if the host disconnects, another player automatically takes over
- **Custom card faces** — all card SVGs are generated in-house, not a third-party pack

---

## 🏗️ Project Structure

```
super_seven_cards/
├── app.py                  # Flask + SocketIO entrypoint
├── config.py               # Runtime/deployment configuration
├── game/                   # Pure domain logic (networking-free)
│   ├── core/               # Cards, players, registry, manager, shared states
│   ├── super_seven/        # Super Seven room, rules, scoring, AI, settings
│   └── super_four/         # Super Four room, powers, scoring, AI, settings
├── sockets/                # Shared WebSocket handlers and per-game gameplay handlers
│   └── gameplay/           # super_seven.py and super_four.py
├── static/
│   ├── css/style.css       # UI styles
│   ├── js/core/            # Shared browser utilities
│   ├── js/seven/           # Super Seven client bundle
│   ├── js/four/            # Super Four client bundle
│   └── img/cards/          # Generated SVG card faces
├── templates/games/        # Per-game table, branding, and script templates
├── static/rules/           # Per-game English and Hindi rule pages
├── tests/                  # Engine, privacy, scoring, power, and socket checks
├── tools/
│   └── generate_cards.py   # SVG card face generator
├── Procfile                # Gunicorn startup command
├── render.yaml             # Render Blueprint deployment spec
└── requirements.txt        # Python dependencies
```

---

## 🛠️ Quick Start (Local)

Requires Python 3.10+ (3.12 recommended).

```bash
# 1. Clone and enter the repo
git clone https://github.com/PankajChauhanji/SuperSevenCards.git
cd SuperSevenCards

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
python app.py
```

Open **http://localhost:5000**. Select a game when creating a room. To test multiplayer locally, open a second browser window in **Incognito** — it generates a separate player identity.

---

## ⚙️ Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session secret — override in production | `dev placeholder` |
| `CORS_ORIGINS` | Socket.IO allowed origins | `*` |
| `PORT` | Port to bind | `5000` |
| `FLASK_DEBUG` | Enable hot reload (`1` to enable) | `0` |

---

## 🌐 Deployment

This is a stateful WebSocket app with in-memory room state — always run **exactly one worker**:

```bash
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT app:app
```

A `render.yaml` blueprint is included for one-click deploys on Render. Railway and Fly.io work equally well.

> ⚠️ **Never use multiple workers.** Room state lives in memory — multiple workers split players across isolated processes and break the game.

---

## 🃏 Regenerating Card SVGs

All card faces are custom generated SVGs — no third-party image packs. Regenerate any time:

```bash
python tools/generate_cards.py    # writes to static/img/cards/*.svg
```

---

## 🧩 Architecture

```
Browser (vanilla JS + Socket.IO client)
              ↕  WebSockets
Flask-SocketIO (single-process, eventlet)
              ↕
Game registry → Super Seven or Super Four room engine
```

- **Shared core** (`game/core/`) owns room registration and common lifecycle contracts.
- **Variant domain layers** (`game/super_seven/`, `game/super_four/`) are decoupled from networking and easy to test.
- **Socket layer** (`sockets/`) dispatches gameplay actions by `game_type`.
- **Client identities** are stable and client-generated — survives page refreshes and reconnections mid-game

---

## 🔍 Troubleshooting

**Players end up in empty isolated rooms**
Your server is running more than one worker. Enforce `-w 1` in your Gunicorn command.

**Cold start delay on first load**
Render's free tier sleeps after 15 minutes of inactivity. The first visitor after a sleep window waits ~1 minute for the instance to wake up.

**Gunicorn version issues**
The project pins `gunicorn==23.0.0`. Versions 26+ removed bundled eventlet support and cause startup errors if upgraded blindly.

---

## 📄 License

Copyright (c) 2024 PankajChauhanji. All Rights Reserved.

Viewing of this source code is permitted for reference purposes only. Copying, modification, distribution, or use of this code in any form is strictly prohibited without explicit written permission from the author.
