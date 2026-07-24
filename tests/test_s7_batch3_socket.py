import sys, os, time, socketio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE="http://localhost:5005"; results=[]
def check(ok,m): results.append(ok); print(("PASS " if ok else "FAIL ")+m)
def cl(s):
    c=socketio.Client()
    c.on("room_created",lambda d:s.update(code=d["code"]))
    c.on("join_ok",lambda d:s.update(code=d["code"]))
    c.on("reaction",lambda d:s.setdefault("rx",[]).append(d))
    return c
S={u:{} for u in("A","B")}; C={u:cl(S[u]) for u in S}
for c in C.values(): c.connect(BASE)
time.sleep(0.3)
C["A"].emit("create_room",{"name":"A","user_id":"A","settings":{}}); time.sleep(0.3)
code=S["A"]["code"]
C["B"].emit("join_room",{"code":code,"name":"B","user_id":"B"}); time.sleep(0.15)
for u in("A","B"): C[u].emit("enter_room",{"code":code,"name":u,"user_id":u}); time.sleep(0.12)

C["A"].emit("reaction",{"code":code,"user_id":"A","emoji":"🔥"}); time.sleep(0.25)
check(any(r["emoji"]=="🔥" for r in S["B"].get("rx",[])),"whitelisted reaction reaches other players")
check(any(r["name"]=="A" for r in S["B"].get("rx",[])),"reaction carries the sender name")
check(any(r["emoji"]=="🔥" for r in S["A"].get("rx",[])),"sender also sees their own reaction")

S["B"]["rx"]=[]
C["A"].emit("reaction",{"code":code,"user_id":"A","emoji":"👽"}); time.sleep(0.25)
check(len(S["B"].get("rx",[]))==0,"non-whitelisted emoji is dropped")

S["B"]["rx"]=[]
C["A"].emit("reaction",{"code":code,"user_id":"GHOST","emoji":"🎉"}); time.sleep(0.25)
check(len(S["B"].get("rx",[]))==0,"reaction from a non-member is ignored")

for c in C.values(): c.disconnect()
time.sleep(0.2)
print("\n%d/%d Batch-3 socket checks passed"%(sum(results),len(results)))
sys.exit(0 if all(results) else 1)
