import streamlit as st
import pandas as pd
from collections import defaultdict
import random
from io import BytesIO
from supabase import create_client, Client
from datetime import date
from calendar import month_abbr

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase()

st.set_page_config(page_title="Pickleball Pool Ladder", layout="wide")
st.title("Pickleball Multi-Court Ladder")
st.info("**Note:** If you don’t see the latest scores or rankings, please **refresh the page** or **open the link again**.")

# ---------- Helpers ----------
def month_range_str(start_date_str=None):
    try:
        if start_date_str:
            start = date.fromisoformat(start_date_str)
        else:
            start = date.today().replace(day=1)
        end = date.today()
        if start.year == end.year:
            if start.month == end.month:
                return f"{month_abbr[start.month]} {start.year}"
            return f"{month_abbr[start.month]}–{month_abbr[end.month]} {start.year}"
        return f"{month_abbr[start.month]} {start.year}–{month_abbr[end.month]} {end.year}"
    except:
        return f"{month_abbr[date.today().month]} {date.today().year}"

def clean_season(s):
    if not s:
        return month_range_str()
    s = str(s).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            d = date.fromisoformat(s)
            return f"{month_abbr[d.month]} {d.year}"
        except:
            pass
    return s

def load_overall_ladder():
    try:
        result = supabase.table("master_ladder").select("*").order("current_rank").execute()
        return result.data if result.data else []
    except Exception as e:
        st.warning(f"Could not load Overall Ladder: {e}")
        return []

def load_last_season_ladder():
    try:
        result = supabase.table("last_season_ladder").select("*").order("current_rank").execute()
        return result.data if result.data else []
    except Exception as e:
        st.warning(f"Could not load Last Season Ladder: {e}")
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

def archive_and_clear_ladder():
    try:
        current = load_overall_ladder()
        supabase.table("last_season_ladder").delete().neq("id", 0).execute()
        if current:
            rows = []
            for p in current:
                rows.append({
                    "player_name": p["player_name"],
                    "dupr": p.get("dupr", 0),
                    "current_rank": p["current_rank"],
                    "last_played": p.get("last_played", str(date.today())),
                    "notes": p.get("notes", "")
                })
            supabase.table("last_season_ladder").insert(rows).execute()
        supabase.table("master_ladder").delete().neq("id", 0).execute()
        return True
    except Exception as e:
        st.error(f"Could not archive ladder: {e}")
        return False

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

def load_hof():
    try:
        result = supabase.table("hall_of_fame").select("*").execute()
        data = result.data if result.data else []
        # Sort: championships desc, then total_diff desc
        def sort_key(row):
            champs = row.get("championships", 0)
            notes = row.get("notes", "")
            diff = 0
            try:
                for part in notes.split("|"):
                    if part.startswith("diff:"):
                        diff = int(part.split(":")[1])
            except:
                pass
            return (-champs, -diff)
        data.sort(key=sort_key)
        return data
    except Exception as e:
        st.warning(f"Could not load Hall of Fame: {e}")
        return []

def add_to_hall_of_fame(player_name, season_str, total_diff=0):
    season_str = clean_season(season_str)
    try:
        existing = supabase.table("hall_of_fame").select("*").eq("player_name", player_name).execute()
        if existing.data:
            row = existing.data[0]
            current = row.get("championships", 0)
            old_seasons = row.get("last_season", "") or ""
            seasons = [s.strip() for s in old_seasons.split(",") if s.strip()]
            if season_str not in seasons:
                seasons.append(season_str)
            new_seasons = ", ".join(seasons)
            # Keep the highest total_diff we have
            old_diff = 0
            try:
                for part in (row.get("notes") or "").split("|"):
                    if part.startswith("diff:"):
                        old_diff = int(part.split(":")[1])
            except:
                pass
            final_diff = max(old_diff, total_diff)
            supabase.table("hall_of_fame").update({
                "championships": current + 1,
                "last_season": new_seasons,
                "notes": f"diff:{final_diff}"
            }).eq("player_name", player_name).execute()
        else:
            supabase.table("hall_of_fame").insert({
                "player_name": player_name,
                "championships": 1,
                "last_season": season_str,
                "notes": f"diff:{total_diff}"
            }).execute()
        return True
    except Exception as e:
        st.error(f"Could not add to Hall of Fame: {e}")
        return False

def save_state():
    if not st.session_state.get("created"):
        return
    data = {k: st.session_state.get(k) for k in [
        "players", "pools", "pool_names", "court_names", "schedules", "scores",
        "num_courts", "num_pools", "players_per_pool", "pool_movers",
        "cycle", "standings", "relevant_ties", "skinny_results",
        "cumulative", "assignment_history", "final_done", "admin_password", "edit_password",
        "play_to", "full_score_history", "locked_matches", "initial_ranks",
        "use_shared_courts", "match_queue", "court_status", "completed_matches",
        "court_queues", "player_notes", "season_start", "last_players_text"
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

def smart_distribute(n_players, preferred_pools, preferred_size):
    if n_players < 3:
        return []
    best = None
    for num_pools in range(max(1, preferred_pools - 1), preferred_pools + 3):
        if num_pools * 3 > n_players or num_pools * 6 < n_players:
            continue
        base = n_players // num_pools
        rem = n_players % num_pools
        sizes = [base] * num_pools
        for i in range(rem):
            sizes[-(i + 1)] += 1
        if all(3 <= s <= 6 for s in sizes):
            has_six = any(s == 6 for s in sizes)
            score = (has_six, abs(num_pools - preferred_pools), abs(base - preferred_size))
            if best is None or score < best[0]:
                best = (score, sizes)
    return best[1] if best else []

def default_movers_for_size(size):
    if size <= 4:
        return 1
    if size == 5:
        return 2
    return 3

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

def build_interleaved_queue(schedules, pool_names, pools):
    sorted_pools = sorted(pool_names, key=lambda p: len(pools.get(p, [])), reverse=True)
    queue = []
    max_rounds = max((len(schedules.get(p, [])) for p in pool_names), default=0)
    for r in range(max_rounds):
        for pname in sorted_pools:
            sched = schedules.get(pname, [])
            if r < len(sched):
                match_idx = 0
                for item in sched[r]:
                    if is_match(item):
                        queue.append({"pool": pname, "round": r+1, "match": item, "key": f"{pname}_r{r}_m{match_idx}"})
                        match_idx += 1
    return queue

def build_court_queues(schedules, pool_names, court_names, pools):
    sorted_pools = sorted(pool_names, key=lambda p: len(pools.get(p, [])), reverse=True)
    court_queues = {}
    for i, pname in enumerate(sorted_pools):
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

def centered_title(text):
    st.markdown(f"<h3 style='text-align: center;'>{text}</h3>", unsafe_allow_html=True)

def get_upcoming_matches():
    upcoming = []
    for court, status in st.session_state.get("court_status", {}).items():
        if status:
            t1, t2 = status["match"]
            upcoming.append({
                "Status": f"▶ {court}",
                "Pool": status["pool"],
                "Match": f"{t1[0]} & {t1[1]} vs {t2[0]} & {t2[1]}"
            })
    if st.session_state.get("use_shared_courts"):
        for item in st.session_state.get("match_queue", [])[:12]:
            t1, t2 = item["match"]
            upcoming.append({
                "Status": "Up next",
                "Pool": item["pool"],
                "Match": f"{t1[0]} & {t1[1]} vs {t2[0]} & {t2[1]}"
            })
    else:
        for court, q in st.session_state.get("court_queues", {}).items():
            for item in q[:4]:
                t1, t2 = item["match"]
                upcoming.append({
                    "Status": f"Up next ({court})",
                    "Pool": item["pool"],
                    "Match": f"{t1[0]} & {t1[1]} vs {t2[0]} & {t2[1]}"
                })
    return upcoming

# ---------- Initialize ----------
if "admin_unlocked" not in st.session_state:
    st.session_state.admin_unlocked = False
if "admin_password" not in st.session_state:
    st.session_state.admin_password = "2302"
if "edit_password" not in st.session_state:
    st.session_state.edit_password = "1234"
if "created" not in st.session_state:
    load_state()
if "full_score_history" not in st.session_state:
    st.session_state.full_score_history = []
if "locked_matches" not in st.session_state:
    st.session_state.locked_matches = {}
if "initial_ranks" not in st.session_state:
    st.session_state.initial_ranks = {}
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
if "show_last_season" not in st.session_state:
    st.session_state.show_last_season = False
if "player_notes" not in st.session_state:
    st.session_state.player_notes = {}
if "pool_movers" not in st.session_state:
    st.session_state.pool_movers = {}
if "show_score_history" not in st.session_state:
    st.session_state.show_score_history = False
if "season_start" not in st.session_state:
    st.session_state.season_start = str(date.today())
if "last_players_text" not in st.session_state:
    st.session_state.last_players_text = ""
if "show_change_admin_pwd" not in st.session_state:
    st.session_state.show_change_admin_pwd = False
if "show_change_edit_pwd" not in st.session_state:
    st.session_state.show_change_edit_pwd = False

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
                if key not in ["admin_password", "edit_password", "admin_unlocked", "last_players_text", "season_start"]:
                    del st.session_state[key]
            try:
                supabase.table("active_session").delete().neq("id", 0).execute()
            except:
                pass
            st.session_state.admin_unlocked = True
            st.rerun()

with c5:
    if st.session_state.admin_unlocked:
        if st.button("Change Admin Pwd"):
            st.session_state.show_change_admin_pwd = True

with c6:
    if st.session_state.admin_unlocked:
        if st.button("Change Edit Pwd"):
            st.session_state.show_change_edit_pwd = True

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

if st.session_state.get("show_change_admin_pwd") and st.session_state.admin_unlocked:
    st.subheader("Change Admin Password")
    old = st.text_input("Current Admin Password", type="password", key="old_admin")
    new = st.text_input("New Admin Password", type="password", key="new_admin")
    if st.button("Update Admin Password"):
        if old == st.session_state.admin_password and new and len(new) >= 4:
            st.session_state.admin_password = new
            st.session_state.show_change_admin_pwd = False
            save_state()
            st.success("Admin password updated")
            st.rerun()
        else:
            st.error("Incorrect or too short")

if st.session_state.get("show_change_edit_pwd") and st.session_state.admin_unlocked:
    st.subheader("Change Edit Password")
    old = st.text_input("Current Admin Password (required)", type="password", key="old_for_edit")
    new = st.text_input("New Edit Password", type="password", key="new_edit")
    if st.button("Update Edit Password"):
        if old == st.session_state.admin_password and new and len(new) >= 3:
            st.session_state.edit_password = new
            st.session_state.show_change_edit_pwd = False
            save_state()
            st.success("Edit password updated")
            st.rerun()
        else:
            st.error("Incorrect admin password or too short")

if st.session_state.get("show_end_season") and st.session_state.admin_unlocked:
    st.warning("This will archive the current Overall Ladder as Last Season, clear it, and add the #1 player to the Hall of Fame.")
    pwd = st.text_input("Admin Password to End Season", type="password", key="end_season_pwd")
    if pwd == st.session_state.admin_password:
        ladder = get_top10_ladder()
        season_str = month_range_str(st.session_state.get("season_start"))
        if ladder:
            champion = ladder[0]["player_name"]
            # Get total +/- from notes
            total_diff = 0
            try:
                for part in (ladder[0].get("notes") or "").split("|"):
                    if part.startswith("diff:"):
                        total_diff = int(part.split(":")[1])
            except:
                pass
            add_to_hall_of_fame(champion, season_str, total_diff)
            success = archive_and_clear_ladder()
            if success:
                st.session_state.season_start = str(date.today())
                st.success(f"✅ Season ended!\n\n**{champion}** added to Hall of Fame.\nOverall Ladder has been archived and cleared.")
            else:
                st.error("Failed to archive ladder.")
        else:
            archive_and_clear_ladder()
            st.session_state.season_start = str(date.today())
            st.info("Overall Ladder was empty. New season started.")
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
    season = month_range_str(st.session_state.get("season_start"))
    st.header(f"📊 Overall Ladder – Top 10 ({season})")
    ladder = get_top10_ladder()
    if ladder:
        rows = []
        for i, p in enumerate(ladder):
            medal = "🥇 " if i == 0 else "🥈 " if i == 1 else "🥉 " if i == 2 else ""
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
    
    if st.button("View Last Season Overall Ladder"):
        st.session_state.show_last_season = True
        st.rerun()
    
    if st.button("Close Overall Ladder"):
        st.session_state.show_ladder_page = False
        st.rerun()
    st.markdown("---")

if st.session_state.get("show_last_season"):
    st.header("📊 Last Season Overall Ladder")
    last = load_last_season_ladder()
    if last:
        rows = []
        for i, p in enumerate(last):
            medal = "🥇 " if i == 0 else "🥈 " if i == 1 else "🥉 " if i == 2 else ""
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
        st.info("No last season data found.")
    if st.button("Close Last Season"):
        st.session_state.show_last_season = False
        st.rerun()
    st.markdown("---")

# ---------- Hall of Fame Page ----------
if st.session_state.show_hof_page:
    st.header("🏆 Hall of Fame")
    hof = load_hof()
    if hof:
        rows = []
        for i, p in enumerate(hof):
            medal = "🥇 " if i == 0 else "🥈 " if i == 1 else "🥉 " if i == 2 else ""
            seasons = clean_season(p.get("last_season", "-"))
            total_diff = 0
            try:
                for part in (p.get("notes") or "").split("|"):
                    if part.startswith("diff:"):
                        total_diff = int(part.split(":")[1])
            except:
                pass
            rows.append({
                "Rank": f"{medal}{i+1}",
                "Player": p["player_name"],
                "Championships": p.get("championships", 0),
                "Total +/−": total_diff,
                "Season": seasons
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("Hall of Fame is empty. Only season winners appear here.")

    if st.session_state.admin_unlocked:
        st.markdown("---")
        st.subheader("Admin Controls")
        if st.button("Reset Hall of Fame"):
            st.session_state.show_reset_hof = True
            st.rerun()
        
        hof_names = [p["player_name"] for p in hof] if hof else []
        if hof_names:
            selected = st.selectbox("Select player to edit", [""] + hof_names)
            if selected:
                edit_champs = st.number_input("Championships", min_value=0, value=1)
                if st.button("Update Championships"):
                    try:
                        supabase.table("hall_of_fame").update({
                            "championships": edit_champs
                        }).eq("player_name", selected).execute()
                        st.success("Updated")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        else:
            st.caption("No players in Hall of Fame to edit.")

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
        num_pools = st.number_input("Number of pools", 2, 8, 3)
    with col3:
        players_per_pool = st.selectbox("Players per pool", [4, 5, 6], 0)

    play_to = st.number_input("Play to", 7, 21, 9)
    st.caption("Movers defaults: 4-player → 1, 5-player → 2, 6-player → 3 (can be changed after pools are created)")

    st.header("2. Enter Players")
    st.caption("Format: Name, DUPR. Players from last session are pre-filled when available.")

    default_text = st.session_state.get("last_players_text") or """Alex, 5.3
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

    player_text = st.text_area("Players (Name, DUPR)", height=280, value=default_text)

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
        else:
            st.session_state.last_players_text = player_text.strip()

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
            sizes = smart_distribute(len(players), num_pools, players_per_pool)

            if not sizes:
                st.error("Could not create valid pools.")
            else:
                actual_pools = len(sizes)
                use_shared = actual_pools > num_courts
                pools = {}
                pool_names = []
                pool_movers = {}
                idx = 0
                for i, size in enumerate(sizes):
                    pname = f"Pool {chr(65 + i)}"
                    pools[pname] = players[idx:idx + size]
                    pool_names.append(pname)
                    pool_movers[pname] = default_movers_for_size(size)
                    idx += size

                size_str = " + ".join(str(s) for s in sizes)
                st.success(f"Created pools: **{size_str}**")

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
                    match_queue = build_interleaved_queue(schedules, pool_names, pools)
                    for i, court in enumerate(court_names):
                        if i < len(match_queue):
                            court_status[court] = match_queue[i]
                    match_queue = match_queue[len(court_names):]
                else:
                    court_queues = build_court_queues(schedules, pool_names, court_names, pools)
                    for court, q in court_queues.items():
                        if q:
                            court_status[court] = q[0]
                            court_queues[court] = q[1:]

                if not st.session_state.get("season_start"):
                    st.session_state.season_start = str(date.today())

                st.session_state.assignment_history = [{"title": "Starting Pool Play Ladder (Overall Ladder + DUPR)", "type": "groups", "data": pools}]
                st.session_state.players = players
                st.session_state.pools = pools
                st.session_state.pool_names = pool_names
                st.session_state.court_names = court_names
                st.session_state.schedules = schedules
                st.session_state.scores = scores
                st.session_state.num_courts = num_courts
                st.session_state.num_pools = actual_pools
                st.session_state.players_per_pool = players_per_pool
                st.session_state.pool_movers = pool_movers
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
                st.session_state.full_score_history = []
                st.session_state.final_done = False
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
    pool_movers = st.session_state.get("pool_movers", {})
    play_to = st.session_state.play_to
    use_shared = st.session_state.use_shared_courts
    player_notes = st.session_state.get("player_notes", {})

    st.caption(f"Courts: {st.session_state.num_courts} | Pools: {num_pools} | Play to: {play_to} | Season: {month_range_str(st.session_state.get('season_start'))}")

    # Score History with direct edit
    if st.button("📜 Show / Hide Score History"):
        st.session_state.show_score_history = not st.session_state.show_score_history

    if st.session_state.show_score_history:
        st.subheader("Full Score History")
        if st.session_state.full_score_history:
            for e_idx, entry in enumerate(st.session_state.full_score_history):
                st.markdown(f"**{entry['title']}**")
                for idx, line in enumerate(entry.get("lines", [])):
                    # Try to find the key from the line
                    key = None
                    for k, v in st.session_state.scores.items():
                        # rough match
                        if line.split("→")[0].strip() in str(k) or True:
                            # better: we store key in history now
                            pass
                    # We will store key in the history entry going forward
                    stored_key = entry.get("keys", [None]*len(entry.get("lines", [])))[idx] if "keys" in entry else None

                    cols = st.columns([5, 1, 1, 1])
                    with cols[0]:
                        st.write(line)
                    if is_admin and stored_key:
                        with cols[1]:
                            s1 = st.number_input("S1", 0, 30, st.session_state.scores.get(stored_key, (0,0))[0], key=f"hs1_{e_idx}_{idx}")
                        with cols[2]:
                            s2 = st.number_input("S2", 0, 30, st.session_state.scores.get(stored_key, (0,0))[1], key=f"hs2_{e_idx}_{idx}")
                        with cols[3]:
                            if st.button("Save", key=f"hsave_{e_idx}_{idx}"):
                                pwd = st.session_state.get(f"hpwd_{e_idx}_{idx}", "")
                                if not pwd:
                                    st.session_state[f"need_pwd_{e_idx}_{idx}"] = True
                                if st.session_state.get(f"need_pwd_{e_idx}_{idx}"):
                                    pwd_input = st.text_input("Edit Password", type="password", key=f"hpwd_input_{e_idx}_{idx}")
                                    if pwd_input == st.session_state.edit_password:
                                        st.session_state.scores[stored_key] = (s1, s2)
                                        # Update the display line
                                        parts = line.split("→")
                                        new_line = parts[0] + f"→ {s1}-{s2}"
                                        st.session_state.full_score_history[e_idx]["lines"][idx] = new_line
                                        save_state()
                                        st.success("Score updated")
                                        st.rerun()
                                    elif pwd_input:
                                        st.error("Wrong Edit Password")
                    elif is_admin:
                        st.caption("(older entry – key missing)")
        else:
            st.caption("No scores recorded yet.")

    for entry in st.session_state.get("assignment_history", []):
        centered_title(entry["title"])
        if entry["type"] == "groups":
            cols = st.columns(min(len(entry["data"]), 4))
            for i, (pname, plist) in enumerate(entry["data"].items()):
                with cols[i % len(cols)]:
                    st.markdown(f"<h4 style='text-align:center'>{pname} ({len(plist)})</h4>", unsafe_allow_html=True)
                    if is_admin:
                        current_m = pool_movers.get(pname, 1)
                        new_m = st.selectbox(f"Movers {pname}", [1, 2, 3], index=min(current_m-1, 2), key=f"movers_{pname}")
                        if new_m != current_m:
                            st.session_state.pool_movers[pname] = new_m
                            save_state()
                    data = [{"Player": p["name"], "DUPR": p["dupr"], "Note": player_notes.get(p["name"], "")} for p in plist]
                    st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)
        elif entry["type"] == "rankings":
            cols = st.columns(min(len(entry["data"]), 4))
            for i, (pname, ranking) in enumerate(entry["data"].items()):
                with cols[i % len(cols)]:
                    st.markdown(f"<h4 style='text-align:center'>{pname}</h4>", unsafe_allow_html=True)
                    st.dataframe(pd.DataFrame([{"#": j+1, "Player": r["name"], "+/−": r["diff"], "W": r["wins"]} for j, r in enumerate(ranking)]), hide_index=True, use_container_width=True)
        elif entry["type"] == "new_groups":
            cols = st.columns(min(len(entry["data"]), 4))
            for i, (pname, rows) in enumerate(entry["data"].items()):
                with cols[i % len(cols)]:
                    st.markdown(f"<h4 style='text-align:center'>{pname}</h4>", unsafe_allow_html=True)
                    st.dataframe(pd.DataFrame([{"Player": r["Player"], "Note": r.get("Note", "")} for r in rows]), hide_index=True, use_container_width=True)

    # Upcoming Schedule
    if not st.session_state.get("final_done"):
        upcoming = get_upcoming_matches()
        if upcoming:
            st.markdown("---")
            centered_title("Upcoming Match Schedule")
            st.dataframe(pd.DataFrame(upcoming), hide_index=True, use_container_width=True)

    # COURT BOARD
    if not st.session_state.get("standings") and not st.session_state.get("final_done"):
        st.markdown("---")
        centered_title(f"Court Board – Round {st.session_state.cycle}")

        for court in court_names:
            status = st.session_state.court_status.get(court)
            if status:
                t1, t2 = status["match"]
                key = status["key"]
                current = st.session_state.scores.get(key, (play_to, play_to - 1))

                st.subheader(f"{court} | {status['pool']} Match {status['round']}")
                col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
                with col1:
                    st.write(f"**{t1[0]} & {t1[1]}** vs **{t2[0]} & {t2[1]}**")

                if is_admin:
                    locked = st.session_state.locked_matches.get(key, False)
                    if locked:
                        st.write(f"Score: **{current[0]} – {current[1]}**")
                        if st.button("🔓 Unlock to Edit", key=f"unlock_{key}"):
                            pwd = st.text_input("Edit Password", type="password", key=f"pwd_unlock_{key}")
                            if pwd == st.session_state.edit_password:
                                st.session_state.locked_matches[key] = False
                                save_state()
                                st.rerun()
                            elif pwd:
                                st.error("Wrong Edit Password")
                    else:
                        with col2:
                            s1 = st.number_input("Score 1", 0, 30, int(current[0]), key=f"s1_{key}")
                        with col3:
                            s2 = st.number_input("Score 2", 0, 30, int(current[1]), key=f"s2_{key}")
                        with col4:
                            if st.button("Save & Next", key=f"save_{key}"):
                                st.session_state.scores[key] = (s1, s2)
                                st.session_state.locked_matches[key] = True
                                st.session_state.completed_matches.append(status)

                                line = f"{status['pool']} Match {status['round']}: {t1[0]} & {t1[1]} vs {t2[0]} & {t2[1]} → {s1}-{s2}"
                                if not st.session_state.full_score_history or st.session_state.full_score_history[-1]["title"] != f"Round {st.session_state.cycle} Scores":
                                    st.session_state.full_score_history.append({"title": f"Round {st.session_state.cycle} Scores", "lines": [], "keys": []})
                                st.session_state.full_score_history[-1]["lines"].append(line)
                                st.session_state.full_score_history[-1]["keys"].append(key)

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
                        with col5:
                            if st.button("Skip →", key=f"skip_{key}"):
                                if use_shared:
                                    if st.session_state.match_queue:
                                        skipped = status
                                        st.session_state.court_status[court] = st.session_state.match_queue.pop(0)
                                        st.session_state.match_queue.append(skipped)
                                    else:
                                        st.session_state.court_status[court] = None
                                else:
                                    q = st.session_state.court_queues.get(court, [])
                                    if q:
                                        skipped = status
                                        st.session_state.court_status[court] = q.pop(0)
                                        q.append(skipped)
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
                            for p in t1: diff[p] += s1 - s2
                            for p in t2: diff[p] += s2 - s1
                            if s1 > s2:
                                for p in t1: wins[p] += 1
                            elif s2 > s1:
                                for p in t2: wins[p] += 1
                    ranking = [{"name": p["name"], "diff": diff[p["name"]], "wins": wins[p["name"]]} for p in pools[pname]]
                    ranking.sort(key=lambda x: (x["diff"], x["wins"]), reverse=True)
                    standings[pname] = ranking

                    move_n = pool_movers.get(pname, 1)
                    n = len(ranking)
                    move_n = min(move_n, n // 2) if n >= 2 else 0
                    ties = []

                    if p_idx > 0 and move_n > 0:
                        cut_diff = ranking[move_n - 1]["diff"]
                        cut_wins = ranking[move_n - 1]["wins"]
                        grp = [r["name"] for r in ranking if r["diff"] == cut_diff and r["wins"] == cut_wins]
                        if len(grp) > move_n:
                            ties.append({"zone": "top (move up)", "players": grp, "needed": move_n, "score": cut_diff})

                    if p_idx < num_pools - 1 and move_n > 0:
                        cut_diff = ranking[-move_n]["diff"]
                        cut_wins = ranking[-move_n]["wins"]
                        grp = [r["name"] for r in ranking if r["diff"] == cut_diff and r["wins"] == cut_wins]
                        if len(grp) > move_n:
                            ties.append({"zone": "bottom (move down)", "players": grp, "needed": move_n, "score": cut_diff})

                    if ties:
                        relevant_ties[pname] = ties

                st.session_state.standings = standings
                st.session_state.relevant_ties = relevant_ties
                st.session_state.skinny_results = {}
                save_state()
                st.rerun()

    # RANKINGS + MOVEMENT
    if st.session_state.get("standings") and not st.session_state.get("final_done"):
        st.markdown("---")
        centered_title(f"Rankings after Round {st.session_state.cycle}")

        if is_admin:
            if st.button("✏️ Edit This Round (re-enter scores)"):
                pwd = st.text_input("Edit Password to re-open round", type="password", key="edit_round_pwd")
                if pwd == st.session_state.edit_password:
                    st.session_state.standings = None
                    st.session_state.relevant_ties = None
                    st.session_state.skinny_results = {}
                    for k in list(st.session_state.locked_matches.keys()):
                        st.session_state.locked_matches[k] = False
                    save_state()
                    st.success("Round re-opened. You can now edit scores.")
                    st.rerun()
                elif pwd:
                    st.error("Wrong Edit Password")

        cols = st.columns(min(len(pool_names), 4))
        for i, pname in enumerate(pool_names):
            with cols[i % len(cols)]:
                st.markdown(f"<h4 style='text-align:center'>{pname}</h4>", unsafe_allow_html=True)
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
                    st.write(f"Select exactly **{tie['needed']}** player(s):")
                    cbs = st.columns(min(len(tie["players"]), 4))
                    for i, p in enumerate(tie["players"]):
                        with cbs[i % len(cbs)]:
                            if st.checkbox(p, key=f"sk_{key}_{p}"):
                                selected.append(p)
                    current_selections[key] = selected
                    if len(selected) == tie["needed"]:
                        st.session_state.skinny_results[key] = selected
                        st.success(f"Selected: {', '.join(selected)}")
                    elif len(selected) > 0:
                        st.warning(f"Selected {len(selected)} – need exactly {tie['needed']}")

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
            col_a, col_b = st.columns(2)
            with col_a:
                if not has_conflict:
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

                        for p_idx in range(len(pool_names) - 1):
                            lower = pool_names[p_idx + 1]
                            upper = pool_names[p_idx]
                            move_n = pool_movers.get(lower, 1)
                            move_n = min(move_n, len(final_rankings[lower]) // 2, len(final_rankings[upper]) // 2)
                            if move_n < 1:
                                continue

                            up_list = final_rankings[lower][:move_n]
                            if f"{lower}_top (move up)" in st.session_state.skinny_results:
                                selected = st.session_state.skinny_results[f"{lower}_top (move up)"]
                                up_list = [r for r in final_rankings[lower] if r["name"] in selected][:move_n]
                            movers_up[lower] = up_list

                            down_list = final_rankings[upper][-move_n:]
                            if f"{upper}_bottom (move down)" in st.session_state.skinny_results:
                                selected = st.session_state.skinny_results[f"{upper}_bottom (move down)"]
                                down_list = [r for r in final_rankings[upper] if r["name"] in selected][-move_n:]
                            movers_down[upper] = down_list

                        for p_idx, pname in enumerate(pool_names):
                            ranking = final_rankings[pname]
                            staying = [r for r in ranking if not any(r["name"] == m["name"] for m in movers_up.get(pname, []) + movers_down.get(pname, []))]
                            incoming_down = movers_down.get(pool_names[p_idx - 1], []) if p_idx > 0 else []
                            incoming_up = movers_up.get(pool_names[p_idx + 1], []) if p_idx < num_pools - 1 else []

                            ordered = []
                            for r in incoming_down:
                                ordered.append({"Player": r["name"], "Note": f"(down from {pool_names[p_idx-1]})"})
                                for pl in pools[pool_names[p_idx-1]]:
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
                                ordered.append({"Player": r["name"], "Note": f"(up from {pool_names[p_idx+1]})"})
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
                                for m_idx, match in enumerate([x for x in rnd if is_match(x)]):
                                    key = f"{pname}_r{r_idx}_m{m_idx}"
                                    new_scores[key] = (play_to, play_to-1) if random.random() < 0.5 else (play_to-1, play_to)
                        st.session_state.scores.update(new_scores)

                        match_queue = []
                        court_status = {c: None for c in court_names}
                        court_queues = {}
                        if use_shared:
                            match_queue = build_interleaved_queue(new_schedules, pool_names, new_pools)
                            for i, court in enumerate(court_names):
                                if i < len(match_queue):
                                    court_status[court] = match_queue[i]
                            match_queue = match_queue[len(court_names):]
                        else:
                            court_queues = build_court_queues(new_schedules, pool_names, court_names, new_pools)
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
                    lines = [f"{p['name']}, {p['dupr']}" for p in st.session_state.players]
                    st.session_state.last_players_text = "\n".join(lines)
                    save_state()
                    st.rerun()

    # FINAL RESULTS
    if st.session_state.get("final_done"):
        st.markdown("---")
        centered_title("Final Results")
        cum = st.session_state.cumulative
        overall_list = sorted(cum.items(), key=lambda x: (x[1]["diff"], x[1]["wins"]), reverse=True)

        st.subheader("Top 3 Overall for the Day")
        for medal, (name, s) in assign_medals(overall_list, key_func=lambda x: (x[1]["diff"], x[1]["wins"])):
            st.write(f"{medal} **{name}** — +/− {s['diff']:+d} (Wins: {s['wins']})")

        st.subheader("Top 3 from Final Top Pool")
        if st.session_state.standings and pool_names:
            top_pool = st.session_state.standings.get(pool_names[0], [])
            for medal, r in assign_medals(top_pool, key_func=lambda x: (x["diff"], x["wins"])):
                st.write(f"{medal} **{r['name']}** — +/− {r['diff']:+d} (Wins: {r['wins']})")

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
            st.write(f"{medal} **{c['name']}** — Climbed **{c['climbed']:+d}** (#{c['start']} → #{c['final']})")

        st.success("Session complete! Overall Ladder has been updated.")

        st.markdown("---")
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                pd.DataFrame({
                    "Player": list(cum.keys()),
                    "+/−": [v["diff"] for v in cum.values()],
                    "Wins": [v["wins"] for v in cum.values()]
                }).to_excel(writer, sheet_name="Day Results", index=False)

                if climbers:
                    pd.DataFrame(climbers).to_excel(writer, sheet_name="Biggest Climbers", index=False)

                match_rows = []
                for entry in st.session_state.get("full_score_history", []):
                    for line in entry.get("lines", []):
                        match_rows.append({"Round": entry["title"], "Match": line})
                if match_rows:
                    pd.DataFrame(match_rows).to_excel(writer, sheet_name="All Match Scores", index=False)

                for entry in st.session_state.get("assignment_history", []):
                    if entry["type"] == "rankings":
                        for pname, ranking in entry["data"].items():
                            df = pd.DataFrame([{"#": j+1, "Player": r["name"], "+/−": r["diff"], "W": r["wins"]} for j, r in enumerate(ranking)])
                            sheet_name = f"{entry['title'][:20]}_{pname}"[:31]
                            df.to_excel(writer, sheet_name=sheet_name, index=False)

            st.download_button("📥 Download Full Excel Report", output.getvalue(), "pickleball_full_session_report.xlsx")
        except Exception as e:
            st.warning(f"Excel export error: {e}")

if st.session_state.get("created"):
    save_state()
