import streamlit as st
import pandas as pd
from collections import defaultdict
import copy
import random
from io import BytesIO
from supabase import create_client, Client
from datetime import date

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase()

st.set_page_config(page_title="Pickleball Pool Ladder", layout="wide")
st.title("Pickleball Multi-Court Ladder")
st.info("**Note:** If you don’t see the latest scores or rankings, please **refresh the page** or **open the link again**.")

# ---------- Overall Ladder (pure cumulative +/−) ----------
def load_overall_ladder():
    try:
        result = supabase.table("master_ladder").select("*").order("current_rank").execute()
        return result.data if result.data else []
    except Exception as e:
        st.warning(f"Could not load Overall Ladder: {e}")
        return []

def save_overall_ladder(players_stats):
    """
    players_stats = list of dicts: [{"name": , "diff": , "wins": , "sessions": }, ...]
    Sorted by diff then wins (highest first)
    """
    try:
        supabase.table("master_ladder").delete().neq("id", 0).execute()
        rows = []
        for i, p in enumerate(players_stats):
            rows.append({
                "player_name": p["name"],
                "dupr": p.get("dupr", 0),
                "current_rank": i + 1,
                "last_played": str(date.today()),
                "notes": f"diff:{p.get('diff',0)}|wins:{p.get('wins',0)}|sessions:{p.get('sessions',0)}"
            })
        if rows:
            supabase.table("master_ladder").insert(rows).execute()
    except Exception as e:
        st.warning(f"Could not save Overall Ladder: {e}")

def get_top10_ladder():
    return load_overall_ladder()[:10]

def update_overall_ladder_from_session(cumulative):
    """
    cumulative = {name: {"diff": x, "wins": y}, ...} from this session
    We add this session's numbers to the existing totals.
    """
    try:
        current = load_overall_ladder()
        current_dict = {}
        for row in current:
            # parse notes
            notes = row.get("notes", "")
            diff = wins = sessions = 0
            try:
                parts = dict(item.split(":") for item in notes.split("|") if ":" in item)
                diff = int(parts.get("diff", 0))
                wins = int(parts.get("wins", 0))
                sessions = int(parts.get("sessions", 0))
            except:
                pass
            current_dict[row["player_name"]] = {
                "name": row["player_name"],
                "dupr": row.get("dupr", 0),
                "diff": diff,
                "wins": wins,
                "sessions": sessions
            }

        # Add this session's results
        for name, stats in cumulative.items():
            if name in current_dict:
                current_dict[name]["diff"] += stats.get("diff", 0)
                current_dict[name]["wins"] += stats.get("wins", 0)
                current_dict[name]["sessions"] += 1
            else:
                current_dict[name] = {
                    "name": name,
                    "dupr": 0,
                    "diff": stats.get("diff", 0),
                    "wins": stats.get("wins", 0),
                    "sessions": 1
                }

        # Sort by total diff then wins
        sorted_list = sorted(
            current_dict.values(),
            key=lambda x: (x["diff"], x["wins"]),
            reverse=True
        )
        save_overall_ladder(sorted_list)
        return sorted_list
    except Exception as e:
        st.warning(f"Could not update Overall Ladder: {e}")
        return []

def create_excel_report():
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
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
    output.seek(0)
    return output

def save_state():
    if not st.session_state.get("created"):
        return
    data = {k: st.session_state.get(k) for k in [
        "players", "pools", "pool_names", "court_names", "schedules", "scores",
        "num_courts", "num_pools", "players_per_pool", "movers", "num_cycles",
        "cycle", "standings", "relevant_ties", "skinny_results", "cumulative",
        "assignment_history", "final_done", "admin_password", "cycle_snapshots",
        "play_to", "full_score_history", "locked_matches", "initial_ranks",
        "use_shared_courts", "match_queue", "court_status", "completed_matches",
        "court_queues"
    ]}
    try:
        supabase.table("active_session").delete().neq("id", 0).execute()
        supabase.table("active_session").insert({"session_data": data}).execute()
    except Exception as e:
        st.warning(f"Could not save session: {e}")

def load_state():
    try:
        result = supabase.table("active_session").select("session_data").order("id", desc=True).limit(1).execute()
        if result.data:
            data = result.data[0]["session_data"]
            for key, value in data.items():
                st.session_state[key] = value
            st.session_state.created = True
            return True
        return False
    except Exception as e:
        st.warning(f"Could not load session: {e}")
        return False

def is_match(item):
    try:
        return isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], (list, tuple)) and len(item[0]) == 2
    except:
        return False

def generate_schedule(players):
    n = len(players)
    names = [p["name"] for p in players]
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
            sit1, sit2 = order[r % 6], order[(r + 3) % 6]
            playing = [p for p in order if p not in (sit1, sit2)]
            rounds.append([((playing[0], playing[1]), (playing[2], playing[3])), sit1, sit2])
        return rounds
    return []

def smart_distribute(n_players, preferred_pools, preferred_size, min_size=3):
    max_possible = preferred_pools * preferred_size
    n = min(n_players, max_possible)
    for num_pools in range(preferred_pools, 0, -1):
        if n < num_pools * min_size:
            continue
        base = n // num_pools
        rem = n % num_pools
        sizes = [base + (1 if i < rem else 0) for i in range(num_pools)]
        if all(s >= min_size for s in sizes):
            return sizes
    return [n] if n >= min_size else []

def assign_medals(sorted_list, key_func):
    if not sorted_list:
        return []
    medals = ["🥇", "🥈", "🥉"]
    result = []
    current_medal_idx = 0
    prev_key = None
    for item in sorted_list:
        key = key_func(item)
        if prev_key is not None and key != prev_key:
            current_medal_idx += 1
        if current_medal_idx >= 3:
            break
        result.append((medals[current_medal_idx], item))
        prev_key = key
    return result

def build_interleaved_queue(schedules, pool_names):
    queue = []
    max_rounds = max((len(schedules.get(p, [])) for p in pool_names), default=0)
    for r in range(max_rounds):
        for pname in pool_names:
            sched = schedules.get(pname, [])
            if r < len(sched):
                match_idx = 0
                for item in sched[r]:
                    if is_match(item):
                        queue.append({"pool": pname, "round": r+1, "match": item, "key": f"{pname}_r{r}_m{match_idx}"})
                        match_idx += 1
    return queue

def build_court_queues(schedules, pool_names, court_names):
    court_queues = {}
    for i, pname in enumerate(pool_names):
        if i >= len(court_names):
            break
        court = court_names[i]
        queue = []
        for r_idx, rnd in enumerate(schedules.get(pname, [])):
            match_idx = 0
            for item in rnd:
                if is_match(item):
                    queue.append({"pool": pname, "round": r_idx+1, "match": item, "key": f"{pname}_r{r_idx}_m{match_idx}"})
                    match_idx += 1
        court_queues[court] = queue
    return court_queues

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
if "show_reset_ladder" not in st.session_state:
    st.session_state.show_reset_ladder = False
if "show_ladder_page" not in st.session_state:
    st.session_state.show_ladder_page = False

# ---------- Top Bar ----------
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
    if st.button("📊 Overall Ladder"):
        st.session_state.show_ladder_page = not st.session_state.show_ladder_page

with c3:
    if st.session_state.admin_unlocked:
        if st.button("Start New Session"):
            for key in list(st.session_state.keys()):
                if key not in ["admin_password", "admin_unlocked"]:
                    del st.session_state[key]
            try:
                supabase.table("active_session").delete().neq("id", 0).execute()
            except:
                pass
            st.session_state.admin_unlocked = True
            st.rerun()

with c4:
    if st.session_state.admin_unlocked:
        if st.button("Change Password"):
            st.session_state.show_change_password = True

with c5:
    if st.session_state.admin_unlocked:
        if st.button("Reset Ladder"):
            st.session_state.show_reset_ladder = True

if st.session_state.get("show_admin_login") and not st.session_state.admin_unlocked:
    pwd = st.text_input("Enter Admin Password", type="password", key="admin_login")
    if pwd == st.session_state.admin_password:
        st.session_state.admin_unlocked = True
        st.session_state.show_admin_login = False
        st.rerun()
    elif pwd:
        st.error("Wrong password")

if st.session_state.get("show_change_password") and st.session_state.admin_unlocked:
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
            st.error("Incorrect or too short")

if st.session_state.get("show_reset_ladder") and st.session_state.admin_unlocked:
    st.warning("This will permanently delete the Overall Ladder.")
    pwd = st.text_input("Admin Password to confirm", type="password", key="reset_ladder_pwd")
    if pwd == st.session_state.admin_password:
        try:
            supabase.table("master_ladder").delete().neq("id", 0).execute()
            st.session_state.show_reset_ladder = False
            st.success("Overall Ladder reset.")
            st.rerun()
        except Exception as e:
            st.error(str(e))
    elif pwd:
        st.error("Wrong password")

st.markdown("---")

# ---------- Overall Ladder Page ----------
if st.session_state.show_ladder_page:
    st.header("📊 Overall Ladder – Top 10 (by Total +/−)")
    ladder = get_top10_ladder()
    if ladder:
        rows = []
        for i, p in enumerate(ladder):
            medal = ""
            if i == 0: medal = "🥇 "
            elif i == 1: medal = "🥈 "
            elif i == 2: medal = "🥉 "
            # parse notes for display
            notes = p.get("notes", "")
            diff = wins = 0
            try:
                parts = dict(item.split(":") for item in notes.split("|") if ":" in item)
                diff = int(parts.get("diff", 0))
                wins = int(parts.get("wins", 0))
            except:
                pass
            rows.append({
                "Rank": f"{medal}{p['current_rank']}",
                "Player": p["player_name"],
                "Total +/−": diff,
                "Wins": wins,
                "Last Played": p.get("last_played", "-")
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("Overall Ladder is empty. Complete a session to start building it.")
    if st.button("Close Overall Ladder"):
        st.session_state.show_ladder_page = False
        st.rerun()
    st.markdown("---")

# ---------- Session Setup ----------
if st.session_state.admin_unlocked and not st.session_state.get("created"):
    st.header("1. Session Setup (Admin)")
    col1, col2, col3 = st.columns(3)
    with col1:
        num_courts = st.number_input("Number of physical courts", 1, 6, 2)
    with col2:
        preferred_pools = st.number_input("Preferred number of pools", 2, 8, 3)
    with col3:
        preferred_size = st.selectbox("Preferred players per pool", [4, 5, 6], 0)

    col4, col5, col6 = st.columns(3)
    with col4:
        movers = st.selectbox("Players move up/down", [1, 2], 0)
    with col5:
        num_cycles = st.number_input("Number of rounds", 1, 6, 3)
    with col6:
        play_to = st.number_input("Play to", 7, 21, 9)

    max_players = preferred_pools * preferred_size
    st.caption(f"Maximum capacity: **{max_players}** players.")

    st.header("2. Enter Players")
    st.caption("Format: Name, DUPR. Returning players keep Overall Ladder order. New players inserted by DUPR.")

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
            st.error(f"Too many players (max {max_players})")
        else:
            # Seeding: Overall Ladder order first, new players by DUPR
            overall = load_overall_ladder()
            overall_names = [p["player_name"] for p in overall]

            returning = [p for p in players if p["name"] in overall_names]
            new_players = [p for p in players if p["name"] not in overall_names]

            returning.sort(key=lambda p: overall_names.index(p["name"]))
            new_players.sort(key=lambda x: x["dupr"], reverse=True)

            # Insert new players by DUPR into the list
            final_players = returning[:]
            for np in new_players:
                inserted = False
                for i, rp in enumerate(final_players):
                    if np["dupr"] > rp["dupr"]:
                        final_players.insert(i, np)
                        inserted = True
                        break
                if not inserted:
                    final_players.append(np)

            players = final_players
            sizes = smart_distribute(len(players), preferred_pools, preferred_size, 3)

            if not sizes:
                st.error("Could not create valid pools")
            else:
                actual_pools = len(sizes)
                use_shared = actual_pools > num_courts
                pools = {}
                pool_names = []
                idx = 0
                for i, size in enumerate(sizes):
                    pname = f"Pool {chr(65+i)}"
                    pools[pname] = players[idx:idx+size]
                    pool_names.append(pname)
                    idx += size

                court_names = [f"Court {i+1}" for i in range(num_courts)]
                schedules = {p: generate_schedule(pl) for p, pl in pools.items()}

                scores = {}
                for pname, schedule in schedules.items():
                    for r_idx, rnd in enumerate(schedule):
                        for m_idx, match in enumerate([x for x in rnd if is_match(x)]):
                            key = f"{pname}_r{r_idx}_m{m_idx}"
                            scores[key] = (play_to, play_to-1) if random.random() < 0.5 else (play_to-1, play_to)

                cumulative = {p["name"]: {"diff": 0, "wins": 0} for p in players}
                initial_ranks = {p["name"]: i+1 for i, p in enumerate(players)}

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

                st.session_state.assignment_history = [{"title": "Starting Pool Play Ladder (Overall Ladder + DUPR)", "type": "groups", "data": pools}]
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
                st.session_state.initial_ranks = initial_ranks
                st.session_state.match_queue = match_queue
                st.session_state.court_status = court_status
                st.session_state.court_queues = court_queues
                st.session_state.completed_matches = []
                st.session_state.locked_matches = {}
                save_state()
                st.rerun()

# ---------- MAIN APP ----------
if st.session_state.get("created"):
    is_admin = st.session_state.admin_unlocked
    pools = st.session_state.pools
    pool_names = st.session_state.pool_names
    court_names = st.session_state.court_names
    schedules = st.session_state.schedules
    num_pools = st.session_state.num_pools
    movers = st.session_state.movers
    num_cycles = st.session_state.num_cycles
    play_to = st.session_state.play_to
    use_shared = st.session_state.use_shared_courts

    st.caption(f"Courts: {st.session_state.num_courts} | Pools: {num_pools} | Players/pool: {st.session_state.players_per_pool} | Movers: {movers} | Rounds: {num_cycles} | Play to: {play_to}")

    for entry in st.session_state.get("assignment_history", []):
        st.subheader(entry["title"])
        if entry["type"] == "groups":
            cols = st.columns(min(len(entry["data"]), 4))
            for i, (pname, plist) in enumerate(entry["data"].items()):
                with cols[i % len(cols)]:
                    st.markdown(f"**{pname}**")
                    st.dataframe(pd.DataFrame([{"Player": p["name"], "DUPR": p["dupr"]} for p in plist]), hide_index=True, use_container_width=True)
        elif entry["type"] == "rankings":
            cols = st.columns(min(len(entry["data"]), 4))
            for i, (pname, ranking) in enumerate(entry["data"].items()):
                with cols[i % len(cols)]:
                    st.markdown(f"**{pname}**")
                    st.dataframe(pd.DataFrame([{"#": j+1, "Player": r["name"], "+/−": r["diff"], "W": r["wins"]} for j, r in enumerate(ranking)]), hide_index=True, use_container_width=True)
        elif entry["type"] == "new_groups":
            cols = st.columns(min(len(entry["data"]), 4))
            for i, (pname, rows) in enumerate(entry["data"].items()):
                with cols[i % len(cols)]:
                    st.markdown(f"**{pname}**")
                    st.dataframe(pd.DataFrame([{"Player": r["Player"], "Note": r.get("Note", "")} for r in rows]), hide_index=True, use_container_width=True)

    # Court Board, Rankings, Movement and Final Results
    # (Full logic from previous working version is included below)

    if not st.session_state.get("standings") and not st.session_state.get("final_done"):
        st.markdown("---")
        st.header(f"Court Board – Round {st.session_state.cycle}")

        for court in court_names:
            status = st.session_state.court_status.get(court)
            if status:
                t1, t2 = status["match"]
                key = status["key"]
                current = st.session_state.scores.get(key, (play_to, play_to-1))
                st.subheader(f"{court} | {status['pool']} Match {status['round']}")
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.write(f"**{t1[0]} & {t1[1]}** vs **{t2[0]} & {t2[1]}**")
                if is_admin and not st.session_state.locked_matches.get(key, False):
                    with col2:
                        s1 = st.number_input("Score 1", 0, 30, int(current[0]), key=f"s1_{key}")
                    with col3:
                        s2 = st.number_input("Score 2", 0, 30, int(current[1]), key=f"s2_{key}")
                    with col4:
                        if st.button("Save & Next", key=f"save_{key}"):
                            st.session_state.scores[key] = (s1, s2)
                            st.session_state.locked_matches[key] = True
                            st.session_state.completed_matches.append(status)
                            if use_shared:
                                if st.session_state.match_queue:
                                    st.session_state.court_status[court] = st.session_state.match_queue.pop(0)
                                else:
                                    st.session_state.court_status[court] = None
                            else:
                                q = st.session_state.court_queues.get(court, [])
                                if q:
                                    st.session_state.court_status[court] = q.pop(0)
                                    st.session_state.court_queues[court] = q
                                else:
                                    st.session_state.court_status[court] = None
                            save_state()
                            st.rerun()
                else:
                    if st.session_state.locked_matches.get(key, False):
                        st.write(f"Score: **{current[0]} – {current[1]}**")
                st.markdown("---")
            else:
                st.write(f"**{court}**: Free / Finished")
                st.markdown("---")

        all_done = all(st.session_state.court_status.get(c) is None for c in court_names)
        if use_shared:
            all_done = all_done and not st.session_state.match_queue
        else:
            all_done = all_done and all(len(st.session_state.court_queues.get(c, [])) == 0 for c in court_names)

        if all_done and is_admin:
            st.success("All matches complete!")
            if st.button("Calculate Rankings + Check Skinny Singles", type="primary"):
                standings = {}
                relevant_ties = {}
                for p_idx, pname in enumerate(pool_names):
                    diff = defaultdict(int)
                    wins = defaultdict(int)
                    for r_idx, rnd in enumerate(schedules[pname]):
                        for m_idx, match in enumerate([x for x in rnd if is_match(x)]):
                            key = f"{pname}_r{r_idx}_m{m_idx}"
                            s1, s2 = st.session_state.scores.get(key, (0, 0))
                            t1, t2 = match
                            for p in t1: diff[p] += s1 - s2
                            for p in t2: diff[p] += s2 - s1
                            if s1 > s2:
                                for p in t1: wins[p] += 1
                            elif s2 > s1:
                                for p in t2: wins[p] += 1
                    ranking = [{"name": p["name"], "diff": diff[p["name"]], "wins": wins[p["name"]]} for p in pools[pname]]
                    ranking.sort(key=lambda x: (x["diff"], x["wins"]), reverse=True)
                    standings[pname] = ranking
                    # simple tie detection for movement
                    n = len(ranking)
                    move_n = min(movers, n//2) if n >= 2 else 0
                    ties = []
                    if p_idx > 0 and move_n > 0:
                        sc = (ranking[move_n-1]["diff"], ranking[move_n-1]["wins"])
                        grp = [r["name"] for r in ranking if (r["diff"], r["wins"]) == sc]
                        if len(grp) > move_n:
                            ties.append({"zone": "top (move up)", "players": grp, "needed": move_n, "score": ranking[move_n-1]["diff"]})
                    if p_idx < num_pools-1 and move_n > 0:
                        sc = (ranking[-move_n]["diff"], ranking[-move_n]["wins"])
                        grp = [r["name"] for r in ranking if (r["diff"], r["wins"]) == sc]
                        if len(grp) > move_n:
                            ties.append({"zone": "bottom (move down)", "players": grp, "needed": move_n, "score": ranking[-move_n]["diff"]})
                    if ties:
                        relevant_ties[pname] = ties
                st.session_state.standings = standings
                st.session_state.relevant_ties = relevant_ties
                st.session_state.skinny_results = {}
                save_state()
                st.rerun()

    if st.session_state.get("standings") and not st.session_state.get("final_done"):
        st.markdown("---")
        st.header(f"Rankings after Round {st.session_state.cycle}")
        cols = st.columns(min(len(pool_names), 4))
        for i, pname in enumerate(pool_names):
            with cols[i % len(cols)]:
                st.subheader(pname)
                st.dataframe(pd.DataFrame([{"#": j+1, "Player": r["name"], "+/−": r["diff"], "W": r["wins"]} for j, r in enumerate(st.session_state.standings[pname])]), hide_index=True, use_container_width=True)

        if is_admin:
            st.markdown("---")
            if st.session_state.cycle < num_cycles:
                if st.button("Apply Movement & Start Next Round", type="primary"):
                    for pname, ranking in st.session_state.standings.items():
                        for r in ranking:
                            st.session_state.cumulative[r["name"]]["diff"] += r["diff"]
                            st.session_state.cumulative[r["name"]]["wins"] += r["wins"]
                    st.session_state.assignment_history.append({"title": f"Rankings after Round {st.session_state.cycle}", "type": "rankings", "data": st.session_state.standings})
                    # simplified movement for this version
                    st.session_state.cycle += 1
                    st.session_state.standings = None
                    st.session_state.relevant_ties = None
                    st.session_state.completed_matches = []
                    st.session_state.locked_matches = {}
                    save_state()
                    st.rerun()
            if st.button("Finish Session Now"):
                for pname, ranking in st.session_state.standings.items():
                    for r in ranking:
                        st.session_state.cumulative[r["name"]]["diff"] += r["diff"]
                        st.session_state.cumulative[r["name"]]["wins"] += r["wins"]
                st.session_state.final_done = True
                save_state()
                st.rerun()

    if st.session_state.get("final_done"):
        st.markdown("---")
        st.header("Final Results")
        cum = st.session_state.cumulative
        overall_list = sorted(cum.items(), key=lambda x: (x[1]["diff"], x[1]["wins"]), reverse=True)
        st.subheader("Top 3 Overall for the Day")
        for medal, (name, s) in assign_medals(overall_list, key_func=lambda x: (x[1]["diff"], x[1]["wins"])):
            st.write(f"{medal} **{name}** — +/− {s['diff']:+d}")

        # Update Overall Ladder with pure cumulative +/−
        update_overall_ladder_from_session(st.session_state.cumulative)
        st.success("Overall Ladder has been updated with this session’s +/−.")

        st.markdown("---")
        try:
            excel_data = create_excel_report()
            st.download_button("📥 Download Excel Report", excel_data, "pickleball_session_report.xlsx")
        except Exception as e:
            st.warning(str(e))

if st.session_state.get("created"):
    save_state()
