import sys, os, time, socketio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://localhost:5005"
results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

def client(store):
    c = socketio.Client()
    c.on("room_created", lambda d: store.update(code=d["code"]))
    c.on("join_ok", lambda d: store.update(code=d["code"]))
    c.on("room_joined", lambda d: store.update(joined=d))
    c.on("player_list", lambda d: store.update(players=d["players"], host=d["host_id"]))
    c.on("settings_updated", lambda d: store.update(settings=d["settings"]))
    c.on("kicked", lambda d: store.update(kicked=True))
    c.on("error", lambda d: store.update(error=d["message"]))
    return c

stores = {u: {} for u in ("A", "B", "C", "D")}
cl = {u: client(stores[u]) for u in stores}
for c in cl.values(): c.connect(BASE)
time.sleep(0.3)

cl["A"].emit("create_room", {"name": "A", "user_id": "A", "settings": {}})
time.sleep(0.3)
code = stores["A"]["code"]
for u in ("B", "C"):
    cl[u].emit("join_room", {"code": code, "name": u, "user_id": u}); time.sleep(0.15)
for u in ("A", "B", "C"):
    cl[u].emit("enter_room", {"code": code, "name": u, "user_id": u}); time.sleep(0.12)

# ---- #1 host edits settings ----
new = {"max_score": 50, "stop_penalty": 30, "win_discount": 10, "turn_timer": 25, "timeout_limit": 2}
cl["A"].emit("update_settings", {"code": code, "user_id": "A", "settings": new})
time.sleep(0.3)
check(stores["B"].get("settings", {}).get("max_score") == 50, "host settings change broadcasts to everyone")
check(stores["C"].get("settings", {}).get("turn_timer") == 25, "all settings fields propagate")

# non-host cannot edit
stores["B"]["error"] = None
cl["B"].emit("update_settings", {"code": code, "user_id": "B", "settings": new})
time.sleep(0.25)
check(stores["B"]["error"] == "Only the host can change the settings.", "non-host settings edit rejected")

# ---- #2 host kicks a player ----
cl["A"].emit("kick_player", {"code": code, "user_id": "A", "target": "C"})
time.sleep(0.3)
check(stores["C"].get("kicked") is True, "kicked player is notified")
ids_after_kick = {p["user_id"] for p in stores["A"].get("players", [])}
check("C" not in ids_after_kick and ids_after_kick == {"A", "B"}, "roster updates after kick")

# non-host cannot kick
stores["B"]["error"] = None
cl["B"].emit("kick_player", {"code": code, "user_id": "B", "target": "A"})
time.sleep(0.25)
check(stores["B"]["error"] == "Only the host can remove players.", "non-host kick rejected")

# ---- #1 a NEW player can join the (re)opened lobby ----
cl["D"].emit("join_room", {"code": code, "name": "D", "user_id": "D"})
time.sleep(0.2)
check(stores["D"].get("code") == code, "new player allowed to join lobby")
cl["D"].emit("enter_room", {"code": code, "name": "D", "user_id": "D"})
time.sleep(0.25)
ids_final = {p["user_id"] for p in stores["A"].get("players", [])}
check(ids_final == {"A", "B", "D"}, "new joiner appears in the roster")

for c in cl.values(): c.disconnect()
time.sleep(0.2)
print("\n%d/%d Batch-1 socket checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
