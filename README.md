# 🃏 Super Cards

Super Cards is a real-time multiplayer card-game platform built with Flask-SocketIO and vanilla JavaScript. Players can create a room, pick a game, invite friends, and jump into a shared table directly in the browser.

The platform has grown beyond a single game and now serves as a home for multiple card experiences under one consistent lobby, room system, and live gameplay flow.

---

## 🚀 Play it now

[![Play now on Render](https://img.shields.io/badge/PLAY_NOW-Super_Cards-6706ce?style=for-the-badge&logo=render&logoColor=white)](https://super-cards.onrender.com)

> The main live experience now runs at the updated Super Cards URL. Feedback, bug reports, and feature ideas are always welcome.

---

## ✨ What makes Super Cards special

- Real-time multiplayer rooms with instant turn sync and live table updates
- A shared platform layer for lobbies, room lifecycle, and player identity
- Per-game rules and UI modules that stay isolated while sharing the same backend
- Responsive browser-based gameplay with no installation required for casual play
- A growing catalog of card games with a consistent experience across them

---

## 📸 Gameplay preview

| Welcome lobby | Live table |
| :---: | :---: |
| ![Super Cards lobby](static/img/game_images/super_seven_lobby.png) | ![Super Cards table](static/img/game_images/super_seven_game_table.png) |

---

## 🎮 Games available

<div>
  <img src="https://placehold.co/900x500/png?text=Super+Seven+Preview" alt="Super Seven preview" width="100%" />
  <details>
    <summary><strong>Super Seven</strong> — tactical shedding and bold Stop calls</summary>
    <br>
    <p>Play a fast-paced round-based game where you try to shed your hand while keeping your total score low enough to survive the table.</p>
    <ul>
      <li><strong>Core loop:</strong> discard, pair, set, sequence, or match cards to reduce your hand.</li>
      <li><strong>Key twist:</strong> calling Stop can win the round, but it can also backfire if you are not truly lowest.</li>
      <li><strong>Special mechanic:</strong> reaching zero points makes you Safe and removes you from the Stop race for that round.</li>
    </ul>
  </details>
</div>

<div>
  <img src="https://placehold.co/900x500/png?text=Super+Four+Preview" alt="Super Four preview" width="100%" />
  <details>
    <summary><strong>Super Four</strong> — memory, deduction, and hidden-card strategy</summary>
    <br>
    <p>A more cerebral game where players manage four hidden slots, memorize cards, and use powers at the right moment.</p>
    <ul>
      <li><strong>Setup:</strong> each player begins with four face-down cards in fixed positions.</li>
      <li><strong>Turn flow:</strong> draw privately, keep or discard, and try to match your own card values at the table.</li>
      <li><strong>Highlights:</strong> table matches, optional powers, and high-risk Stop decisions shape every round.</li>
    </ul>
  </details>
</div>

<div>
  <img src="https://placehold.co/900x500/png?text=Bluff+Preview" alt="Bluff preview" width="100%" />
  <details>
    <summary><strong>Bluff</strong> — deception, challenge, and table reading</summary>
    <br>
    <p>A bluff-heavy game built around one locked rank per round and a constant tension between truth and deception.</p>
    <ul>
      <li><strong>Objective:</strong> be the first player to get rid of all your cards.</li>
      <li><strong>Core mechanic:</strong> players declare a rank while placing cards face down and hope no one challenges them.</li>
      <li><strong>Drama:</strong> Show calls can flip the round instantly, turning an ordinary play into a bold gamble.</li>
    </ul>
  </details>
</div>

---

## 🧰 Features

- Real-time multiplayer gameplay powered by Flask-SocketIO
- Room-based game creation with a smooth lobby experience
- Shared platform services for connection handling, room state, and player identity
- Server-authoritative rules, timers, and turn flow for fairness
- Multiple game modes under one umbrella project
- Custom-generated card art with in-house SVG assets
- Reconnection and host-hand-off support for more reliable live sessions

---

## 🏗️ Project structure

```text
super_cards/
├── app.py                  # Flask + SocketIO entry point
├── config.py               # Runtime and deployment configuration
├── game/                   # Core game logic and per-game engines
│   ├── core/               # Shared cards, player, registry, and room utilities
│   ├── bluff/              # Bluff game logic
│   ├── super_four/         # Super Four game logic
│   └── super_seven/        # Super Seven game logic
├── sockets/                # Shared WebSocket handlers and gameplay routing
├── static/                 # CSS, JavaScript, images, and generated card assets
├── templates/              # Page templates and per-game views
├── tests/                  # Game logic, scoring, socket, and engine tests
├── tools/                  # Asset generation and development helpers
├── Procfile                # Gunicorn startup command
├── render.yaml             # Render deployment blueprint
└── requirements.txt        # Python dependencies
```

---

## ⚙️ Quick start

Requires Python 3.10+ (3.12+ recommended).

```bash
# 1. Clone the repository
git clone https://github.com/PankajChauhanji/SuperSevenCards.git
cd SuperSevenCards

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the app
python app.py
```

Open http://localhost:5000 in your browser. To test multiplayer locally, open a second browser window or another browser profile so you can join the same room as a second player.

---

## 🌐 Deployment notes

This project is a stateful WebSocket app, so it should be deployed with a single worker to preserve room state correctly.

```bash
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT app:app
```

A Render blueprint is included for simple hosting. The app is designed to run as one process so live rooms remain consistent and players stay in the same shared session.

---

## 🃏 Card assets

Card faces are generated locally as SVGs rather than pulled from a third-party card pack.

```bash
python tools/generate_cards.py
```

This writes updated card artwork into the static image folders used by the client UI.

---

## 🔍 Development notes

- Keep game-specific rules and UI isolated inside their own modules
- Prefer server-authoritative validation for turn legality and scoring
- Use the shared core for common room and player lifecycle behavior
- If you run into multiplayer issues, verify that the app is not using multiple workers

---

## 📄 License

Copyright (c) 2024 PankajChauhanji. All Rights Reserved.

Viewing of this source code is permitted for reference purposes only. Copying, modification, distribution, or use of this code in any form is strictly prohibited without explicit written permission from the author.
