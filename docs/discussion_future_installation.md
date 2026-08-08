# Discussion — Future Installation, Offline Play, Ads & Accounts

> ⚠️ **THIS IS A DISCUSSION, NOT A PLAN.**
>
> Nothing in this document is committed, scheduled, or approved. It is a record of an
> exploratory conversation held on **2026-08-08** about directions the project *could*
> take. It is deliberately kept so the analysis (especially the cost estimates and the
> hosting gotchas) doesn't have to be re-derived later.
>
> **Do not treat any section here as a roadmap.** The actual roadmap is
> `PLATFORM_PLAN.md` + `todos.md`.

---

## Decisions actually taken from this discussion

Everything else below is exploratory. Only these three lines are real:

| Topic | Decision |
|---|---|
| **Mobile packaging** | ✅ **Go with TWA** (Trusted Web Activity, built via Bubblewrap). Current focus. |
| **User accounts / data** | ❌ **Skipped.** Not storing user data for now. No auth, no DB. |
| **Offline play & ads** | ⏸️ **Deferred.** Not being built. Notes retained below for later. |

Because offline play and AdMob are both off the table, **TWA is a valid choice** — the
objections to it recorded below only apply if those two requirements come back.

---

## Starting context

Facts established about the codebase at the time of this discussion:

- All game state is **server-side and authoritative**; the browser is a thin renderer that
  emits socket events. An Android app is therefore only ever a *client* — no Python ships
  in it.
- The PWA groundwork is already complete and good: `static/manifest.json` (192/512 PNGs +
  maskable), `static/sw.js` (correctly passes Socket.IO traffic through uncached),
  `/sw.js` + `/manifest.json` served from root in `app.py`, and a
  `templates/partials/install_modal.html`.
- The frontend is **server-rendered Jinja** — `game.html` includes per-game partials and
  injects `window.GAME_TYPE` server-side.
- **Zero persistence anywhere.** No DB, no file writes, all state in memory. Identity is a
  localStorage UUID (`static/js/core/identity.js`) that the server keys players by.
- `CORS_ORIGINS` defaults to `*` in `config.py`, so a WebView origin wouldn't be blocked.
- No Android toolchain installed on the dev machine — no JDK, no Node, no Android SDK.

---

## 1. Offline solo play (vs. the bot, no internet)

**The problem.** 100% of the rules live in Python (`room.py`, `rules.py`, `scoring.py`,
`ai.py` per game). The browser knows nothing about how the games work. Offline means
putting an engine on the device.

**Options considered:**

| Option | Cost | Verdict |
|---|---|---|
| **Port engines to JavaScript** | ~2,000 LOC across 3 games (Super Four worst — powers, match window, Stop orbit). Every rule change then needs two edits in two languages, **forever**. | ❌ Breaks the single-source-of-truth guardrail permanently |
| **Pyodide** (CPython in WASM) | ~10MB bundle, 2–4s cold boot. **Zero rule duplication** — runs the actual Python engine. | ✅ Best path *if* offline is ever required |
| **Skip it** | — | ✅ **Chosen** |

**Why Pyodide fits unusually well here:** the existing architecture already separated the
engine from the socket layer, so `room.py` is a pure state machine with no I/O. That's the
hard part, and it's already done.

**The architectural catch that mattered most:**

> Offline forces **Capacitor** (bundled assets can't be served from a TWA) **and** a
> template refactor — Jinja-rendered `game.html` would have to become static
> client-rendered HTML. That partially undoes the Phase 2 architecture.

**Reasoning for skipping:** it's a *social* game — the value is playing with friends, and
bot practice is a side dish. Not worth ~2,000 lines plus permanent drift risk.

---

## 2. Google Ads

**Hard constraint discovered:**

> **AdMob requires a native app. It cannot run in a PWA or a TWA.** Web-installed apps can
> only use AdSense, at roughly half the RPM.

This puts "install from web" and "AdMob revenue" in direct tension.

### Revenue estimates (India-weighted audience — eCPMs ~5–10× lower than US/EU)

| Users (MAU) | Realistic monthly ad revenue |
|---|---|
| 100 | ~$2 |
| 1,000 | **$17–25** |
| 10,000 | $170–250 |

The 1,000 MAU figure assumes ~11,000 interstitials/month at ~$1 eCPM, plus lobby banners
and some rewarded views.

### Against costs

- Render Starter: **$7/month**
- Domain: ~$12/year (~$1/month)
- **Total ~$8/month → break-even at roughly 400–500 MAU**

### Practical gotchas

- **AdMob doesn't pay out until $100 accrues.** At $20/month that's five months to a first
  cheque.
- Ads in a real-time game are UX-poison if misplaced. **Never mid-round.**

### Best monetization idea from the discussion

**Rewarded video to unlock table themes.** The themes system already exists
(`static/js/core/themes.js`). Rewarded video has the highest eCPM of any format, is fully
opt-in, and degrades gameplay for nobody. This is the one to build first, if ever.

**Reasoning for deferring:** at current scale ads earn approximately nothing, and $7/month
is cheaper than the engineering time. Revisit at 500+ DAU.

---

## 3. Google Sign-In + progress storage — **SKIPPED, but read the warning**

*(Decision: not storing user data for now. Retained because the warning is expensive to
re-learn.)*

**Auth would be easy when wanted:** the server already keys players by an opaque
`user_id`. Google Sign-In just changes *where that ID comes from*. Firebase Auth (works
web + Android identically), verify the ID token in Flask with `google-auth`, map to a user
record.

**Design note if ever built:** keep anonymous play working. Forcing sign-in on a casual
card game costs more players than persistence gains. Auth should be purely additive.

### ⚠️ The warning worth keeping

> **A JSON file DB on Render will silently lose all its data.** Render's filesystem is
> **ephemeral** — wiped on every deploy and every restart. User progress would vanish the
> first time a fix is pushed.

Working around it needs a Render Persistent Disk (paid, pins you to one instance). So the
"JSON now, migrate to Mongo later" plan costs *more* total work than the alternative:

**Skip JSON entirely — start on MongoDB Atlas free tier** (512MB, free forever, no card).
It's the destination anyway, so the persistence layer gets written exactly once. Neon or
Supabase Postgres are equivalent free alternatives. Either way, put it behind a thin
repository interface so storage stays swappable.

---

## 4. Distribution

**Web-install-first is correct**, for a reason specific to this game:

> The viral loop is the **room code**, not store search. Players arrive via a friend
> sharing a link, so store discovery adds little.

**Caveats:**
- On iOS, PWA install works but is buried (Share → Add to Home Screen) and needs guiding.
- Web install means AdSense, not AdMob (see §2).

---

## 5. Packaging: TWA vs. Capacitor

| | **TWA (Bubblewrap)** | **Capacitor** |
|---|---|---|
| Code changes | One Flask route (`/.well-known/assetlinks.json`) | New `android/` folder + Node toolchain |
| Renderer | Chrome itself | Android System WebView |
| Native APIs | Web APIs only | Full native plugins |
| AdMob | ❌ Not possible | ✅ Supported |
| Offline / bundled assets | ❌ Not possible | ✅ Supported |
| APK size | ~1 MB | ~5–10 MB |
| Toolchain | Node + JDK (auto-installed) | + Android Studio |

**Note on Web APIs:** TWA runs in Chrome, so Screen Wake Lock, Vibration, and Web Push all
work. Those cover most of what a card game actually needs.

**Conclusion:** with offline and ads deferred, **TWA wins** — minimal repo change, best
renderer, auto-updates with the server. Moving TWA → Capacitor later is not a rewrite, so
this doesn't paint us into a corner.

---

## 6. Mobile hardening (separate from packaging — still relevant)

Packaging is the easy half. These matter regardless of TWA vs. Capacitor and are **not yet
done**:

- **Socket reconnect on background/foreground** — Android suspends WebView timers
  aggressively. Server state survives; the socket drops and needs a clean resume.
- **Screen Wake Lock** — the phone currently sleeps while waiting for your turn.
- **Back button** — currently walks the user out of a live room mid-game.
- **Safe areas** — `viewport-fit=cover` + `env(safe-area-inset-*)` for notches and the
  gesture bar.
- **Render cold start** — on the free tier a spun-down instance takes ~50s. Tolerable on
  web, brutal as an app's first launch.

Existing mobile CSS is in decent shape per `todos.md` §7–8 (verified at 360/375px), so
this is polish, not a redesign.

---

## Sequencing suggested during the discussion

*(Recorded for context — superseded by the decisions table at the top, which drops steps
2, 4 and 5.)*

1. Ship PWA install from the site (~95% done already)
2. ~~Add auth + Mongo Atlas~~ — **dropped**
3. Get real usage data
4. ~~Capacitor + AdMob at 500+ DAU~~ — **deferred**
5. ~~Offline via Pyodide~~ — **deferred**

The one firm piece of advice: **don't build ad infrastructure for $2/month.** Get to a few
hundred daily players first — that number decides the deferred items.
