# Poker (No-Limit Texas Hold'em) — Rules & Gameplay Guide

The Super Cards version of the world's most popular poker game. Every player starts with the
same pile of coins. Over a fixed number of rounds the coins move around the table, and when
the game ends **whoever holds the most coins wins**.

> **Status:** v1 rules, agreed with the owner on 2026-10-05. Wherever standard poker leaves
> a choice open, or where we simplified for online play, the choice is marked
> **[decision]** so it can be revisited. The answers to the review questions are recorded
> at the end.
>
> **Play money only.** Coins have no cash value. They cannot be bought, sold, transferred or
> exchanged for anything, and they do not carry over from one game to the next.

---

## 📋 Table of Contents
1. [Words used in this guide](#-words-used-in-this-guide)
2. [Objective](#-objective)
3. [Setup & host settings](#%EF%B8%8F-setup--host-settings)
4. [The dealer button & blinds](#-the-dealer-button--blinds)
5. [How a round plays](#-how-a-round-plays)
6. [Your options on your turn](#-your-options-on-your-turn)
7. [Bet sizes — the No-Limit rules](#-bet-sizes--the-no-limit-rules)
8. [How a round ends](#-how-a-round-ends)
9. [Hand rankings](#-hand-rankings)
10. [The pot, side pots & split pots](#-the-pot-side-pots--split-pots)
11. [Running out of coins](#-running-out-of-coins)
12. [End of the game & medals](#-end-of-the-game--medals)
13. [Timer, sitting out & leaving](#%EF%B8%8F-timer-sitting-out--leaving)
14. [Joining a game in progress](#-joining-a-game-in-progress)
15. [Hidden information (fair play)](#-hidden-information-fair-play)
16. [A full round, worked through](#-a-full-round-worked-through)
17. [Review decisions](#-review-decisions-2026-10-05)
18. [Showing amounts](#-showing-amounts)

---

## 📖 Words used in this guide

| Word | Meaning |
| :--- | :--- |
| **Game** | The whole session, from the first deal until medals are given out. |
| **Round** | One deal of the cards, from the blinds to the moment the pot is paid out. Poker players also call this a *hand*. The host chooses how many rounds a game has. |
| **Stage** | One of the four betting turns inside a round: **Pre-flop, Flop, Turn, River**. |
| **Hole cards** | Your two private cards. Only you see them. |
| **Board** | The shared face-up cards in the middle (up to 5). Everyone uses them. |
| **Stack** | The coins you have in front of you that are not yet in the pot. |
| **Pot** | The coins bet so far in this round, which the winner(s) collect. |
| **In the round** | You have not folded. You can still win this round's pot. |

---

## 🎯 Objective

Finish the game holding **as many coins as possible**. You win coins by winning pots: either
everyone else gives up (folds) against your bets, or you show the best five-card hand at the
end of a round.

---

## ⚙️ Setup & host settings

* **Players:** 2 to **20**, the same table size as Super Seven and Bluff. **[decision]** One
  deck is enough even at a full table: 20 players × 2 hole cards + 5 board cards + 3 burn
  cards = 48 of the 52 cards.
* **Deck:** one standard 52-card deck, no Jokers, reshuffled before every round. Poker is
  always played with a single deck, so unlike the other games this is not a setting.
* **Computer players** can be seated from the lobby, as in the other games. They play by
  exactly these rules.

The host sets these in the lobby before starting:

| Setting | Default | Allowed range | What it does |
| :--- | :--- | :--- | :--- |
| **Starting coins** | **1,000,000** | 10,000 – 100,000,000 | Every player starts the game with exactly this many coins. |
| **Rounds** | **10** | 1 – 100 | The game ends after this many rounds (or earlier if one player wins everything). |
| **Turn timer** | **30 s** | 15 – 120 s | How long you have to act on your turn. |
| **Timeout limit** | **3** | 1 – 10 | Turns missed in a row before you are automatically sat out. |
| **Blinds double every** | **0** (off) | 0 – 50 rounds | If set, both blinds double every this many rounds. 0 keeps them fixed. |
| **Hand hints** | **Off** | On / Off | For the whole table: when on, each player privately sees the name of the hand they hold ("Two Pair, Kings and Sevens"), and its row lights up in the Hand rankings card. |

**Blinds are set automatically from the starting coins. [decision]**

* **Big blind = 1% of starting coins**, and **small blind = half the big blind**.
* With the default 1,000,000 coins, that means a **small blind of 5,000** and a **big blind
  of 10,000**.
* Every player therefore starts with 100 big blinds, the normal "deep" stack in poker, at
  any coin amount the host picks. It also means one fewer setting to get wrong.
* Blinds are whole coins, rounded down.
* Blinds stay the same for the whole game, unless the host turns on **Blinds double every**.
  *Example:* with that setting at 3, rounds 1–3 play at 5,000 / 10,000, rounds 4–6 at
  10,000 / 20,000, and so on.

---

## 🔘 The dealer button & blinds

* **Dealer button.** One player holds the button, which marks the "dealer" seat for the
  round. A random player gets it for round 1. **[decision]** After each round it moves one
  seat clockwise, skipping anyone who has no coins left.
* **Blinds.** Before any cards are dealt, the two players to the left of the button put in
  forced bets, so every pot has something worth winning:
  * **Small blind (SB):** the first player clockwise from the button.
  * **Big blind (BB):** the next player after that.
* **Heads-up (2 players):** the button posts the small blind and the other player posts the
  big blind. The button acts **first** pre-flop and **last** on every later stage. This is
  the standard heads-up rule.
* **Short of the blind:** a player who cannot cover their blind puts in everything they have
  and is **all-in** (see Side pots).
* **[decision]** We use a simple *moving button*. If a player busts, the button and blinds
  simply move on to the next players who still have coins. There is no "dead button".

---

## 🔄 How a round plays

1. **Blinds** are posted.
2. **Deal.** Each player gets **2 hole cards**, face down, visible only to them.
3. **Pre-flop betting.**
   * The first player to act sits left of the big blind.
   * The blinds count as bets, so everyone else must call, raise, or fold.
   * **The big blind's option:** if everyone only calls, the big blind may still check or
     raise when action reaches them.
4. **The Flop.** 3 cards are dealt face up on the board, then a betting stage follows.
5. **The Turn.** A 4th board card, then a betting stage.
6. **The River.** A 5th and final board card, then the last betting stage.
7. **Showdown.** If two or more players are still in the round, hands are revealed and the
   best five-card hand wins the pot.

**Who acts first:** pre-flop, it is the player left of the big blind. On the Flop, Turn and
River, it is the first player still in the round clockwise from the button. Play always
moves clockwise.

**When a betting stage is over:** every player still in the round has either put in the same
amount as the highest bet, or is all-in. Everyone must also have had a chance to act since
the last full raise. If nobody bets in a stage, it ends once everyone has checked.

**Burn cards:** as in live poker, one card is discarded face down, never shown to anyone,
before the Flop, the Turn and the River. **[decision]** This has no effect on fairness,
because the server shuffles, but it keeps the deck behaving exactly like a real one.

---

## 🃏 Your options on your turn

The server only offers the options that are legal right now.

| Option | When you can use it | What happens |
| :--- | :--- | :--- |
| **Fold** | Always | You give up this round. Coins you already put in stay in the pot. Your cards are never shown. |
| **Check** | Nobody has bet in this stage, or you are the big blind and nobody raised pre-flop | You pass the action without betting, and stay in the round. |
| **Call** | Someone has bet more than you have put in this stage | You match the current bet. If your stack is smaller than the bet, calling puts you all-in. |
| **Bet** | Nobody has bet yet in this stage (Flop, Turn, River) | You make the first bet of the stage. |
| **Raise** | Someone has already bet in this stage | You increase the bet that others must match. |
| **All-in** | Always, if you have coins | You put your whole stack in. It counts as a bet, raise or call depending on the size (see below). |

* **Fold when you could check:** this is allowed, but the game will warn you that checking is
  free. **[decision]**
* **Check-raise is allowed:** you may check, and then raise if someone bets after you.

---

## 📏 Bet sizes — the No-Limit rules

"No-Limit" means you may bet **any amount up to your whole stack** at any time. There is no
cap. There are minimums:

* **Minimum bet:** one big blind. With default settings that is 10,000.
* **Minimum raise:** a raise must increase the current bet by **at least the size of the
  previous bet or raise in this stage**, and never by less than one big blind.
  * *Example:* the big blind is 10,000. A raises to 30,000, an increase of 20,000. The
    smallest re-raise is now to 50,000, which is another increase of 20,000.
* **Maximum:** your whole stack.
* **Amounts:** any whole number of coins is allowed. **[decision]** The bet slider steps in
  small-blind units to make choosing easy.

**All-in for less than a full raise.** If a player goes all-in, and that only raises the bet
by *less* than a minimum raise:

* Players who have **not yet acted** in this stage may fold, call or raise as normal.
* Players who **have already acted** may only **call or fold**, and cannot re-raise.
* The exception: if, by the time action comes back to them, the bet has gone up by at least
  one full raise in total, they may raise again.

This stops a small all-in from being used to re-open betting unfairly. It is the standard
rule in every poker room.

**Table stakes:** you can only bet the coins in your stack. Nobody can add coins during a
round, and there are no re-buys.

---

## 🏁 How a round ends

A round ends in one of three ways:

1. **Everyone else folds.**
   * The last player left wins the whole pot immediately.
   * The remaining board cards are **not** dealt.
   * The winner's cards are **not** shown. **[decision]** There is no "show anyway" option
     in v1.
2. **Showdown after the River.**
   * Every hand still in the round is revealed to the whole table.
   * The best five-card hand wins.
   * **[decision]** Online, we reveal all of them automatically rather than asking each
     player whether to show or throw away their cards. This keeps the game moving.
3. **All-in, nobody left to bet.**
   * If at most one player in the round still has coins behind (everyone else is all-in),
     no more betting is possible.
   * All remaining hands are turned face up straight away, and the rest of the board is
     dealt out, one stage at a time, for the drama.
   * Then the pot is paid as in a showdown.

**Using the board.** Your hand is the **best five cards out of the seven available**: your 2
hole cards plus the 5 board cards. You may use both hole cards, one, or none. If the board
itself is your best five, you are "playing the board".

### The round summary

When the pot is paid, a **round summary** pops up for everyone, like the round-end screen in
Super Seven. It shows:

* who won each pot, and with which hand;
* the hands that were shown;
* every player's **coins left**, and how much they won or lost this round.

The **host** has a **Start next round** button. If the host does not press it, the next round
starts automatically after **30 seconds**. Everyone else sees the countdown.

After the **last round**, or once one player has won all the coins, the game goes straight to
the medal podium instead of the round summary.

---

## 🏆 Hand rankings

From strongest to weakest. A higher category always beats a lower one.

| # | Hand | Example | Description |
| :---: | :--- | :--- | :--- |
| 1 | **Royal Flush** | A♠ K♠ Q♠ J♠ 10♠ | A-K-Q-J-10, all the same suit. The best possible hand. |
| 2 | **Straight Flush** | 9♥ 8♥ 7♥ 6♥ 5♥ | Five cards in sequence, all the same suit. |
| 3 | **Four of a Kind** | Q♣ Q♦ Q♥ Q♠ 4♦ | Four cards of the same rank. |
| 4 | **Full House** | 8♠ 8♦ 8♥ K♣ K♠ | Three of one rank plus a pair of another. |
| 5 | **Flush** | A♦ J♦ 9♦ 6♦ 2♦ | Five cards of the same suit, not in sequence. |
| 6 | **Straight** | 10♣ 9♦ 8♠ 7♥ 6♣ | Five cards in sequence, mixed suits. |
| 7 | **Three of a Kind** | 7♣ 7♦ 7♠ K♥ 2♦ | Three cards of the same rank. |
| 8 | **Two Pair** | J♥ J♣ 4♠ 4♦ A♣ | Two different pairs. |
| 9 | **One Pair** | 10♠ 10♥ K♦ 6♣ 3♠ | Two cards of the same rank. |
| 10 | **High Card** | A♣ Q♦ 8♠ 5♥ 3♣ | None of the above. Your highest card plays. |

**Aces** count **high** (above the King) and also **low**, but only in the straight
A-2-3-4-5, called the "wheel". That is the *lowest* straight. A straight cannot wrap around
the Ace: Q-K-A-2-3 is **not** a straight.

**When two players have the same kind of hand**, compare in this order:

| Hand | Decided by |
| :--- | :--- |
| Straight / Straight Flush | The highest card of the sequence (a wheel's highest card is the 5). |
| Four of a Kind | The rank of the four, then the fifth card. |
| Full House | The rank of the three, then the rank of the pair. |
| Flush / High Card | The highest card, then the next highest, and so on through all five. |
| Three of a Kind | The rank of the three, then the two remaining cards, highest first. |
| Two Pair | The higher pair, then the lower pair, then the fifth card. |
| One Pair | The pair, then the three remaining cards, highest first. |

The remaining cards used to break a tie are called **kickers**.

* **Suits never break a tie.** A spade flush is no better than a heart flush of the same
  ranks.
* If the best five cards are exactly equal, the players **split** that pot.
* Only five cards ever count. A sixth or seventh card never breaks a tie.

---

## 💰 The pot, side pots & split pots

**Main pot and side pots.** When a player is all-in, they can only win from each other
player as much as they themselves put in. Any extra betting between the players who still
have coins goes into a separate **side pot**, which the all-in player cannot win.

> **Example.** A has 100,000 and goes all-in. B and C each have 500,000 and both bet
> 300,000.
> * **Main pot:** 100,000 from each of A, B and C = **300,000**. A, B and C can all win it.
> * **Side pot:** the extra 200,000 from each of B and C = **400,000**. Only B and C can win
>   it.
>
> At showdown each pot is awarded separately. If A has the best hand, A wins the main pot,
> and the side pot goes to whichever of B or C is better. A can win the main pot while
> losing nothing more than the 100,000 they put in.

* There can be several side pots, one for each different all-in amount.
* **Folded players' coins stay in the pot** they put them into. Folded players simply cannot
  win anything.
* **Uncalled bet returned.** If you bet or raise and nobody matches the full amount, the part
  nobody matched is returned to you. It is never "won".
* **Split pots.** If players tie for a pot, it is divided equally between them. Any coin left
  over after the equal division goes to the tied winner sitting closest to the button,
  counting clockwise.

---

## 💸 Running out of coins

* A player whose stack is **0 at the end of a round** has **busted**. They are out of the
  game and watch the rest as a spectator.
* There are no re-buys and no loans. Being all-in is not the same as busting: if you are
  all-in and win, you are back in.

---

## 🥇 End of the game & medals

**The game ends** as soon as either of these happens:

1. **The last round has been played.** The game ends right after that round's pot is paid.
2. **Only one player still has coins.** That player has won every coin on the table, and the
   game ends immediately, whatever round it is.

**Final ranking:**

1. **Players still holding coins**, from **most coins to fewest**. All players start with the
   same coins, so this is the same as ranking by how much each player won.
2. **Then busted players**, ranked by when they busted: the **later** you went out, the
   higher you finish. If two players bust in the same round, the one who started that round
   with more coins ranks higher.

**[decision]** Players who left the game are not ranked. This matches how quitting works in
Bluff.

* **[decision]** Players with exactly the same final coins share the place.
* **Medals:** 🥇 1st, 🥈 2nd, 🥉 3rd, on the shared winner podium.
* The podium shows each player's **final coins** and their **net result** against what they
  started with, for example **2,450,000 (+1,450,000)** or **320,000 (−680,000)**.

---

## ⏱️ Timer, sitting out & leaving

* **Turn timer.** You have **30 seconds** by default (the host's *Turn timer* setting) to act
  on your turn.
* **When the timer runs out,** the game acts for you: it **checks** if checking is free,
  otherwise it **folds**. This counts as one timeout.
* **Sitting out. [decision]**
  * After the *Timeout limit* (3 by default) **in a row**, you are **sat out**.
  * While sat out, you stay at the table and are still dealt in, and your blinds are still
    posted when they are due. But the game checks or folds for you the instant action
    reaches you, so the table never waits on you.
  * Press **"I'm back"** to play again from your next turn.
  * Any action you take yourself resets your timeout count.
  * Being sat out does not protect your stack: the blinds keep costing you.
* **Disconnected players** are treated exactly the same. Their timer runs as normal, and they
  can reconnect at any time and pick up where they left off.
* **Leaving mid-game. [decision]**
  * If you quit, your current round is folded.
  * Coins you already put in stay in the pot.
  * The rest of your stack leaves the game with you and goes to nobody.
  * You are not on the final podium.
* **Host leaving:** host duties pass to another player, as in every other game.
* Computer players never time out.

---

## 🚪 Joining a game in progress

* Anyone who joins after the game has started watches as a **spectator**.
* **[decision]** The host may let them in. They then join at the start of the next round
  with the **average stack** of the players still holding coins, rounded down to a whole
  big blind. This matches how Super Four seats late joiners at the table's average.
* The admit window's **penalty %** reduces that stack. For example, a 20% penalty seats
  them with 80% of the average. They always get at least one big blind.
* Their net result on the podium is measured against the coins they were given, not the
  original starting coins.

---

## 🔒 Hidden information (fair play)

The server decides everything and only ever tells each player what they are allowed to see.

| Information | Who can see it |
| :--- | :--- |
| Your hole cards | **Only you**, from the deal until the round ends |
| Another player's hole cards | **Nobody**, unless that hand is revealed at a showdown or an all-in runout |
| A folded hand | **Nobody, ever**, not even after the round |
| An uncontested winner's cards | **Nobody** (see "Everyone else folds") |
| The deck order and burn cards | **Nobody, ever** |
| Board cards, stacks, bets, pots, who folded / is all-in / is sat out, button & blinds, the action history | **Everyone**, including spectators |
| Hands turned up in an all-in runout or at showdown | **Everyone**, from the moment they are turned up |

Computer players follow the same rules. A bot knows only its own two cards and the public
information, never anyone else's cards or what is coming next in the deck.

---

## 🧪 A full round, worked through

Three players with default settings (SB 5,000 / BB 10,000), each with 1,000,000. **Asha**
has the button, **Ben** is the small blind, **Chirag** is the big blind.

1. **Blinds.** Ben posts 5,000 and Chirag posts 10,000. Pot: 15,000.
2. **Deal.** Asha has A♠ K♠. Ben has 7♦ 7♣. Chirag has Q♥ 9♣.
3. **Pre-flop.**
   * Asha acts first (left of the big blind) and **raises to 30,000**.
   * Ben **calls**, adding 25,000 to his 5,000 blind.
   * Chirag **calls**, adding 20,000.
   * Pot: 90,000.
4. **Flop:** K♦ 7♥ 2♠.
   * Ben is first to act after the button and **checks**.
   * Chirag **checks**.
   * Asha, holding a pair of Kings, **bets 50,000**.
   * Ben has three 7s. He **raises to 150,000**.
   * Chirag **folds**.
   * Asha **calls**.
   * Pot: 390,000.
5. **Turn:** 3♣. Ben **bets 200,000**, and Asha **calls**. Pot: 790,000.
6. **River:** J♠. Ben **checks**, and Asha **checks**.
7. **Showdown.** Ben's **Three of a Kind, 7s** beats Asha's **One Pair, Kings**. Ben wins
   790,000.

**After the round:** Ben has 1,410,000, Asha has 620,000 and Chirag has 970,000 (still
1,000,000 coins each on average). The button moves to Ben for round 2.

---

## ✅ Review decisions (2026-10-05)

The answers to the review questions on the first draft:

| Question | Decision |
| :--- | :--- |
| What happens between rounds? | A **round summary** popup with every player's coins left. The host presses **Start next round**, or it starts by itself after **30 seconds**. |
| Rising blinds? | Yes, as the **Blinds double every** setting. **Off by default.** |
| How to show big numbers? | Short **K / M** on the table (1.2M, 350K), with the full number on hover or tap. The Hindi rules page uses **Lakh / Crore** in its prose. |
| Table size? | Up to **20** players. |
| Default rounds? | **10**, and the host can change it. |
| Late joiners? | Let in by the host at the next round, with the **average stack**. |
| Hand-name help? *(2026-10-06)* | A **host setting for the whole table**, off by default. The rankings card is always available as static reference. With hints off the server does not send anyone their hand name. |

## 💬 Showing amounts

Chip amounts on the table are shortened so they fit on a seat: **5K, 350K, 1.2M, 12.5M**.
Hover over one (or long-press it on a phone) to see the full amount. The round summary and
the podium use the same short form, again with the full amount on hover.

The game screens are in English, so the table always uses K / M. The Hindi rules page writes
amounts the Indian way in its prose (10 लाख, 1 करोड़).

| Amount | On the table | In the Hindi rules |
| :--- | :--- | :--- |
| 5,000 | 5K | 5 हज़ार |
| 350,000 | 350K | 3.5 लाख |
| 1,000,000 | 1M | 10 लाख |
| 12,500,000 | 12.5M | 1.25 करोड़ |
