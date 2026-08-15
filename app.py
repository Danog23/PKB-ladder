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

# ---------- Overall Ladder helpers ----------
def load_overall_ladder():
    try:
        result = supabase.table("master_ladder").select("*").order("current_rank").execute()
        return result.data if result.data else []
    except Exception as e:
        st.warning(f"Could not load Overall Ladder: {e}")
        return []

def parse_notes(notes):
    diff = wins = sessions = 0
    try:
        parts = dict(item.split(":") for item in str(notes).split("|") if ":" in item)
        diff = int(parts.get("diff", 0))
        wins = int(parts.get("wins", 0))
        sessions = int(parts.get("sessions", 0))
    except:
        pass
    return diff, wins, sessions

def save_overall_ladder(players_stats):
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
    try:
        current = load_overall_ladder()
        current_dict = {}
        for row in current:
            diff, wins, sessions = parse_notes(row.get("notes", ""))
            current_dict[row["player_name"]] = {
                "name": row["player_name"],
                "dupr": row.get("dupr", 0),
                "diff": diff,
                "wins": wins,
                "sessions": sessions
            }

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

        sorted_list = sorted(current_dict.values(), key=lambda x: (x["diff"], x["wins"]), reverse=True)
        save_overall_ladder(sorted_list)
        return sorted_list
    except Exception as e:
        st.warning(f"Could not update Overall Ladder: {e}")
        return []

# ---------- Hall of Fame helpers ----------
def load_hof():
    try:
        result = supabase.table("hall_of_fame").select("*").order("championships", desc=True).execute()
        return result.data if result.data else []
    except Exception as e:
        st.warning(f"Could not load Hall of Fame: {e}")
        return []

def add_to_hall_of_fame(player_name):
    try:
        existing = supabase.table("hall_of_fame").select("*").eq("player_name", player_name).execute()
        if existing.data:
            current = existing.data[0].get("championships", 0)
            supabase.table("hall_of_fame").update({
                "championships": current + 1,
                "last_season": str(date.today())
            }).eq("player_name", player_name).execute()
        else:
            supabase.table("hall_of_fame").insert({
                "player_name": player_name,
                "championships": 1,
                "last_season": str(date.today()),
                "notes": "Season Champion"
            }).execute()
    except Exception as e:
        st.error(f"Could not add to Hall of Fame: {e}")

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
        "court_queues", "player_notes"
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
            sit1 = order[r % 6]
            sit2 = order[(r + 3) % 6]
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
if "show_hof_page" not in st.session_state:
    st.session_state.show_hof_page = False
if "show_end_season" not in st.session_state:
    st.session_state.show_end_season = False
if "show_reset_hof" not in st.session_state:
    st.session_state.show_reset_hof = False
if "player_notes" not in st.session_state:
    st.session_state.player_notes = {}

# ---------- Top Bar ----------
c1, c2, c3, c4, c5, c6, c7 = st.columns([1.3, 1.3, 1.3, 1.3, 1.3, 1.3, 1.3])

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
    if st.button("🏆 Hall of Fame"):
        st.session_state.show_hof_page = not st.session_state.show_hof_page

with c4:
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

with c5:
    if st.session_state.admin_unlocked:
        if st.button("Change Password"):
            st.session_state.show_change_password = True

with c6:
    if st.session_state.admin_unlocked:
        if st.button("Reset Ladder"):
            st.session_state.show_reset_ladder = True

with c7:
    if st.session_state.admin_unlocked:
        if st.button("End Season"):
            st.session_state.show_end_season = True

# Dialogs
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

if st.session_state.get("show_end_season") and st.session_state.admin_unlocked:
    st.warning("This will end the current season and add the #1 player to the Hall of Fame.")
    pwd = st.text_input("Admin Password to End Season", type="password", key="end_season_pwd")
    if pwd == st.session_state.admin_password:
        ladder = get_top10_ladder()
        if ladder:
            champion = ladder[0]["player_name"]
            add_to_hall_of_fame(champion)
            st.success(f"Season ended! **{champion}** has been added to the Hall of Fame.")
        else:
            st.info("Overall Ladder is empty.")
        st.session_state.show_end_season = False
        st.rerun()
    elif pwd:
        st.error("Wrong password")

if st.session_state.get("show_reset_hof") and st.session_state.admin_unlocked:
    st.warning("This will permanently delete the Hall of Fame.")
    pwd = st.text_input("Admin Password to Reset Hall of Fame", type="password", key="reset_hof_pwd")
    if pwd == st.session_state.admin_password:
        try:
            supabase.table("hall_of_fame").delete().neq("id", 0).execute()
            st.session_state.show_reset_hof = False
            st.success("Hall of Fame has been reset.")
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
            diff, wins, sessions = parse_notes(p.get("notes", ""))
            rows.append({
                "Rank": f"{medal}{p['current_rank']}",
                "Player": p["player_name"],
                "Total +/−": diff,
                "Wins": wins,
                "Sessions": sessions
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("Overall Ladder is empty.")
    if st.button("Close Overall Ladder"):
        st.session_state.show_ladder_page = False
        st.rerun()
    st.markdown("---")

# ---------- Hall of Fame Page ----------
if st.session_state.show_hof_page:
    st.header("🏆 Hall of Fame")
    hof = load_hof()
    if hof:
        rows = []
        for i, p in enumerate(hof):
            medal = ""
            if i == 0: medal = "🥇 "
            elif i == 1: medal = "🥈 "
            elif i == 2: medal = "🥉 "
            rows.append({
                "Rank": f"{medal}{i+1}",
                "Player": p["player_name"],
                "Championships": p.get("championships", 0),
                "Last Season": p.get("last_season", "-")
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("Hall of Fame is empty.")

    if st.session_state.admin_unlocked:
        st.markdown("---")
        st.subheader("Admin: Edit / Reset Hall of Fame")
        if st.button("Reset Hall of Fame"):
            st.session_state.show_reset_hof = True
            st.rerun()

        # Simple edit
        st.write("Add or update a player manually:")
        edit_name = st.text_input("Player name")
        edit_champs = st.number_input("Championships", min_value=0, value=1)
        if st.button("Save to Hall of Fame"):
            if edit_name.strip():
                try:
                    existing = supabase.table("hall_of_fame").select("*").eq("player_name", edit_name.strip()).execute()
                    if existing.data:
                        supabase.table("hall_of_fame").update({
                            "championships": edit_champs,
                            "last_season": str(date.today())
                        }).eq("player_name", edit_name.strip()).execute()
                    else:
                        supabase.table("hall_of_fame").insert({
                            "player_name": edit_name.strip(),
                            "championships": edit_champs,
                            "last_season": str(date.today()),
                            "notes": "Manual entry"
                        }).execute()
                    st.success("Updated")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    if st.button("Close Hall of Fame"):
        st.session_state.show_hof_page = False
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
            overall = load_overall_ladder()
            overall_names = [p["player_name"] for p in overall]
            overall_rank = {p["player_name"]: p["current_rank"] for p in overall}

            returning = [p for p in players if p["name"] in overall_names]
            new_players = [p for p in players if p["name"] not in overall_names]

            returning.sort(key=lambda p: overall_names.index(p["name"]))
            new_players.sort(key=lambda x: x["dupr"], reverse=True)

            final_players = returning[:]
            player_notes = {}

            for p in returning:
                player_notes[p["name"]] = f"Overall Ladder #{overall_rank.get(p['name'], '?')}"

            for np in new_players:
                inserted = False
                for i, rp in enumerate(final_players):
                    if np["dupr"] > rp["dupr"]:
                        final_players.insert(i, np)
                        inserted = True
                        break
                if not inserted:
                    final_players.append(np)
                player_notes[np["name"]] = f"New Player (DUPR {np['dupr']})"

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
                    pname = f"Pool {chr(65 + i)}"
                    pools[pname] = players[idx:idx + size]
                    pool_names.append(pname)
                    idx += size

                court_names = [f"Court {i+1}" for i in range(num_courts)]
                schedules = {p: generate_schedule(pl) for p, pl in pools.items()}

                scores = {}
                for pname, schedule in schedules.items():
                    for r_idx, rnd in enumerate(schedule):
                        for m_idx, match in enumerate([x for x in rnd if is_match(x)]):
                            key = f"{pname}_r{r_idx}_m{m_idx}"
                            scores[key] = (play_to, play_to - 1) if random.random() < 0.5 else (play_to - 1, play_to)

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
                st.session_state.player_notes = player_notes
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
    player_notes = st.session_state.get("player_notes", {})

    st.caption(f"Courts: {st.session_state.num_courts} | Pools: {num_pools} | Players/pool: {st.session_state.players_per_pool} | Movers: {movers} | Rounds: {num_cycles} | Play to: {play_to}")

    for entry in st.session_state.get("assignment_history", []):
        st.subheader(entry["title"])
        if entry["type"] == "groups":
            cols = st.columns(min(len(entry["data"]), 4))
            for i, (pname, plist) in enumerate(entry["data"].items()):
                with cols[i % len(cols)]:
                    st.markdown(f"**{pname}**")
                    data = []
                    for p in plist:
                        note = player_notes.get(p["name"], "")
                        data.append({"Player": p["name"], "DUPR": p["dupr"], "Note": note})
                    st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)
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

    # ---------- COURT BOARD ----------
    if not st.session_state.get("standings") and not st.session_state.get("final_done"):
        st.markdown("---")
        st.header(f"Court Board – Round {st.session_state.cycle}")

        for court in court_names:
            status = st.session_state.court_status.get(court)
            if status:
                t1, t2 = status["match"]
                key = status["key"]
                current = st.session_state.scores.get(key, (play_to, play_to - 1))

                st.subheader(f"{court} | {status['pool']} Match {status['round']}")
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

                with col1:
                    st.write(f"**{t1[0]} & {t1[1]}** vs **{t2[0]} & {t2[1]}**")

                if is_admin and not st.session_state.locked_matches.get(key, False):
                    with col2:
                        s1 = st.number_input("Score 1", min_value=0, max_value=30, value=int(current[0]), key=f"s1_{key}")
                    with col3:
                        s2 = st.number_input("Score 2", min_value=0, max_value=30, value=int(current[1]), key=f"s2_{key}")
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
            st.success("All matches in this round are complete!")
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
                            for p in t1:
                                diff[p] += s1 - s2
                            for p in t2:
                                diff[p] += s2 - s1
                            if s1 > s2:
                                for p in t1:
                                    wins[p] += 1
                            elif s2 > s1:
                                for p in t2:
                                    wins[p] += 1

                    ranking = [{"name": p["name"], "diff": diff[p["name"]], "wins": wins[p["name"]]} for p in pools[pname]]
                    ranking.sort(key=lambda x: (x["diff"], x["wins"]), reverse=True)
                    standings[pname] = ranking

                    n = len(ranking)
                    move_n = min(movers, n // 2) if n >= 2 else 0
                    ties = []
                    if p_idx > 0 and move_n > 0:
                        sc = (ranking[move_n - 1]["diff"], ranking[move_n - 1]["wins"])
                        grp = [r["name"] for r in ranking if (r["diff"], r["wins"]) == sc]
                        if len(grp) > move_n:
                            ties.append({"zone": "top (move up)", "players": grp, "needed": move_n, "score": ranking[move_n - 1]["diff"]})
                    if p_idx < num_pools - 1 and move_n > 0:
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

    # ---------- RANKINGS + MOVEMENT ----------
    if st.session_state.get("standings") and not st.session_state.get("final_done"):
        st.markdown("---")
        st.header(f"Rankings after Round {st.session_state.cycle}")

        cols = st.columns(min(len(pool_names), 4))
        for i, pname in enumerate(pool_names):
            with cols[i % len(cols)]:
                st.subheader(pname)
                st.dataframe(pd.DataFrame([{"#": j+1, "Player": r["name"], "+/−": r["diff"], "W": r["wins"]} for j, r in enumerate(st.session_state.standings[pname])]), hide_index=True, use_container_width=True)

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
                            incoming_down = movers_down.get(pool_names[p_idx - 1], []) if p_idx > 0 else []
                            incoming_up = movers_up.get(pool_names[p_idx + 1], []) if p_idx < num_pools - 1 else []

                            ordered = []
                            for r in incoming_down:
                                ordered.append({"Player": r["name"], "Note": f"(down from {pool_names[p_idx - 1]})"})
                                for pl in pools[pool_names[p_idx - 1]]:
                                    if pl["name"] == r["name"]:
                                        new_pools[pname].append(pl)
                                        break
                            for r in staying:
                                ordered.append({"Player": r["name"], "Note": ""})
                                for pl in pools[pname]:
                                    if pl["name"] == r["name"]:
                                        new_pools[pname].append(pl)
                                        break
                            for r in incoming_up:
                                ordered.append({"Player": r["name"], "Note": f"(up from {pool_names[p_idx + 1]})"})
                                for pl in pools[pool_names[p_idx + 1]]:
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
                                for m_idx, match in enumerate([x for x in rnd if is_match(x)]):
                                    key = f"{pname}_r{r_idx}_m{m_idx}"
                                    new_scores[key] = (play_to, play_to - 1) if random.random() < 0.5 else (play_to - 1, play_to)

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
                    for pname, ranking in st.session_state.standings.items():
                        for r in ranking:
                            st.session_state.cumulative[r["name"]]["diff"] += r["diff"]
                            st.session_state.cumulative[r["name"]]["wins"] += r["wins"]
                    st.session_state.final_done = True
                    update_overall_ladder_from_session(st.session_state.cumulative)
                    save_state()
                    st.rerun()

    # ---------- FINAL RESULTS ----------
    if st.session_state.get("final_done"):
        st.markdown("---")
        st.header("Final Results")

        cum = st.session_state.cumulative
        overall_list = sorted(cum.items(), key=lambda x: (x[1]["diff"], x[1]["wins"]), reverse=True)

        st.subheader("Top 3 Overall for the Day (Total +/−)")
        for medal, (name, s) in assign_medals(overall_list, key_func=lambda x: (x[1]["diff"], x[1]["wins"])):
            st.write(f"{medal} **{name}** — +/− {s['diff']:+d}  (Wins: {s['wins']})")

        st.subheader("Top 3 from Final Top Pool")
        if st.session_state.standings and pool_names:
            top_pool = st.session_state.standings.get(pool_names[0], [])
            for medal, r in assign_medals(top_pool, key_func=lambda x: (x["diff"], x["wins"])):
                st.write(f"{medal} **{r['name']}** — +/− {r['diff']:+d}")

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
            st.write(f"{medal} **{c['name']}** — Climbed **{c['climbed']:+d}** positions (#{c['start']} → #{c['final']})")

        st.success("Session complete! Overall Ladder has been updated.")

        st.markdown("---")
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                pd.DataFrame({
                    "Player": list(cum.keys()),
                    "+/−": [v["diff"] for v in cum.values()],
                    "Wins": [v["wins"] for v in cum.values()]
                }).to_excel(writer, index=False)
            st.download_button("📥 Download Excel Report", output.getvalue(), "pickleball_session_report.xlsx")
        except Exception as e:
            st.warning(str(e))

if st.session_state.get("created"):
    save_state()
