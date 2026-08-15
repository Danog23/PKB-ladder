import streamlit as st
import pandas as pd
from collections import defaultdict
import json
import os
import copy
import random
from io import BytesIO

from supabase import create_client, Client

# ---------- Supabase connection ----------
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase()

st.set_page_config(page_title="Pickleball Pool Ladder", layout="wide")
st.title("Pickleball Multi-Court Ladder")

st.info("**Note:** If you don’t see the latest scores or rankings, please **refresh the page** or **open the link again**.")

SAVE_FILE = "pickleball_session.json"
HOF_FILE = "hall_of_fame.json"

# ---------- Hall of Fame helpers (Supabase) ----------
def load_hof():
    try:
        result = supabase.table("hall_of_fame").select("*").execute()
        hof = {}
        for row in result.data:
            hof[row["player_name"]] = {
                "diff": 0,
                "wins": 0,
                "sessions": 0,
                "championships": row.get("championships", 0)
            }
        return hof
    except Exception as e:
        st.warning(f"Could not load Hall of Fame: {e}")
        return {}

def save_hof(hof_data):
    # Kept for compatibility – not used the same way with Supabase
    pass

def get_top5_with_ranks(hof_data):
    if not hof_data:
        return []
    items = list(hof_data.items())
    items.sort(key=lambda x: (x[1].get("championships", 0), x[1].get("diff", 0)), reverse=True)

    ranked = []
    current_rank = 0
    prev_key = None
    for name, stats in items:
        key = (stats.get("championships", 0), stats.get("diff", 0))
        if key != prev_key:
            current_rank += 1
        if current_rank > 5:
            break
        ranked.append((current_rank, name, stats))
        prev_key = key
    return ranked

def update_hof_from_session(cumulative):
    try:
        for name, stats in cumulative.items():
            existing = supabase.table("hall_of_fame").select("*").eq("player_name", name).execute()
            if existing.data:
                pass  # We will improve this later with season points
            else:
                supabase.table("hall_of_fame").insert({
                    "player_name": name,
                    "championships": 0
                }).execute()
        return load_hof()
    except Exception as e:
        st.warning(f"Could not update Hall of Fame: {e}")
        return {}

# ---------- Excel export ----------
def create_excel_report():
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Session info
        info = {
            "Setting": ["Courts", "Pools", "Players per pool", "Movers", "Rounds", "Play to"],
            "Value": [
                st.session_state.get("num_courts"),
                st.session_state.get("num_pools"),
                st.session_state.get("players_per_pool"),
                st.session_state.get("movers"),
                st.session_state.get("num_cycles"),
                st.session_state.get("play_to"),
            ]
        }
        pd.DataFrame(info).to_excel(writer, sheet_name="Session Info", index=False)

        # Starting ladder
        if st.session_state.get("assignment_history"):
            start = st.session_state.assignment_history[0]
            if start["type"] == "groups":
                rows = []
                for pname, plist in start["data"].items():
                    for p in plist:
                        rows.append({"Pool": pname, "Player": p["name"], "DUPR": p["dupr"]})
                pd.DataFrame(rows).to_excel(writer, sheet_name="Starting Ladder", index=False)

        # All scores
        score_rows = []
        for entry in st.session_state.get("full_score_history", []):
            for line in entry.get("lines", []):
                score_rows.append({"Round": entry["title"], "Match": line})
        if score_rows:
            pd.DataFrame(score_rows).to_excel(writer, sheet_name="All Scores", index=False)

        # Final cumulative
        cum = st.session_state.get("cumulative", {})
        if cum:
            cum_rows = [{"Player": n, "+/−": s["diff"], "Wins": s["wins"]} for n, s in cum.items()]
            cum_rows = sorted(cum_rows, key=lambda x: (x["+/−"], x["Wins"]), reverse=True)
            pd.DataFrame(cum_rows).to_excel(writer, sheet_name="Final Cumulative", index=False)

        # Hall of Fame
        hof = load_hof()
        top5 = get_top5_with_ranks(hof)
        if top5:
            hof_rows = [{"Rank": r, "Player": n, "+/−": s.get("diff",0), "Wins": s.get("wins",0), "Sessions": s.get("sessions",0)} for r,n,s in top5]
            pd.DataFrame(hof_rows).to_excel(writer, sheet_name="Hall of Fame", index=False)

    output.seek(0)
    return output

# ---------- Normal session helpers ----------
def save_state():
    if not st.session_state.get("created"):
        return
    data = {
        "players": st.session_state.get("players"),
        "pools": st.session_state.get("pools"),
        "pool_names": st.session_state.get("pool_names"),
        "court_names": st.session_state.get("court_names"),
        "schedules": st.session_state.get("schedules"),
        "scores": st.session_state.get("scores"),
        "num_courts": st.session_state.get("num_courts"),
        "num_pools": st.session_state.get("num_pools"),
        "players_per_pool": st.session_state.get("players_per_pool"),
        "movers": st.session_state.get("movers"),
        "num_cycles": st.session_state.get("num_cycles"),
        "cycle": st.session_state.get("cycle"),
        "standings": st.session_state.get("standings"),
        "relevant_ties": st.session_state.get("relevant_ties"),
        "skinny_results": st.session_state.get("skinny_results", {}),
        "cumulative": st.session_state.get("cumulative"),
        "assignment_history": st.session_state.get("assignment_history"),
        "final_done": st.session_state.get("final_done"),
        "admin_password": st.session_state.get("admin_password", "2302"),
        "cycle_snapshots": st.session_state.get("cycle_snapshots", {}),
        "play_to": st.session_state.get("play_to", 9),
        "full_score_history": st.session_state.get("full_score_history", []),
        "locked_matches": st.session_state.get("locked_matches", {}),
        "initial_ranks": st.session_state.get("initial_ranks", {}),
        "use_shared_courts": st.session_state.get("use_shared_courts", False),
        "match_queue": st.session_state.get("match_queue", []),
        "court_status": st.session_state.get("court_status", {}),
        "completed_matches": st.session_state.get("completed_matches", []),
        "court_queues": st.session_state.get("court_queues", {}),
        "hof_priority_players": st.session_state.get("hof_priority_players", []),
    }
    try:
        # Delete old active session and insert the new one
        supabase.table("active_session").delete().neq("id", 0).execute()
        supabase.table("active_session").insert({
            "session_data": data
        }).execute()
    except Exception as e:
        st.warning(f"Could not save session to Supabase: {e}")

def load_state():
    try:
        result = supabase.table("active_session").select("session_data").order("id", desc=True).limit(1).execute()
        if result.data and len(result.data) > 0:
            data = result.data[0]["session_data"]
            for key, value in data.items():
                st.session_state[key] = value
            st.session_state.created = True
            return True
        return False
    except Exception as e:
        st.warning(f"Could not load session from Supabase: {e}")
        return False
# ---------- Initialize ----------
if "admin_unlocked" not in st.session_state:
    st.session_state.admin_unlocked = False
if "admin_password" not in st.session_state:
    st.session_state.admin_password = "2302"
if "created" not in st.session_state:
    load_state()
if "cycle_snapshots" not in st.session_state:
    st.session_state.cycle_snapshots = {}
if "full_score_history" not in st.session_state:
    st.session_state.full_score_history = []
if "show_score_history" not in st.session_state:
    st.session_state.show_score_history = False
if "locked_matches" not in st.session_state:
    st.session_state.locked_matches = {}
if "initial_ranks" not in st.session_state:
    st.session_state.initial_ranks = {}
if "show_finish_pwd" not in st.session_state:
    st.session_state.show_finish_pwd = False
if "match_queue" not in st.session_state:
    st.session_state.match_queue = []
if "court_status" not in st.session_state:
    st.session_state.court_status = {}
if "completed_matches" not in st.session_state:
    st.session_state.completed_matches = []
if "skinny_results" not in st.session_state:
    st.session_state.skinny_results = {}
if "court_queues" not in st.session_state:
    st.session_state.court_queues = {}
if "show_reset_hof" not in st.session_state:
    st.session_state.show_reset_hof = False
if "show_hof_page" not in st.session_state:
    st.session_state.show_hof_page = False
if "hof_priority_players" not in st.session_state:
    st.session_state.hof_priority_players = []

# ---------- Top Admin Bar ----------
c1, c2, c3, c4, c5 = st.columns([1.6, 1.6, 1.6, 1.6, 1.6])

with c1:
    if not st.session_state.admin_unlocked:
        if st.button("Admin Mode"):
            st.session_state.show_admin_login = True
    else:
        st.success("Admin Active")
        if st.button("User Mode"):
            st.session_state.admin_unlocked = False
            st.rerun()

with c2:
    if st.button("🏆 Hall of Fame"):
        st.session_state.show_hof_page = not st.session_state.show_hof_page

with c3:
    if st.session_state.admin_unlocked:
        if st.button("Start New Session"):
            for key in list(st.session_state.keys()):
                if key not in ["admin_password", "admin_unlocked"]:
                    del st.session_state[key]
            try:
                # Clear the active session in Supabase
                supabase.table("active_session").delete().neq("id", 0).execute()
            except Exception:
                pass
            st.session_state.admin_unlocked = True
            st.rerun()

with c4:
    if st.session_state.admin_unlocked:
        if st.button("Change Password"):
            st.session_state.show_change_password = True

with c5:
    if st.session_state.admin_unlocked:
        if st.button("Reset HoF"):
            st.session_state.show_reset_hof = True

# Admin login
if st.session_state.get("show_admin_login") and not st.session_state.admin_unlocked:
    pwd = st.text_input("Enter Admin Password", type="password", key="admin_login")
    if pwd:
        if pwd == st.session_state.admin_password:
            st.session_state.admin_unlocked = True
            st.session_state.show_admin_login = False
            st.rerun()
        else:
            st.error("Wrong password")

# Change password
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

# Reset Hall of Fame
if st.session_state.get("show_reset_hof") and st.session_state.admin_unlocked:
    st.warning("This will permanently delete the Hall of Fame rankings.")
    pwd = st.text_input("Enter Admin Password to confirm Reset", type="password", key="reset_hof_pwd")
    if pwd:
        if pwd == st.session_state.admin_password:
            try:
                # Delete all rows from the hall_of_fame table
                supabase.table("hall_of_fame").delete().neq("id", 0).execute()
                st.session_state.show_reset_hof = False
                st.session_state.hof_priority_players = []
                st.success("✅ Hall of Fame has been completely reset and is now empty.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to reset Hall of Fame: {e}")
        else:
            st.error("Wrong password")

# ---------- Hall of Fame Page ----------
if st.session_state.show_hof_page:
    st.header("🏆 Hall of Fame – Top 5")
    hof_data = load_hof()
    top5 = get_top5_with_ranks(hof_data)
    if top5:
        for rank, name, stats in top5:
            st.write(f"**{rank}. {name}**  —  +/− **{stats.get('diff', 0):+d}**  |  Wins: {stats.get('wins', 0)}  |  Sessions: {stats.get('sessions', 0)}")
    else:
        st.info("Hall of Fame is empty. Complete a session to start building it.")
    
    if st.button("Close Hall of Fame"):
        st.session_state.show_hof_page = False
        st.rerun()
    st.markdown("---")

# ---------- Session Setup ----------
if st.session_state.admin_unlocked and not st.session_state.get("created"):
    st.header("1. Session Setup (Admin)")

    col1, col2, col3 = st.columns(3)
    with col1:
        num_courts = st.number_input("Number of physical courts", min_value=1, max_value=6, value=2)
    with col2:
        preferred_pools = st.number_input("Preferred number of pools", min_value=2, max_value=8, value=3)
    with col3:
        preferred_size = st.selectbox("Preferred players per pool", [4, 5, 6], index=0)

    col4, col5, col6 = st.columns(3)
    with col4:
        movers = st.selectbox("Players move up/down each round", [1, 2], index=0)
    with col5:
        num_cycles = st.number_input("Number of rounds", min_value=1, max_value=6, value=3)
    with col6:
        play_to = st.number_input("Play to", min_value=7, max_value=21, value=9)

    max_players = preferred_pools * preferred_size
    st.caption(f"Maximum capacity: **{max_players}** players.")

    st.header("2. Enter Players")
    st.caption(f"Format: Name, DUPR. Maximum **{max_players}** players.")
    st.caption("Players currently in the Hall of Fame Top 5 will automatically get the highest starting positions.")

    default_players = """Alex, 5.3
Jordan, 5.1
Sam, 4.9
Taylor, 4.8
Casey, 4.6
Riley, 4.5
Morgan, 4.4
Jamie, 4.3
Quinn, 4.2
Avery, 4.1
Reese, 4.0
Skyler, 3.9"""

    player_text = st.text_area("Players (Name, DUPR)", height=280, value=default_players)

    if st.button("Create Session", type="primary"):
        players = []
        for line in player_text.strip().splitlines():
            if "," in line:
                try:
                    name, dupr = line.split(",", 1)
                    players.append({"name": name.strip(), "dupr": float(dupr.strip())})
                except:
                    pass

        if len(players) < 3:
            st.error("Need at least 3 players")
        elif len(players) > max_players:
            st.error(f"Too many players. Maximum is **{max_players}**.")
        else:
            hof = load_hof()
            top5_list = get_top5_with_ranks(hof)
            top5_names = [name for _, name, _ in top5_list]
            
            hof_players = []
            other_players = []
            
            if top5_names:
                for p in players:
                    if p["name"] in top5_names:
                        hof_players.append(p)
                    else:
                        other_players.append(p)
                hof_players.sort(key=lambda p: top5_names.index(p["name"]) if p["name"] in top5_names else 999)
            else:
                other_players = players[:]
            
            other_players = sorted(other_players, key=lambda x: x["dupr"], reverse=True)
            players = hof_players + other_players
            hof_priority_names = [p["name"] for p in hof_players]

            sizes = smart_distribute(len(players), preferred_pools, preferred_size, min_size=3)

            if not sizes:
                st.error("Could not create valid pools")
            else:
                actual_pools = len(sizes)
                use_shared = actual_pools > num_courts

                pools = {}
                pool_names = []
                idx = 0
                for i, size in enumerate(sizes):
                    pname = f"Pool {chr(65 + i)}"
                    pools[pname] = players[idx:idx + size]
                    pool_names.append(pname)
                    idx += size

                size_str = " – ".join(str(s) for s in sizes)
                st.success(f"Adapted to **{len(players)} players** → {size_str}")
                
                if hof_priority_names:
                    st.info(f"Hall of Fame priority given to: {', '.join(hof_priority_names)}")
                else:
                    st.info("Hall of Fame is empty — all players sorted by DUPR only.")

                court_names = [f"Court {i+1}" for i in range(num_courts)]
                schedules = {p: generate_schedule(pl) for p, pl in pools.items()}

                scores = {}
                for pname, schedule in schedules.items():
                    for r_idx, rnd in enumerate(schedule):
                        matches = [x for x in rnd if is_match(x)]
                        for m_idx, match in enumerate(matches):
                            key = f"{pname}_r{r_idx}_m{m_idx}"
                            if random.random() < 0.5:
                                scores[key] = (play_to, play_to - 1)
                            else:
                                scores[key] = (play_to - 1, play_to)

                cumulative = {p["name"]: {"diff": 0, "wins": 0} for p in players}
                initial_ranks = {p["name"]: i + 1 for i, p in enumerate(players)}

                match_queue = []
                court_status = {c: None for c in court_names}
                court_queues = {}

                if use_shared:
                    match_queue = build_interleaved_queue(schedules, pool_names)
                    for i, court in enumerate(court_names):
                        if i < len(match_queue):
                            court_status[court] = match_queue[i]
                    match_queue = match_queue[len(court_names):]
                else:
                    court_queues = build_court_queues(schedules, pool_names, court_names)
                    for court, q in court_queues.items():
                        if q:
                            court_status[court] = q[0]
                            court_queues[court] = q[1:]

                st.session_state.assignment_history = [{
                    "title": "Starting Pool Play Ladder (Hall of Fame + DUPR)",
                    "type": "groups",
                    "data": pools
                }]
                st.session_state.players = players
                st.session_state.pools = pools
                st.session_state.pool_names = pool_names
                st.session_state.court_names = court_names
                st.session_state.schedules = schedules
                st.session_state.scores = scores
                st.session_state.num_courts = num_courts
                st.session_state.num_pools = actual_pools
                st.session_state.players_per_pool = preferred_size
                st.session_state.movers = movers
                st.session_state.num_cycles = num_cycles
                st.session_state.play_to = play_to
                st.session_state.use_shared_courts = use_shared
                st.session_state.created = True
                st.session_state.cycle = 1
                st.session_state.standings = None
                st.session_state.relevant_ties = None
                st.session_state.skinny_results = {}
                st.session_state.cumulative = cumulative
                st.session_state.final_done = False
                st.session_state.cycle_snapshots = {}
                st.session_state.full_score_history = []
                st.session_state.show_score_history = False
                st.session_state.locked_matches = {}
                st.session_state.initial_ranks = initial_ranks
                st.session_state.show_finish_pwd = False
                st.session_state.match_queue = match_queue
                st.session_state.court_status = court_status
                st.session_state.completed_matches = []
                st.session_state.court_queues = court_queues
                st.session_state.hof_priority_players = hof_priority_names
                save_state()
                st.rerun()

# ---------- Main ----------
if st.session_state.get("created"):
    if "skinny_results" not in st.session_state:
        st.session_state.skinny_results = {}

    pools = st.session_state.pools
    pool_names = st.session_state.pool_names
    court_names = st.session_state.court_names
    schedules = st.session_state.schedules
    num_courts = st.session_state.num_courts
    num_pools = st.session_state.num_pools
    movers = st.session_state.get("movers", 1)
    num_cycles = st.session_state.num_cycles
    is_admin = st.session_state.admin_unlocked
    play_to = st.session_state.get("play_to", 9)
    use_shared = st.session_state.get("use_shared_courts", False)
    players_per_pool = st.session_state.get("players_per_pool", 4)
    hof_priority = st.session_state.get("hof_priority_players", [])

    mode_label = "Mode 2 (Shared)" if use_shared else "Mode 1 (Dedicated)"
    st.success(f"Round {st.session_state.cycle} of {num_cycles}  |  {mode_label}  |  {sum(len(p) for p in pools.values())} players")

    st.caption(
        f"**Settings:** {num_courts} courts · {num_pools} pools · {players_per_pool} per pool · "
        f"{movers} mover(s) · {num_cycles} rounds · play to {play_to} · {mode_label}"
    )

    if st.button("View Full Score History"):
        st.session_state.show_score_history = not st.session_state.show_score_history

    if st.session_state.show_score_history:
        st.markdown("---")
        st.header("Full Score History")
        if not st.session_state.full_score_history:
            st.info("No scores recorded yet.")
        else:
            for entry in st.session_state.full_score_history:
                st.subheader(entry["title"])
                for line in entry["lines"]:
                    st.write(line)
        if st.button("Close Score History"):
            st.session_state.show_score_history = False
            st.rerun()

    st.markdown("---")
    st.header("Full History")

    for idx, entry in enumerate(st.session_state.assignment_history):
        colh1, colh2 = st.columns([6, 1])
        with colh1:
            st.subheader(entry["title"])
        with colh2:
            if is_admin and entry["type"] == "rankings" and "Rankings after Round" in entry["title"]:
                try:
                    cycle_num = int(entry["title"].split("Round ")[1])
                    if st.button("Edit", key=f"edit_hist_{cycle_num}_{idx}"):
                        st.session_state[f"ask_pwd_edit_{cycle_num}"] = True
                except:
                    pass

        if is_admin and entry["type"] == "rankings" and "Rankings after Round" in entry["title"]:
            try:
                cycle_num = int(entry["title"].split("Round ")[1])
                if st.session_state.get(f"ask_pwd_edit_{cycle_num}", False):
                    pwd = st.text_input(f"Re-enter Admin Password to edit Round {cycle_num}", type="password", key=f"pwd_e_{cycle_num}")
                    if pwd:
                        if pwd == st.session_state.admin_password:
                            if str(cycle_num) in st.session_state.cycle_snapshots:
                                snap = st.session_state.cycle_snapshots[str(cycle_num)]
                                
                                # Restore the exact state from the snapshot
                                st.session_state.pools = copy.deepcopy(snap.get("pools", st.session_state.pools))
                                st.session_state.schedules = copy.deepcopy(snap.get("schedules", st.session_state.schedules))
                                st.session_state.scores = copy.deepcopy(snap.get("scores", {}))
                                st.session_state.cycle = cycle_num
                                st.session_state.standings = None
                                st.session_state.relevant_ties = None
                                st.session_state.skinny_results = {}
                                st.session_state.final_done = False
                                st.session_state.assignment_history = st.session_state.assignment_history[:idx]
                                st.session_state[f"ask_pwd_edit_{cycle_num}"] = False
                                
                                # Rebuild queues but KEEP the restored scores
                                if use_shared:
                                    mq = build_interleaved_queue(st.session_state.schedules, pool_names)
                                    cs = {c: None for c in court_names}
                                    for i, court in enumerate(court_names):
                                        if i < len(mq):
                                            cs[court] = mq[i]
                                    st.session_state.match_queue = mq[len(court_names):]
                                    st.session_state.court_status = cs
                                else:
                                    cq = build_court_queues(st.session_state.schedules, pool_names, court_names)
                                    cs = {c: None for c in court_names}
                                    for court, q in cq.items():
                                        if q:
                                            cs[court] = q[0]
                                            cq[court] = q[1:]
                                    st.session_state.court_queues = cq
                                    st.session_state.court_status = cs
                                
                                # Mark all matches as unlocked so they can be edited, but scores stay
                                st.session_state.locked_matches = {}
                                st.session_state.completed_matches = []
                                
                                save_state()
                                st.success(f"Restored Round {cycle_num} with the original scores. You can now edit them.")
                                st.rerun()
                        else:
                            st.error("Wrong password")
            except Exception as e:
                st.error(f"Error restoring: {e}")

        if entry["type"] in ["groups", "rankings", "new_groups"]:
            cols = st.columns(min(len(pool_names), 4))
            for i, pname in enumerate(pool_names):
                with cols[i % len(cols)]:
                    st.markdown(f"**{pname}**")
                    if entry["type"] == "groups":
                        plist = entry["data"].get(pname, [])
                        if plist:
                            display_rows = []
                            for p in plist:
                                note = "🏆 Hall of Fame" if p["name"] in hof_priority else ""
                                display_rows.append({
                                    "Player": p["name"],
                                    "DUPR": p["dupr"],
                                    "Note": note
                                })
                            st.dataframe(pd.DataFrame(display_rows), hide_index=True, use_container_width=True)
                    elif entry["type"] == "rankings":
                        ranking = entry["data"].get(pname, [])
                        if ranking:
                            data = [{"#": j+1, "Player": r["name"], "+/−": r["diff"], "W": r["wins"]} for j, r in enumerate(ranking)]
                            st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)
                    elif entry["type"] == "new_groups":
                        rows = entry["data"].get(pname, [])
                        if rows:
                            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.markdown("")

    # ==================== UNIFIED COURT BOARD ====================
    if not st.session_state.get("final_done") and not st.session_state.get("standings"):
        st.markdown("---")
        st.header("Court Board")

        st.subheader("Now Playing")
        for court in court_names:
            status = st.session_state.court_status.get(court)
            if status:
                t1, t2 = status["match"]
                key = status["key"]
                current = st.session_state.scores.get(key, (play_to, play_to - 1))

                st.markdown(f"**{court}** — {status['pool']} (Match {status['round']})")
                st.markdown(f"**{t1[0]} & {t1[1]}**  vs  **{t2[0]} & {t2[1]}**")

                if is_admin:
                    col1, col2, col3, col4 = st.columns([1.1, 1.1, 1.3, 1.3])
                    with col1:
                        s1 = st.number_input("s1", min_value=0, max_value=30, value=int(current[0]), key=f"s1_{court}_{key}", label_visibility="collapsed")
                    with col2:
                        s2 = st.number_input("s2", min_value=0, max_value=30, value=int(current[1]), key=f"s2_{court}_{key}", label_visibility="collapsed")
                    with col3:
                        if st.button("Save & Next", key=f"save_{court}_{key}"):
                            st.session_state.scores[key] = (s1, s2)
                            st.session_state.locked_matches[key] = True
                            st.session_state.completed_matches.append(status)

                            if use_shared:
                                if st.session_state.match_queue:
                                    next_match = st.session_state.match_queue.pop(0)
                                    st.session_state.court_status[court] = next_match
                                else:
                                    st.session_state.court_status[court] = None
                            else:
                                q = st.session_state.court_queues.get(court, [])
                                if q:
                                    next_match = q.pop(0)
                                    st.session_state.court_status[court] = next_match
                                    st.session_state.court_queues[court] = q
                                else:
                                    st.session_state.court_status[court] = None
                            save_state()
                            st.rerun()
                    with col4:
                        if st.button("Skip", key=f"skip_{court}_{key}"):
                            if use_shared:
                                st.session_state.match_queue.append(status)
                                if st.session_state.match_queue:
                                    next_match = st.session_state.match_queue.pop(0)
                                    st.session_state.court_status[court] = next_match
                                else:
                                    st.session_state.court_status[court] = None
                            else:
                                q = st.session_state.court_queues.get(court, [])
                                q.append(status)
                                if q:
                                    next_match = q.pop(0)
                                    st.session_state.court_status[court] = next_match
                                    st.session_state.court_queues[court] = q
                                else:
                                    st.session_state.court_status[court] = None
                            save_state()
                            st.rerun()
                else:
                    if st.session_state.locked_matches.get(key, False):
                        st.write(f"Score: **{current[0]} – {current[1]}**")
                    else:
                        st.caption("Score not yet entered")
                st.markdown("---")
            else:
                st.write(f"**{court}**: Free / Finished")
                st.markdown("---")

        st.subheader("Up Next")
        if use_shared:
            queue = st.session_state.match_queue
            if queue:
                for i, item in enumerate(queue[:10]):
                    t1, t2 = item["match"]
                    st.write(f"{i+1}. **{item['pool']}** Match {item['round']}: {t1[0]} & {t1[1]} vs {t2[0]} & {t2[1]}")
                if len(queue) > 10:
                    st.caption(f"... and {len(queue)-10} more")
            else:
                st.info("No more matches waiting")
        else:
            any_left = False
            for court in court_names:
                q = st.session_state.court_queues.get(court, [])
                if q:
                    any_left = True
                    st.markdown(f"**{court}**")
                    for i, item in enumerate(q[:5]):
                        t1, t2 = item["match"]
                        st.write(f"  {i+1}. Match {item['round']}: {t1[0]} & {t1[1]} vs {t2[0]} & {t2[1]}")
            if not any_left:
                st.info("No more matches waiting")

        st.subheader("Games Completed")
        completed = st.session_state.get("completed_matches", [])
        if completed:
            for i, item in enumerate(reversed(completed)):
                t1, t2 = item["match"]
                key = item["key"]
                score = st.session_state.scores.get(key, (0, 0))

                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**{item['pool']}** Match {item['round']}: {t1[0]} & {t1[1]} vs {t2[0]} & {t2[1]}  →  **{score[0]}–{score[1]}**")
                with col2:
                    if is_admin:
                        if st.button("Edit", key=f"edit_c_{key}_{i}"):
                            st.session_state.locked_matches[key] = False
                            st.session_state[f"editing_{key}"] = True
                            save_state()
                            st.rerun()

                if is_admin and st.session_state.get(f"editing_{key}", False):
                    c1, c2, c3 = st.columns([1.2, 1.2, 1.5])
                    with c1:
                        ns1 = st.number_input("s1", min_value=0, max_value=30, value=int(score[0]), key=f"es1_{key}")
                    with c2:
                        ns2 = st.number_input("s2", min_value=0, max_value=30, value=int(score[1]), key=f"es2_{key}")
                    with c3:
                        if st.button("Update", key=f"upd_{key}"):
                            st.session_state.scores[key] = (ns1, ns2)
                            st.session_state.locked_matches[key] = True
                            st.session_state[f"editing_{key}"] = False
                            save_state()
                            st.rerun()
        else:
            st.caption("No games completed yet")

        all_done = all(st.session_state.court_status.get(c) is None for c in court_names)
        if use_shared:
            all_done = all_done and not st.session_state.match_queue
        else:
            all_done = all_done and all(len(st.session_state.court_queues.get(c, [])) == 0 for c in court_names)

        if all_done and is_admin:
            st.success("All matches in this round are complete!")
            if st.button("Calculate Rankings + Check Skinny Singles", type="primary"):
                standings = {}
                relevant_ties = {}
                cycle_lines = []
                for p_idx, pname in enumerate(pool_names):
                    schedule = schedules[pname]
                    diff = defaultdict(int)
                    wins = defaultdict(int)
                    for r_idx, rnd in enumerate(schedule):
                        matches = [x for x in rnd if is_match(x)]
                        for m_idx, match in enumerate(matches):
                            key = f"{pname}_r{r_idx}_m{m_idx}"
                            s1, s2 = st.session_state.scores.get(key, (0, 0))
                            t1, t2 = match
                            pdif = s1 - s2
                            for p in t1: diff[p] += pdif
                            for p in t2: diff[p] -= pdif
                            if s1 > s2:
                                for p in t1: wins[p] += 1
                            elif s2 > s1:
                                for p in t2: wins[p] += 1
                            cycle_lines.append(f"{pname} Match {r_idx+1}: {t1[0]} & {t1[1]} vs {t2[0]} & {t2[1]} → {s1}-{s2}")
                    ranking = [{"name": p["name"], "diff": diff[p["name"]], "wins": wins[p["name"]]} for p in pools[pname]]
                    ranking.sort(key=lambda x: (x["diff"], x["wins"]), reverse=True)
                    standings[pname] = ranking

                    n = len(ranking)
                    ties = []
                    is_top = (p_idx == 0)
                    is_bot = (p_idx == num_pools - 1)
                    move_n = min(movers, n // 2) if n >= 2 else 0
                    if not is_top and move_n > 0:
                        sc = (ranking[move_n-1]["diff"], ranking[move_n-1]["wins"])
                        grp = [r for r in ranking if (r["diff"], r["wins"]) == sc]
                        if len(grp) > move_n:
                            ties.append({"zone": "top (move up)", "players": [r["name"] for r in grp], "score": grp[0]["diff"], "needed": move_n})
                    if not is_bot and move_n > 0:
                        sc = (ranking[-move_n]["diff"], ranking[-move_n]["wins"])
                        grp = [r for r in ranking if (r["diff"], r["wins"]) == sc]
                        if len(grp) > move_n:
                            ties.append({"zone": "bottom (move down)", "players": [r["name"] for r in grp], "score": grp[0]["diff"], "needed": move_n})
                    if ties:
                        relevant_ties[pname] = ties

                # Save snapshot WITH the real scores
                st.session_state.cycle_snapshots[str(st.session_state.cycle)] = {
                    "pools": copy.deepcopy(pools),
                    "schedules": copy.deepcopy(schedules),
                    "scores": copy.deepcopy(st.session_state.scores)
                }

                st.session_state.full_score_history.append({"title": f"Round {st.session_state.cycle} Scores", "lines": cycle_lines})
                st.session_state.standings = standings
                st.session_state.relevant_ties = relevant_ties
                st.session_state.skinny_results = {}
                save_state()
                st.rerun()

    # ==================== RANKINGS + MOVEMENT ====================
    if st.session_state.get("standings") and not st.session_state.get("final_done"):
        st.markdown("---")
        st.header(f"Rankings after Round {st.session_state.cycle}")

        cols = st.columns(min(len(pool_names), 4))
        for i, pname in enumerate(pool_names):
            with cols[i % len(cols)]:
                st.subheader(pname)
                data = [{"#": j+1, "Player": r["name"], "+/−": r["diff"], "W": r["wins"]} for j, r in enumerate(st.session_state.standings[pname])]
                st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)

        has_conflict = False
        if st.session_state.get("relevant_ties") and is_admin:
            st.markdown("---")
            st.header("Skinny Singles Required")
            current_selections = {}
            for pname, ties in st.session_state.relevant_ties.items():
                for tie in ties:
                    key = f"{pname}_{tie['zone']}"
                    selected = []
                    st.write(f"**{pname} – {tie['zone']}** (tied at {tie['score']:+d})")
                    st.write(f"Select exactly {tie['needed']} player(s):")
                    cbs = st.columns(min(len(tie["players"]), 4))
                    for i, p in enumerate(tie["players"]):
                        with cbs[i % len(cbs)]:
                            if st.checkbox(p, key=f"sk_{key}_{p}"):
                                selected.append(p)
                    current_selections[key] = selected
                    if len(selected) == tie["needed"]:
                        st.session_state.skinny_results[key] = selected
                        st.success(f"Selected: {', '.join(selected)}")

            up_players = set()
            down_players = set()
            for key, selected in current_selections.items():
                if "move up" in key:
                    up_players.update(selected)
                if "move down" in key:
                    down_players.update(selected)
            conflict = up_players.intersection(down_players)
            if conflict:
                has_conflict = True
                st.error(f"Same player selected for up and down: {', '.join(conflict)}")

        if is_admin:
            st.markdown("---")
            st.subheader("Next Action")
            col_a, col_b = st.columns(2)

            with col_a:
                if st.session_state.cycle < num_cycles and not has_conflict:
                    if st.button("Apply Movement & Start Next Round", type="primary"):
                        for pname, ranking in st.session_state.standings.items():
                            for r in ranking:
                                st.session_state.cumulative[r["name"]]["diff"] += r["diff"]
                                st.session_state.cumulative[r["name"]]["wins"] += r["wins"]

                        st.session_state.assignment_history.append({
                            "title": f"Rankings after Round {st.session_state.cycle}",
                            "type": "rankings",
                            "data": st.session_state.standings
                        })

                        final_rankings = st.session_state.standings
                        new_pools = {name: [] for name in pool_names}
                        display_data = {name: [] for name in pool_names}
                        movers_up = {name: [] for name in pool_names}
                        movers_down = {name: [] for name in pool_names}
                        move_n = movers

                        for p_idx, pname in enumerate(pool_names):
                            ranking = final_rankings[pname]
                            up_list = ranking[:move_n] if p_idx > 0 else []
                            down_list = ranking[-move_n:] if p_idx < num_pools - 1 else []

                            if f"{pname}_top (move up)" in st.session_state.skinny_results:
                                selected = st.session_state.skinny_results[f"{pname}_top (move up)"]
                                up_list = [r for r in ranking if r["name"] in selected][:move_n]
                            if f"{pname}_bottom (move down)" in st.session_state.skinny_results:
                                selected = st.session_state.skinny_results[f"{pname}_bottom (move down)"]
                                down_list = [r for r in ranking if r["name"] in selected][-move_n:]

                            if p_idx > 0:
                                movers_up[pname] = up_list
                            if p_idx < num_pools - 1:
                                movers_down[pname] = down_list

                        for p_idx, pname in enumerate(pool_names):
                            ranking = final_rankings[pname]
                            staying = [r for r in ranking if not any(r["name"] == m["name"] for m in movers_up[pname] + movers_down[pname])]
                            incoming_down = movers_down.get(pool_names[p_idx-1], []) if p_idx > 0 else []
                            incoming_up = movers_up.get(pool_names[p_idx+1], []) if p_idx < num_pools - 1 else []

                            ordered = []
                            for r in incoming_down:
                                ordered.append({"Player": r["name"], "+/−": 0, "Note": f"(down from {pool_names[p_idx-1]})"})
                                for pl in pools[pool_names[p_idx-1]]:
                                    if pl["name"] == r["name"]:
                                        new_pools[pname].append(pl)
                                        break
                            for r in staying:
                                ordered.append({"Player": r["name"], "+/−": 0, "Note": ""})
                                for pl in pools[pname]:
                                    if pl["name"] == r["name"]:
                                        new_pools[pname].append(pl)
                                        break
                            for r in incoming_up:
                                ordered.append({"Player": r["name"], "+/−": 0, "Note": f"(up from {pool_names[p_idx+1]})"})
                                for pl in pools[pool_names[p_idx+1]]:
                                    if pl["name"] == r["name"]:
                                        new_pools[pname].append(pl)
                                        break
                            display_data[pname] = ordered

                        st.session_state.assignment_history.append({
                            "title": f"Start of Round {st.session_state.cycle + 1} (After Movement)",
                            "type": "new_groups",
                            "data": display_data
                        })

                        new_schedules = {p: generate_schedule(pl) for p, pl in new_pools.items()}
                        new_scores = {}
                        for pname, schedule in new_schedules.items():
                            for r_idx, rnd in enumerate(schedule):
                                matches = [x for x in rnd if is_match(x)]
                                for m_idx, match in enumerate(matches):
                                    key = f"{pname}_r{r_idx}_m{m_idx}"
                                    if random.random() < 0.5:
                                        new_scores[key] = (play_to, play_to - 1)
                                    else:
                                        new_scores[key] = (play_to - 1, play_to)

                        # Keep old scores + add new ones
                        st.session_state.scores.update(new_scores)

                        match_queue = []
                        court_status = {c: None for c in court_names}
                        court_queues = {}

                        if use_shared:
                            match_queue = build_interleaved_queue(new_schedules, pool_names)
                            for i, court in enumerate(court_names):
                                if i < len(match_queue):
                                    court_status[court] = match_queue[i]
                            match_queue = match_queue[len(court_names):]
                        else:
                            court_queues = build_court_queues(new_schedules, pool_names, court_names)
                            for court, q in court_queues.items():
                                if q:
                                    court_status[court] = q[0]
                                    court_queues[court] = q[1:]

                        st.session_state.pools = new_pools
                        st.session_state.schedules = new_schedules
                        st.session_state.cycle += 1
                        st.session_state.standings = None
                        st.session_state.relevant_ties = None
                        st.session_state.skinny_results = {}
                        st.session_state.locked_matches = {}
                        st.session_state.match_queue = match_queue
                        st.session_state.court_status = court_status
                        st.session_state.court_queues = court_queues
                        st.session_state.completed_matches = []
                        save_state()
                        st.rerun()

            with col_b:
                if st.button("Finish Session Now"):
                    st.session_state.show_finish_pwd = True

            if st.session_state.get("show_finish_pwd"):
                pwd = st.text_input("Re-enter Admin Password to finish early", type="password", key="finish_pwd")
                if pwd:
                    if pwd == st.session_state.admin_password:
                        for pname, ranking in st.session_state.standings.items():
                            for r in ranking:
                                st.session_state.cumulative[r["name"]]["diff"] += r["diff"]
                                st.session_state.cumulative[r["name"]]["wins"] += r["wins"]
                        st.session_state.assignment_history.append({
                            "title": f"Rankings after Round {st.session_state.cycle}",
                            "type": "rankings",
                            "data": st.session_state.standings
                        })
                        st.session_state.final_done = True
                        st.session_state.show_finish_pwd = False
                        save_state()
                        st.rerun()
                    else:
                        st.error("Wrong password")

    # ==================== FINAL RESULTS + HALL OF FAME + EXCEL ----------
    if st.session_state.get("final_done"):
        st.markdown("---")
        st.header("Final Results")

        st.subheader("Top 3 Overall for the Day (Total +/−)")
        cum = st.session_state.cumulative
        overall_list = sorted(cum.items(), key=lambda x: (x[1]["diff"], x[1]["wins"]), reverse=True)
        for medal, (name, s) in assign_medals(overall_list, key_func=lambda x: (x[1]["diff"], x[1]["wins"])):
            st.write(f"{medal} **{name}**  —  +/− {s['diff']:+d}  (Matches Won: {s['wins']})")

        st.subheader("Top 3 from Final Top Pool")
        if st.session_state.standings and pool_names:
            top_pool = st.session_state.standings.get(pool_names[0], [])
            for medal, r in assign_medals(top_pool, key_func=lambda x: (x["diff"], x["wins"])):
                st.write(f"{medal} **{r['name']}**  —  +/− {r['diff']:+d}")

        st.subheader("Biggest Climbers")
        initial_ranks = st.session_state.get("initial_ranks", {})
        final_ranks = {}
        rank_counter = 1
        if st.session_state.standings:
            for pname in pool_names:
                for r in st.session_state.standings.get(pname, []):
                    final_ranks[r["name"]] = rank_counter
                    rank_counter += 1

        climbers = []
        for name, start_rank in initial_ranks.items():
            final_rank = final_ranks.get(name)
            if final_rank is not None:
                climbed = start_rank - final_rank
                climbers.append({"name": name, "climbed": climbed, "start": start_rank, "final": final_rank})
        climbers.sort(key=lambda x: x["climbed"], reverse=True)
        for medal, c in assign_medals(climbers, key_func=lambda x: x["climbed"]):
            st.write(f"{medal} **{c['name']}**  —  Climbed **{c['climbed']:+d}** positions (Start #{c['start']} → Final #{c['final']})")

        # Hall of Fame update
        st.markdown("---")
        st.header("🏆 Hall of Fame Updated")
        updated_hof = update_hof_from_session(st.session_state.cumulative)
        top5 = get_top5_with_ranks(updated_hof)
        
        if top5:
            for rank, name, stats in top5:
                st.write(f"**{rank}. {name}**  —  +/− {stats.get('diff', 0):+d}  |  Wins: {stats.get('wins', 0)}  |  Sessions: {stats.get('sessions', 0)}")
        else:
            st.info("Hall of Fame is empty.")

        st.success("Session complete! Hall of Fame has been updated.")

        # Excel Download
        st.markdown("---")
        st.subheader("Download Session Report")
        try:
            excel_data = create_excel_report()
            st.download_button(
                label="📥 Download Excel Report",
                data=excel_data,
                file_name="pickleball_session_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.warning(f"Could not generate Excel (you may need openpyxl). Error: {e}")

if st.session_state.get("created"):
    save_state()
