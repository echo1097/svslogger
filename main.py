import tkinter as tk
from tkinter import ttk
import threading, time, urllib.request, json, re

localDMG = "http://localhost:8111/hudmsg?lastEvt=0&lastDmg=0"
localMAP = "http://localhost:8111/map_info.json"
localMISSION = "http://localhost:8111/mission.json"
delay = 2
PPS = 8

seen_ids = set()
players = {}
squadrons = set()

def getdata():
    try:
        with urllib.request.urlopen(localDMG) as f:
            
            d = json.loads(f.read().decode("utf-8"))
        return d.get("damage", [])[::-1]
    except:
        return []

def filter_existing():
    try:
        with urllib.request.urlopen(localDMG) as f:
            d = json.loads(f.read().decode("utf-8"))
        old = d.get("damage", [])
        for e in old:
            seen_ids.add(e["id"])
    except:
        pass

def isingame():
    try:
        with urllib.request.urlopen(localMAP) as f:
            d = json.loads(f.read().decode("utf-8"))
        return bool(d.get("valid", False))
    except:
        return False

def currentstatus():
    try:
        with urllib.request.urlopen(localMISSION) as f:
            d = json.loads(f.read().decode("utf-8"))
        st = d.get("status", "").strip().lower()
        if st == "success":
            return "Won"
        elif st == "fail":
            return "Loss"
        elif st == "running":
            return "In Game"
        return "Undetermined"
    except:
        return "Undetermined"

def fetchsquadrontag(s):
    return re.sub(r"[^a-zA-Z0-9 ]", "", s or "").strip()

def parseNV(s):
    s = s.strip()
    if not s:
        return "", "Unknown"
    i = len(s) - 1
    while i >= 0 and s[i].isspace():
        i -= 1
    if i < 0 or s[i] != ')':
        return s, "Unknown"
    close_idx = i
    cnt = 0
    for j in range(close_idx, -1, -1):
        if s[j] == ')':
            cnt += 1
        elif s[j] == '(':
            cnt -= 1
            if cnt == 0:
                open_idx = j
                break
    else:
        return s, "Unknown"
    user = s[:open_idx].strip()
    veh = s[open_idx+1:close_idx].strip()
    return user, veh

def parseSQNV(raw):
    if not raw:
        return None
    parts = raw.split(maxsplit=1)
    if len(parts) == 1:
        u, v = parseNV(raw)
        return (None, u, v)
    sq, rem = parts
    u, v = parseNV(rem)
    sq = re.sub(r"\s+", " ", sq).strip()
    return (sq, u, v)

def ignoreline(msg):
    low = msg.lower()
    return any(x in low for x in ["recon micro", "drone", "scout"])

def MAS(sq):
    if sq and len(squadrons) < 2:
        squadrons.add(sq)

def readkillmsgs(msg):
    crash_m = re.match(r"^(.*)\s+has\s+crashed\.$", msg)
    if crash_m:
        vs = crash_m.group(1).strip()
        pv = parseSQNV(vs)
        if not pv:
            return None
        return {
            "attacker_squadron": None,
            "attacker_name": None,
            "attacker_vehicle": None,
            "method": "crashed",
            "victim_squadron": pv[0],
            "victim_name": pv[1],
            "victim_vehicle": pv[2]
        }
    kill_m = re.search(r"\s(shot down|destroyed)\s", msg)
    if kill_m:
        mth = kill_m.group(1)
        left = msg[: kill_m.start()].strip()
        right = msg[kill_m.end() :].strip()
        pa = parseSQNV(left)
        pv = parseSQNV(right)
        if not pa or not pv:
            return None
        return {
            "attacker_squadron": pa[0],
            "attacker_name": pa[1],
            "attacker_vehicle": pa[2],
            "method": mth,
            "victim_squadron": pv[0],
            "victim_name": pv[1],
            "victim_vehicle": pv[2]
        }
    return None

def bestsquad(msg):
    m = re.search(r'(.*)\s+has achieved\s+"The Best Squad"', msg)
    if not m:
        return None
    raw = m.group(1).strip()
    return parseSQNV(raw)

def trackkill(k):
    if not k:
        return
    vs, vn, vv, mth = k["victim_squadron"], k["victim_name"], k["victim_vehicle"], k["method"]
    asq, an, av = k["attacker_squadron"], k["attacker_name"], k["attacker_vehicle"]
    MAS(vs)
    if vn not in players:
        players[vn] = {"squadron": vs, "vehicle": vv, "alive": True, "kills": 0}
    players[vn]["squadron"] = vs
    players[vn]["vehicle"] = vv
    players[vn]["alive"] = False
    if mth != "crashed" and asq and an:
        MAS(asq)
        if an not in players:
            players[an] = {"squadron": asq, "vehicle": av, "alive": True, "kills": 0}
        else:
            players[an]["squadron"] = asq
            players[an]["vehicle"] = av
        players[an]["kills"] += 1

def missingadd(sq, nm, veh):
    if not sq or not nm:
        return
    MAS(sq)
    if nm not in players:
        players[nm] = {"squadron": sq, "vehicle": veh, "alive": True, "kills": 0}
    else:
        if players[nm]["vehicle"] == "Unknown":
            players[nm]["vehicle"] = veh
        if players[nm]["squadron"] != sq:
            players[nm]["squadron"] = sq

def killcheck():
    dmg = getdata()
    for e in dmg:
        i = e["id"]
        if i in seen_ids:
            continue
        seen_ids.add(i)
        msg = e["msg"]
        if ignoreline(msg):
            continue
        kill_info = readkillmsgs(msg)
        if kill_info:
            trackkill(kill_info)
        else:
            bsm = bestsquad(msg)
            if bsm:
                s, n, v = bsm
                missingadd(s, n, v)

def resetmathdata():
    global players, squadrons
    players = {}
    squadrons = set()

class mainapp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SVS Logger by echo1097")
        self.geometry("1100x600")
        self.configure(bg="#2b2b2b")
        self.current_in_game = False
        self.match_frozen = False
        self.poll_thread_running = False  
        filter_existing()

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
            background="#2b2b2b",
            foreground="white",
            rowheight=25,
            fieldbackground="#2b2b2b",
            bordercolor="#333333",
            borderwidth=1
        )
        style.map("Treeview",
            background=[("selected", "#4d4d4d")],
            foreground=[("selected", "white")]
        )
        style.configure("Treeview.Heading",
            background="#444444",
            foreground="white",
            font=("Arial", 11, "bold")
        )

        top = tk.Frame(self, bg="#2b2b2b")
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        self.game_status_label = tk.Label(
            top, text="Not in game", fg="white", bg="#666666",
            font=("Arial", 12), width=12
        )
        self.game_status_label.pack(side=tk.LEFT, padx=5)

        self.win_loss_label = tk.Label(
            top, text="", fg="white", bg="#666666",
            font=("Arial", 12), width=12
        )
        self.win_loss_label.pack(side=tk.LEFT, padx=5)

        self.main_frame = tk.Frame(self, bg="#2b2b2b")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.after(500, self.poll_loop)

    def poll_loop(self):
        if not self.poll_thread_running:
            self.poll_thread_running = True
            threading.Thread(target=self.background_polling, daemon=True).start()
        self.after(delay * 1000, self.poll_loop)

    def background_polling(self):
        new_in_game = isingame()

        if not self.current_in_game and new_in_game:
            resetmathdata()
            self.match_frozen = False

        if self.current_in_game and not new_in_game:
            self.match_frozen = True
            killcheck()
            st = currentstatus()
            self.after(0, lambda: self.win_loss_label.config(
                text=("Won" if st.lower() == "won" else
                      "Loss" if st.lower() == "loss" else
                      "In Game" if st.lower() == "in game" else
                      "Undetermined"),
                bg=("#336699" if st.lower() == "won" else
                    "#993333" if st.lower() == "loss" else
                    "#336633" if st.lower() == "in game" else
                    "#666666")
            ))
        self.current_in_game = new_in_game

        if not self.current_in_game:
            self.after(0, lambda: self.game_status_label.config(text="Not in game", bg="#666666"))
        else:
            self.after(0, lambda: self.game_status_label.config(text="In game", bg="#336633"))
            st = currentstatus()
            self.after(0, lambda: self.win_loss_label.config(
                text=("Won" if st.lower() == "won" else
                      "Loss" if st.lower() == "loss" else
                      "In Game" if st.lower() == "in game" else
                      "Undetermined"),
                bg=("#336699" if st.lower() == "won" else
                    "#993333" if st.lower() == "loss" else
                    "#336633" if st.lower() == "in game" else
                    "#666666")
            ))
        if not self.match_frozen:
            killcheck()

        self.after(0, self.refresh_display)
        self.poll_thread_running = False

    def refresh_display(self):
        for w in self.main_frame.winfo_children():
            w.destroy()

        sq_list = sorted(list(squadrons))
        s1 = sq_list[0] if len(sq_list) > 0 else None
        s2 = sq_list[1] if len(sq_list) > 1 else None

        cont = tk.Frame(self.main_frame, bg="#2b2b2b")
        cont.pack(fill=tk.BOTH, expand=True)

        f_left = tk.Frame(cont, bg="#2b2b2b")
        f_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        f_right = tk.Frame(cont, bg="#2b2b2b")
        f_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        lbl1_text = fetchsquadrontag(s1) if s1 else "No Squad"
        lbl1 = tk.Label(f_left, text=lbl1_text, fg="white", bg="#2b2b2b", font=("Arial", 14, "bold"))
        lbl1.pack(pady=(0,5))
        tv1 = self.create_table(f_left)
        self.populate_squad_table(tv1, s1)

        lbl2_text = fetchsquadrontag(s2) if s2 else "No Squad"
        lbl2 = tk.Label(f_right, text=lbl2_text, fg="white", bg="#2b2b2b", font=("Arial", 14, "bold"))
        lbl2.pack(pady=(0,5))
        tv2 = self.create_table(f_right)
        self.populate_squad_table(tv2, s2)

    def create_table(self, parent):
        cols = ("Players", "Vehicle", "State", "Kills")
        tv = ttk.Treeview(parent, columns=cols, show="headings", height=8)
        tv.heading("Players", text="Players")
        tv.heading("Vehicle", text="Vehicle")
        tv.heading("State", text="State")
        tv.heading("Kills", text="Kills")
        tv.column("Players", width=160, anchor=tk.W)
        tv.column("Vehicle", width=160, anchor=tk.W)
        tv.column("State", width=80, anchor=tk.CENTER)
        tv.column("Kills", width=80, anchor=tk.CENTER)
        tv.tag_configure("Alive", background="#2e4d2b")
        tv.tag_configure("Dead", background="#4d2b2b")
        tv.tag_configure("Unknown", background="#444444")
        tv.pack(fill=tk.BOTH, expand=False)
        return tv

    def populate_squad_table(self, tree, sq):
        if not sq:
            for _ in range(PPS):
                tree.insert("", "end", values=("Unknown", "Unknown", "Unknown", ""), tags=("Unknown",))
            return
        rel = [p for p, d in players.items() if d["squadron"] == sq]
        while len(rel) < PPS:
            ph = f"Unknown_{sq}_{len(rel)+1}"
            players[ph] = {"squadron": sq, "vehicle": "Unknown", "alive": True, "kills": 0}
            rel.append(ph)
        norm = [p for p in rel if not p.startswith("Unknown_")]
        unk = [p for p in rel if p.startswith("Unknown_")]
        allp = norm + unk
        for nm in allp:
            d = players[nm]
            st = "Alive" if d["alive"] else "Dead"
            k = d["kills"]
            ks = str(k) if k > 0 else "No kills"
            n_str = nm
            v_str = d["vehicle"]
            tag = "Alive" if d["alive"] else "Dead"
            if nm.startswith("Unknown_"):
                n_str, v_str, st, ks, tag = "Unknown", "Unknown", "Unknown", "", "Unknown"
            tree.insert("", "end", values=(n_str, v_str, st, ks), tags=(tag,))

def main():
    app = mainapp()
    app.mainloop()

if __name__ == "__main__":
    main()
