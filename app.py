import streamlit as st
import pandas as pd
from collections import defaultdict
import json
import os
import copy

st.set_page_config(page_title="Pickleball Pool Ladder", layout="wide")
st.title("Pickleball Multi-Court Ladder")

SAVE_FILE = "pickleball_session.json"

def save_state():
    if not st.session_state.get("created"):
        return
    data = {
        "players": st.session_state.get("players"),
        "courts": st.session_state.get("courts"),
        "court_names": st.session_state.get("court_names"),
        "schedules": st.session_state.get("schedules"),
        "scores": st.session_state.get("scores"),
        "num_courts": st.session_state.get("num_courts"),
        "num_cycles": st.session_state.get("num_cycles"),
        "cycle": st.session_state.get("cycle"),
        "standings": st.session_state.get("standings"),
        "relevant_ties": st.session_state.get("relevant_ties"),
        "skinny_results": st.session_state.get("skinny_results"),
        "cumulative": st.session_state.get("cumulative"),
        "assignment_history": st.session_state.get("assignment_history"),
        "final_done": st.session_state.get("final_done"),
        "admin_password": st.session_state.get("admin_password", "2302"),
        "cycle_snapshots": st.session_state.get("cycle_snapshots", {}),
        "play_to": st.session_state.get("play_to", 9),
    }
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def load_state():
    if not os.path.exists(SAVE_FILE):
        return False
    try:
        with open(SAVE_FILE, "r") as f:
            data = json.load(f)
        for key, value in data.items():
            st.session_state[key] = value
        st.session_state.created = True
        return True
    except Exception:
        return False

def generate_schedule(players):
    n = len(players)
    names = [p["name"] for p in players]
    if n < 4:
        return []
    if n == 4:
        return [
            [((names[0], names[1]), (names[2], names[3]))],
            [((names[0], names[2]), (names[1], names[3]))],
            [((names[0], names[3]), (names[1], names[2]))],
        ]
    if n == 5:
        return [
            [((names[0], names[1]), (names[2], names[3])), names[4]],
            [((names[1], names[3]), (names[2], names[4])), names[0]],
            [((names[0], names[4]), (names[1], names[2])), names[3]],
            [((names[0], names[2]), (names[3], names[4])), names[1]],
            [((names[0], names[3]), (names[1], names[4])), names[2]],
        ]
    if n == 6:
        rounds = []
        order = names[:]
        for r in range(6):
            sit1 = order[r % 6]
            sit2 = order[(r + 3) % 6]
            playing = [p for p in order if p not in (sit1, sit2)]
            match = ((playing[0], playing[1]), (playing[2], playing[3]))
            rounds.append([match, sit1, sit2])
        return rounds
    return []

# ---------- Initialize ----------
if "admin_unlocked" not in st.session_state:
    st.session_state.admin_unlocked = False
if "admin_password" not in st.session_state:
    st.session_state.admin_password = "2302"
if "created" not in st.session_state:
    load_state()
if "cycle_snapshots" not in st.session_state:
    st.session_state.cycle_snapshots = {}
if "edit_scores_unlocked" not in st.session_state:
    st.session_state.edit_scores_unlocked = False

# ---------- Top Admin Bar ----------
c1, c2, c3 = st.columns([2, 2, 3])
with c1:
    if not st.session_state.admin_unlocked:
        if st.button("Administrative Mode"):
            st.session_state.show_admin_login = True
    else:
        st.success("Admin Mode Active")
        if st.button("Lock Admin"):
            st.session_state.admin_unlocked = False
            st.session_state.edit_scores_unlocked = False
            st.rerun()

with c2:
    if st.session_state.admin_unlocked:
        if st.button("Start New Session"):
            for key in list(st.session_state.keys()):
                if key not in ["admin_password", "admin_unlocked"]:
                    del st.session_state[key]
            if os.path.exists(SAVE_FILE):
                try:
                    os.remove(SAVE_FILE)
                except Exception:
                    pass
            st.session_state.admin_unlocked = True
            st.rerun()

with c3:
    if st.session_state.admin_unlocked:
        if st.button("Change Admin Password"):
            st.session_state.show_change_password = True

if st.session_state.get("show_admin_login") and not st.session_state.admin_unlocked:
    pwd = st.text_input("Enter Admin Password", type="password", key="admin_login")
    if pwd:
        if pwd == st.session_state.admin_password:
            st.session_state.admin_unlocked = True
            st.session_state.show_admin_login = False
            st.rerun()
        else:
            st.error("Wrong password")

if st.session_state.get("show_change_password") and st.session_state.admin_unlocked:
    st.markdown("### Change Admin Password")
    old = st.text_input("Current password", type="password", key="old_pwd")
    new = st.text_input("New password", type="password", key="new_pwd")
    if st.button("Update Password"):
        if old == st.session_state.admin_password and new and len(new) >= 4:
            st.session_state.admin_password = new
            st.session_state.show_change_password = False
            save_state()
            st.success("Password updated")
            st.rerun()
        else:
            st.error("Current password incorrect or new password too short")

st.markdown("---")

# ---------- Session Setup ----------
if st.session_state.admin_unlocked and not st.session_state.get("created"):
    st.header("1. Session Setup (Admin)")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        num_courts = st.number_input("Number of courts", min_value=2, max_value=6, value=3)
    with col2:
        num_cycles = st.number_input("Number of cycles", min_value=1, max_value=6, value=3)
    with col3:
        play_to = st.number_input("Play to", min_value=7, max_value=21, value=9)
    with col4:
        win_by = st.selectbox("Win by", [1, 2], index=0)

    st.header("2. Enter Players")
    player_text = st.text_area("Players (Name, DUPR)", height=200, value="""Bruce, 5.5
Tonkla, 5.0
Vlad, 4.7
JP, 4.7
Gav, 4.5
Pun, 4.4
Krating, 4.3
Andy, 4.1
Dan, 4.2
Justin, 4.0
Val, 4.0
Jack, 3.8
Tuan, 3.6
Oscar, 3.6
Sara, 3.0
Mike, 3.9
John, 4.5
Lisa, 3.7
Tom, 4.3
Emma, 3.5""")

    if st.button("Create Session", type="primary"):
        players = []
        for line in player_text.strip().splitlines():
            if "," in line:
                try:
                    name, dupr = line.split(",", 1)
                    players.append({"name": name.strip(), "dupr": float(dupr.strip())})
                except:
                    pass
        if len(players) < num_courts * 4:
            st.error("Not enough players (minimum 4 per court)")
        else:
            players = sorted(players, key=lambda x: x["dupr"], reverse=True)
            total = len(players)
            base = total // num_courts
            rem = total % num_courts
            sizes = [base + (1 if i >= num_courts - rem else 0) for i in range(num_courts)]

            courts = {}
            idx = 0
            court_names = []
            for i in range(num_courts):
                cname = f"Court {chr(65 + i)}"
                courts[cname] = players[idx:idx + sizes[i]]
                court_names.append(cname)
                idx += sizes[i]

            schedules = {c: generate_schedule(p) for c, p in courts.items()}

            default_score = int(play_to)
            scores = {}
            for cname, schedule in schedules.items():
                for r_idx, rnd in enumerate(schedule):
                    matches = [x for x in rnd if isinstance(x, tuple) and len(x) == 2 and isinstance(x[0], tuple)]
                    for m_idx, match in enumerate(matches):
                        key = f"{cname}_r{r_idx}_m{m_idx}"
                        scores[key] = (default_score, default_score)

            cumulative = {p["name"]: {"diff": 0, "wins": 0} for p in players}

            st.session_state.assignment_history = [{
                "title": "Starting Pool Play Ladder (by DUPR)",
                "type": "groups",
                "data": courts
            }]
            st.session_state.scores = scores
            st.session_state.skinny_results = {}
            st.session_state.players = players
            st.session_state.courts = courts
            st.session_state.court_names = court_names
            st.session_state.schedules = schedules
            st.session_state.num_courts = num_courts
            st.session_state.num_cycles = num_cycles
            st.session_state.play_to = play_to
            st.session_state.created = True
            st.session_state.cycle = 1
            st.session_state.standings = None
            st.session_state.relevant_ties = None
            st.session_state.cumulative = cumulative
            st.session_state.final_done = False
            st.session_state.cycle_snapshots = {}
            st.session_state.edit_scores_unlocked = False
            save_state()
            st.rerun()

# ---------- Main ----------
if st.session_state.get("created"):
    courts = st.session_state.courts
    schedules = st.session_state.schedules
    num_courts = st.session_state.num_courts
    court_names = st.session_state.court_names
    num_cycles = st.session_state.num_cycles
    is_admin = st.session_state.admin_unlocked
    play_to = st.session_state.get("play_to", 9)

    st.success(f"Cycle {st.session_state.cycle} of {num_cycles}")

    # History
    st.markdown("---")
    st.header("Full History")

    for idx, entry in enumerate(st.session_state.assignment_history):
        colh1, colh2 = st.columns([6, 1])
        with colh1:
            st.subheader(entry["title"])
        with colh2:
            if is_admin and entry["type"] == "rankings" and "Rankings after Cycle" in entry["title"]:
                try:
                    cycle_num = int(entry["title"].split("Cycle ")[1])
                    if st.button("Edit", key=f"edit_{cycle_num}_{idx}"):
                        st.session_state[f"ask_pwd_for_edit_{cycle_num}"] = True
                except Exception:
                    pass

        if is_admin and entry["type"] == "rankings" and "Rankings after Cycle" in entry["title"]:
            try:
                cycle_num = int(entry["title"].split("Cycle ")[1])
                if st.session_state.get(f"ask_pwd_for_edit_{cycle_num}", False):
                    pwd = st.text_input(f"Re-enter Admin Password to edit Cycle {cycle_num}", type="password", key=f"pwd_edit_{cycle_num}")
                    if pwd:
                        if pwd == st.session_state.admin_password:
                            if str(cycle_num) in st.session_state.cycle_snapshots:
                                snap = st.session_state.cycle_snapshots[str(cycle_num)]
                                st.session_state.courts = copy.deepcopy(snap["courts"])
                                st.session_state.schedules = copy.deepcopy(snap["schedules"])
                                st.session_state.scores = copy.deepcopy(snap["scores"])
                                st.session_state.cycle = cycle_num
                                st.session_state.standings = None
                                st.session_state.relevant_ties = None
                                st.session_state.skinny_results = {}
                                st.session_state.final_done = False
                                st.session_state.assignment_history = st.session_state.assignment_history[:idx]
                                st.session_state[f"ask_pwd_for_edit_{cycle_num}"] = False
                                st.session_state.edit_scores_unlocked = False
                                save_state()
                                st.rerun()
                        else:
                            st.error("Wrong password")
            except Exception:
                pass

        if entry["type"] == "groups":
            cols = st.columns(num_courts)
            for i, cname in enumerate(court_names):
                with cols[i]:
                    st.markdown(f"**{cname}**")
                    plist = entry["data"].get(cname, [])
                    if plist:
                        df = pd.DataFrame(plist)[["name", "dupr"]].rename(columns={"name": "Player", "dupr": "DUPR"})
                        st.dataframe(df, hide_index=True, use_container_width=True)

        elif entry["type"] == "rankings":
            cols = st.columns(num_courts)
            for i, cname in enumerate(court_names):
                with cols[i]:
                    st.markdown(f"**{cname}**")
                    ranking = entry["data"].get(cname, [])
                    if ranking:
                        data = [{"#": j+1, "Player": r["name"], "+/−": r["diff"], "Matches Won": r["wins"]} for j, r in enumerate(ranking)]
                        st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)

        elif entry["type"] == "new_groups":
            cols = st.columns(num_courts)
            for i, cname in enumerate(court_names):
                with cols[i]:
                    st.markdown(f"**{cname}**")
                    rows = entry["data"].get(cname, [])
                    if rows:
                        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        st.markdown("")

    # ---------- SCORES ----------
    if not st.session_state.get("final_done") and not st.session_state.get("standings"):
        st.markdown("---")
        st.header(f"3. Scores – Cycle {st.session_state.cycle}")
        if not is_admin:
            st.info("View only. Unlock Administrative Mode to edit scores.")

        for cname in court_names:
            st.subheader(cname)
            schedule = schedules.get(cname, [])

            if not schedule:
                st.warning(f"No schedule generated for {cname}")
                continue

            for r_idx, rnd in enumerate(schedule):
                st.markdown(f"**Round {r_idx+1}**")

                matches = []
                byes = []
                for item in rnd:
                    if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], tuple):
                        matches.append(item)
                    elif isinstance(item, str):
                        byes.append(item)

                for m_idx, match in enumerate(matches):
                    t1, t2 = match
                    key = f"{cname}_r{r_idx}_m{m_idx}"
                    current = st.session_state.scores.get(key, (play_to, play_to))

                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{t1[0]} & {t1[1]}**")
                        st.markdown("  vs")
                        st.markdown(f"**{t2[0]} & {t2[1]}**")
                    with col2:
                        if is_admin:
                            s1 = st.number_input("s1", min_value=0, max_value=30, value=int(current[0]), key=f"input_s1_{key}", label_visibility="collapsed")
                            st.write("")
                            s2 = st.number_input("s2", min_value=0, max_value=30, value=int(current[1]), key=f"input_s2_{key}", label_visibility="collapsed")
                        else:
                            st.markdown(f"**{current[0]}**")
                            st.write("")
                            st.markdown(f"**{current[1]}**")
                            s1, s2 = current[0], current[1]

                    st.session_state.scores[key] = (s1, s2)
                    st.markdown("---")

                if byes:
                    st.caption(f"Bye: {', '.join(byes)}")
            st.markdown("")

        if is_admin:
            if st.button("Calculate Rankings + Check Skinny Singles", type="primary"):
                standings = {}
                relevant_ties = {}
                for c_idx, cname in enumerate(court_names):
                    schedule = schedules[cname]
                    diff = defaultdict(int)
                    wins = defaultdict(int)
                    for r_idx, rnd in enumerate(schedule):
                        matches = [x for x in rnd if isinstance(x, tuple) and len(x) == 2 and isinstance(x[0], tuple)]
                        for m_idx, match in enumerate(matches):
                            key = f"{cname}_r{r_idx}_m{m_idx}"
                            s1, s2 = st.session_state.scores.get(key, (0, 0))
                            t1, t2 = match
                            pdif = s1 - s2
                            for p in t1: diff[p] += pdif
                            for p in t2: diff[p] -= pdif
                            if s1 > s2:
                                for p in t1: wins[p] += 1
                            elif s2 > s1:
                                for p in t2: wins[p] += 1
                    ranking = [{"name": p["name"], "diff": diff[p["name"]], "wins": wins[p["name"]]} for p in courts[cname]]
                    ranking.sort(key=lambda x: (x["diff"], x["wins"]), reverse=True)
                    standings[cname] = ranking

                    is_top = (c_idx == 0)
                    is_bot = (c_idx == num_courts - 1)
                    n = len(ranking)
                    ties = []
                    if not is_top and n >= 2:
                        sc = (ranking[1]["diff"], ranking[1]["wins"])
                        grp = [r for r in ranking if (r["diff"], r["wins"]) == sc]
                        if len(grp) >= 2:
                            better = sum(1 for r in ranking if (r["diff"], r["wins"]) > sc)
                            need = max(0, 2 - better)
                            if need > 0 and len(grp) > need:
                                ties.append({"zone": "top (move up)", "players": [r["name"] for r in grp], "score": grp[0]["diff"], "needed": need})
                    if not is_bot and n >= 2:
                        sc = (ranking[-2]["diff"], ranking[-2]["wins"])
                        grp = [r for r in ranking if (r["diff"], r["wins"]) == sc]
                        if len(grp) >= 2:
                            worse = sum(1 for r in ranking if (r["diff"], r["wins"]) < sc)
                            need = max(0, 2 - worse)
                            if need > 0 and len(grp) > need:
                                ties.append({"zone": "bottom (move down)", "players": [r["name"] for r in grp], "score": grp[0]["diff"], "needed": need})
                    if ties:
                        relevant_ties[cname] = ties

                st.session_state.standings = standings
                st.session_state.relevant_ties = relevant_ties
                st.session_state.cycle_snapshots[str(st.session_state.cycle)] = {
                    "courts": copy.deepcopy(courts),
                    "schedules": copy.deepcopy(schedules),
                    "scores": copy.deepcopy(st.session_state.scores)
                }
                st.session_state.edit_scores_unlocked = False
                save_state()
                st.rerun()

    # Rankings + Skinny Singles
    if st.session_state.get("standings") and not st.session_state.get("final_done"):
        st.markdown("---")
        col_rank, col_edit = st.columns([5, 1])
        with col_rank:
            st.header(f"Rankings after Cycle {st.session_state.cycle}")
        with col_edit:
            if is_admin:
                if st.button("Edit Scores"):
                    st.session_state.show_edit_pwd = True

        if st.session_state.get("show_edit_pwd"):
            pwd = st.text_input("Re-enter Admin Password to edit scores", type="password", key="edit_scores_pwd")
            if pwd:
                if pwd == st.session_state.admin_password:
                    st.session_state.standings = None
                    st.session_state.relevant_ties = None
                    st.session_state.skinny_results = {}
                    st.session_state.show_edit_pwd = False
                    st.session_state.edit_scores_unlocked = True
                    save_state()
                    st.rerun()
                else:
                    st.error("Wrong password")

        cols = st.columns(num_courts)
        for i, cname in enumerate(court_names):
            with cols[i]:
                st.subheader(cname)
                data = [{"#": j+1, "Player": r["name"], "+/−": r["diff"], "Matches Won": r["wins"]} for j, r in enumerate(st.session_state.standings[cname])]
                st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)

        has_conflict = False
        if st.session_state.get("relevant_ties") and is_admin:
            st.markdown("---")
            st.header("Skinny Singles Required")

            # First collect current selections (free selection)
            current_selections = {}
            for cname, ties in st.session_state.relevant_ties.items():
                for tie in ties:
                    key = f"{cname}_{tie['zone']}"
                    selected = []
                    st.write(f"**{tie['zone']}** — tied at {tie['score']:+d}: {', '.join(tie['players'])}")
                    st.write(f"Select exactly {tie['needed']} player(s):")
                    cbs = st.columns(min(len(tie["players"]), 4))
                    for i, p in enumerate(tie["players"]):
                        with cbs[i % len(cbs)]:
                            if st.checkbox(p, key=f"sk_{cname}_{tie['zone']}_{p}_{st.session_state.cycle}"):
                                selected.append(p)
                    current_selections[key] = selected
                    if len(selected) == tie["needed"]:
                        st.session_state.skinny_results[key] = selected
                        st.success(f"Selected: {', '.join(selected)}")
                    elif len(selected) > tie["needed"]:
                        st.warning(f"Select only {tie['needed']}")
                    elif len(selected) > 0:
                        st.warning(f"Select {tie['needed'] - len(selected)} more")

            # Check for conflicts (same player in both up and down)
            up_players = set()
            down_players = set()
            for key, selected in current_selections.items():
                if "move up" in key:
                    up_players.update(selected)
                if "move down" in key:
                    down_players.update(selected)

            conflict_players = up_players.intersection(down_players)
            if conflict_players:
                has_conflict = True
                st.error(f"Please choose player again – same player has been selected to move up and down: **{', '.join(conflict_players)}**")

        if is_admin:
            st.markdown("---")
            if st.session_state.cycle < num_cycles:
                if has_conflict:
                    st.button("Apply Movement & Start Next Cycle", type="primary", disabled=True)
                    st.warning("Fix the conflict above before continuing")
                else:
                    if st.button("Apply Movement & Start Next Cycle", type="primary"):
                        ready = True
                        if st.session_state.get("relevant_ties"):
                            for cname, ties in st.session_state.relevant_ties.items():
                                for tie in ties:
                                    key = f"{cname}_{tie['zone']}"
                                    if key not in st.session_state.skinny_results or len(st.session_state.skinny_results[key]) != tie["needed"]:
                                        ready = False
                                        st.error(f"Please finish skinny singles for {cname}")
                        if not ready:
                            st.stop()

                        for cname, ranking in st.session_state.standings.items():
                            for r in ranking:
                                st.session_state.cumulative[r["name"]]["diff"] += r["diff"]
                                st.session_state.cumulative[r["name"]]["wins"] += r["wins"]

                        st.session_state.assignment_history.append({
                            "title": f"Rankings after Cycle {st.session_state.cycle}",
                            "type": "rankings",
                            "data": st.session_state.standings
                        })

                        final_rankings = st.session_state.standings
                        new_courts = {name: [] for name in court_names}
                        display_data = {name: [] for name in court_names}
                        movers_up = {name: [] for name in court_names}
                        movers_down = {name: [] for name in court_names}

                        for c_idx, cname in enumerate(court_names):
                            ranking = final_rankings[cname]
                            up_list = ranking[:2] if c_idx > 0 else []
                            down_list = ranking[-2:] if c_idx < num_courts - 1 else []

                            if f"{cname}_top (move up)" in st.session_state.skinny_results:
                                selected_names = st.session_state.skinny_results[f"{cname}_top (move up)"]
                                up_list = [r for r in ranking if r["name"] in selected_names]
                                for r in ranking:
                                    if (r["diff"], r["wins"]) > (ranking[1]["diff"], ranking[1]["wins"]) and r["name"] not in selected_names:
                                        up_list.insert(0, r)
                                up_list = up_list[:2]

                            if f"{cname}_bottom (move down)" in st.session_state.skinny_results:
                                selected_names = st.session_state.skinny_results[f"{cname}_bottom (move down)"]
                                down_list = [r for r in ranking if r["name"] in selected_names]
                                for r in reversed(ranking):
                                    if (r["diff"], r["wins"]) < (ranking[-2]["diff"], ranking[-2]["wins"]) and r["name"] not in selected_names:
                                        down_list.append(r)
                                down_list = down_list[-2:]

                            if c_idx > 0:
                                movers_up[cname] = up_list
                            if c_idx < num_courts - 1:
                                movers_down[cname] = down_list

                        for c_idx, cname in enumerate(court_names):
                            ranking = final_rankings[cname]
                            staying = []
                            for r in ranking:
                                is_up = any(r["name"] == m["name"] for m in movers_up[cname])
                                is_down = any(r["name"] == m["name"] for m in movers_down[cname])
                                if not is_up and not is_down:
                                    staying.append(r)

                            incoming_down = movers_down.get(court_names[c_idx - 1], []) if c_idx > 0 else []
                            incoming_up = movers_up.get(court_names[c_idx + 1], []) if c_idx < num_courts - 1 else []

                            ordered = []
                            for r in incoming_down:
                                ordered.append({"Player": r["name"], "+/−": r["diff"], "Matches Won": r["wins"], "Note": f"(moved down from {court_names[c_idx-1]})"})
                                for pl in courts[court_names[c_idx-1]]:
                                    if pl["name"] == r["name"]:
                                        new_courts[cname].append(pl)
                                        break
                            for r in staying:
                                ordered.append({"Player": r["name"], "+/−": r["diff"], "Matches Won": r["wins"], "Note": ""})
                                for pl in courts[cname]:
                                    if pl["name"] == r["name"]:
                                        new_courts[cname].append(pl)
                                        break
                            for r in incoming_up:
                                ordered.append({"Player": r["name"], "+/−": r["diff"], "Matches Won": r["wins"], "Note": f"(moved up from {court_names[c_idx+1]})"})
                                for pl in courts[court_names[c_idx+1]]:
                                    if pl["name"] == r["name"]:
                                        new_courts[cname].append(pl)
                                        break
                            display_data[cname] = ordered

                        st.session_state.assignment_history.append({
                            "title": f"Start of Cycle {st.session_state.cycle + 1} (After Movement)",
                            "type": "new_groups",
                            "data": display_data
                        })

                        new_schedules = {c: generate_schedule(p) for c, p in new_courts.items()}
                        default_score = int(st.session_state.get("play_to", 9))
                        new_scores = {}
                        for cname, schedule in new_schedules.items():
                            for r_idx, rnd in enumerate(schedule):
                                matches = [x for x in rnd if isinstance(x, tuple) and len(x) == 2 and isinstance(x[0], tuple)]
                                for m_idx, match in enumerate(matches):
                                    key = f"{cname}_r{r_idx}_m{m_idx}"
                                    new_scores[key] = (default_score, default_score)

                        st.session_state.courts = new_courts
                        st.session_state.schedules = new_schedules
                        st.session_state.scores = new_scores
                        st.session_state.cycle += 1
                        st.session_state.standings = None
                        st.session_state.relevant_ties = None
                        st.session_state.skinny_results = {}
                        st.session_state.edit_scores_unlocked = False
                        save_state()
                        st.rerun()
            else:
                if st.button("Show Final Results", type="primary"):
                    for cname, ranking in st.session_state.standings.items():
                        for r in ranking:
                            st.session_state.cumulative[r["name"]]["diff"] += r["diff"]
                            st.session_state.cumulative[r["name"]]["wins"] += r["wins"]
                    st.session_state.assignment_history.append({
                        "title": f"Rankings after Cycle {st.session_state.cycle}",
                        "type": "rankings",
                        "data": st.session_state.standings
                    })
                    st.session_state.final_done = True
                    save_state()
                    st.rerun()

    if st.session_state.get("final_done"):
        st.markdown("---")
        st.header("Final Results")
        st.subheader("Top 3 Overall for the Day (Total +/−)")
        cum = st.session_state.cumulative
        overall = sorted(cum.items(), key=lambda x: (x[1]["diff"], x[1]["wins"]), reverse=True)[:3]
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, s) in enumerate(overall):
            st.write(f"{medals[i]} **{name}**  —  +/− {s['diff']:+d}  (Matches Won: {s['wins']})")
        st.subheader("Top 3 from Final Cycle (Court A)")
        if st.session_state.standings and "Court A" in st.session_state.standings:
            for i, r in enumerate(st.session_state.standings["Court A"][:3]):
                st.write(f"{medals[i]} **{r['name']}**  —  +/− {r['diff']:+d}")
        st.success("Session complete!")

if st.session_state.get("created"):
    save_state()
