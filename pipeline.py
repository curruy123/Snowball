"""
Snowball — Data Pipeline
Fetches your Akali games from the Riot API and stores them locally.

Run:  python3 pipeline.py

Output: data/games.json  — raw game + timeline data
        data/processed.json — cleaned, feature-engineered dataset
"""

import json
import os
import time
import requests
from typing import Optional

# Load .env if present (pip install python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
RIOT_API_KEY = os.environ.get("RIOT_API_KEY", "")   # set in .env (see .env.example)
SUMMONER     = os.environ.get("SUMMONER", "")   # Name#TAG  e.g. KYLEAKALI#KR2
REGION       = os.environ.get("REGION",   "NA")     # KR, NA, EUW, etc.
GAME_COUNT   = int(os.environ.get("GAME_COUNT", 300))   # how many recent ranked games to scan (only Akali games are kept)
AKALI_ID     = 84
GUNBLADE_ID  = 3146

REGIONS = {
    "KR":  ("kr",  "asia"),
    "NA":  ("na1", "americas"),
    "EUW": ("euw1","europe"),
    "EUNE":("eun1","europe"),
}
# ─────────────────────────────────────────────────────────────────────────────

os.makedirs("data", exist_ok=True)


class RiotClient:
    def __init__(self, api_key, region):
        platform, routing = REGIONS.get(region.upper(), ("kr","asia"))
        self.platform = platform
        self.routing  = routing
        self.headers  = {"X-Riot-Token": api_key}

    def _get(self, url):
        r = requests.get(url, headers=self.headers)
        if r.status_code == 429:
            print("  Rate limited — waiting 10s...")
            time.sleep(10)
            return self._get(url)
        if r.status_code != 200:
            raise Exception(f"API {r.status_code}: {r.text[:200]}")
        return r.json()

    def get_puuid(self, name_tag):
        name, tag = name_tag.split("#", 1)
        url = (f"https://{self.routing}.api.riotgames.com"
               f"/riot/account/v1/accounts/by-riot-id"
               f"/{requests.utils.quote(name)}/{requests.utils.quote(tag)}")
        return self._get(url)["puuid"]

    def get_match_ids(self, puuid, count=100):
        all_ids = []
        start = 0
        batch = 100
        while len(all_ids) < count:
            fetch = min(batch, count - len(all_ids))
            url = (f"https://{self.routing}.api.riotgames.com"
                   f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
                   f"?queue=420&count={fetch}&start={start}")
            ids = self._get(url)
            if not ids:
                break
            all_ids.extend(ids)
            start += len(ids)
            time.sleep(1.5)
        return all_ids

    def get_match(self, mid):
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/{mid}"
        return self._get(url)

    def get_timeline(self, mid):
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/{mid}/timeline"
        return self._get(url)


# ── Feature extraction ────────────────────────────────────────────────────────

def ms(t): return t // 1000
def ts(t): return f"{ms(t)//60}:{ms(t)%60:02d}"

def frame_at(frames, target_ms):
    best, bd = None, float("inf")
    for f in frames:
        d = abs(f.get("timestamp",0) - target_ms)
        if d < bd:
            bd, best = d, f
    return best

def pf(frame, pid_str):
    return (frame or {}).get("participantFrames",{}).get(pid_str,{})

def cs(p): return p.get("minionsKilled",0) + p.get("jungleMinionsKilled",0)

def get_enemy_mid_str(parts, team_id):
    for p in parts:
        if p["teamId"] != team_id and p.get("teamPosition","").upper() in ("MIDDLE","MID"):
            return str(p["participantId"])
    return None


def extract_features(match, timeline, puuid):
    parts  = match["info"]["participants"]
    player = next((p for p in parts if p["puuid"] == puuid), None)
    if not player or player.get("championId") != AKALI_ID:
        return None

    pid     = player["participantId"]
    pid_str = str(pid)
    team_id = player["teamId"]
    frames  = timeline.get("info",{}).get("frames",[])
    events  = [e for f in frames for e in f.get("events",[])]

    enemy_mid_str = get_enemy_mid_str(parts, team_id)
    opp_champ = "Unknown"
    if enemy_mid_str:
        opp = next((p for p in parts if str(p["participantId"]) == enemy_mid_str), None)
        if opp: opp_champ = opp.get("championName","Unknown")

    # ── Gold lead over time (every 60s up to 30 min) ──────────────────────────
    gold_lead_timeline = []
    for t_s in range(0, 31*60, 60):
        f = frame_at(frames, t_s * 1000)
        if not f: break
        my_gold = pf(f, pid_str).get("totalGold", 0)
        em_gold = pf(f, enemy_mid_str).get("totalGold", 0) if enemy_mid_str else 0
        gold_lead_timeline.append({
            "t_s":      t_s,
            "my_gold":  my_gold,
            "em_gold":  em_gold,
            "lead":     my_gold - em_gold,
        })

    # ── XP lead timeline ──────────────────────────────────────────────────────
    xp_lead_timeline = []
    for t_s in range(0, 31*60, 60):
        f = frame_at(frames, t_s * 1000)
        if not f: break
        my_xp = pf(f, pid_str).get("xp", 0)
        em_xp = pf(f, enemy_mid_str).get("xp", 0) if enemy_mid_str else 0
        xp_lead_timeline.append({
            "t_s":  t_s,
            "lead": my_xp - em_xp,
        })

    # ── CS lead timeline ──────────────────────────────────────────────────────
    cs_lead_timeline = []
    for t_s in range(0, 31*60, 60):
        f = frame_at(frames, t_s * 1000)
        if not f: break
        my_cs = cs(pf(f, pid_str))
        em_cs = cs(pf(f, enemy_mid_str)) if enemy_mid_str else 0
        cs_lead_timeline.append({
            "t_s":  t_s,
            "lead": my_cs - em_cs,
        })

    # ── Snapshot leads at key times ───────────────────────────────────────────
    def gold_lead_at(t_s):
        f = frame_at(frames, t_s * 1000)
        if not f: return 0
        my = pf(f, pid_str).get("totalGold",0)
        em = pf(f, enemy_mid_str).get("totalGold",0) if enemy_mid_str else 0
        return my - em

    gold_lead_10 = gold_lead_at(10*60)
    gold_lead_15 = gold_lead_at(15*60)
    gold_lead_20 = gold_lead_at(20*60)

    # ── Objective events lookup ───────────────────────────────────────────────
    objective_events = [e for e in events if e.get("type") in (
        "BUILDING_KILL", "ELITE_MONSTER_KILL"
    )]

    def objective_lost_after(t_ms, window_ms=90000):
        for oe in objective_events:
            ot = oe.get("timestamp", 0)
            if t_ms < ot <= t_ms + window_ms:
                if oe.get("type") == "BUILDING_KILL":
                    if oe.get("teamId", 0) != team_id:
                        return True
                if oe.get("type") == "ELITE_MONSTER_KILL":
                    killer_id   = oe.get("killerId", 0)
                    killer_part = next((p for p in parts if p["participantId"] == killer_id), None)
                    if killer_part and killer_part["teamId"] != team_id:
                        return True
        return False

    def gold_swing_after(t_ms, window_ms=90000):
        f_now   = frame_at(frames, t_ms)
        f_later = frame_at(frames, t_ms + window_ms)
        lead_now   = pf(f_now,   pid_str).get("totalGold",0) - (pf(f_now,   enemy_mid_str).get("totalGold",0) if enemy_mid_str else 0)
        lead_later = pf(f_later, pid_str).get("totalGold",0) - (pf(f_later, enemy_mid_str).get("totalGold",0) if enemy_mid_str else 0)
        return lead_later - lead_now

    def classify_throw(t_ms, lead_at_death, bounty_est):
        obj_lost   = objective_lost_after(t_ms)
        gold_swing = gold_swing_after(t_ms)
        spiral = any(
            e.get("type") == "CHAMPION_KILL"
            and e.get("victimId") == pid
            and t_ms + 8000 < e.get("timestamp", 0) <= t_ms + 3*60*1000
            for e in events
        )
        if obj_lost and gold_swing < -500:
            return "clean_throw"
        elif bounty_est >= 500 and gold_swing < -400:
            return "shutdown_punished"
        elif spiral:
            return "spiral"
        elif gold_swing >= -100:
            return "absorbed"
        else:
            return "recovered"

    # ── Deaths while ahead ────────────────────────────────────────────────────
    deaths_while_ahead = []
    deaths_while_behind = []
    for e in events:
        if e.get("type") != "CHAMPION_KILL" or e.get("victimId") != pid:
            continue
        t_ms = e["timestamp"]
        t_s  = ms(t_ms)
        f    = frame_at(frames, t_ms)
        my_g = pf(f, pid_str).get("totalGold",0)
        em_g = pf(f, enemy_mid_str).get("totalGold",0) if enemy_mid_str else 0
        lead = my_g - em_g
        if lead >= 300:
            bounty_est = min(1000, 300 + lead // 10)
            outcome    = classify_throw(t_ms, lead, bounty_est)
            deaths_while_ahead.append({
                "t_s":           t_s,
                "lead_at_death": lead,
                "throw_outcome": outcome,
            })
        else:
            deaths_while_behind.append({"t_s": t_s, "lead_at_death": lead})

    # ── Gunblade window ───────────────────────────────────────────────────────
    gunblade_ms = None
    for e in events:
        if (e.get("type") == "ITEM_PURCHASED"
                and e.get("participantId") == pid
                and e.get("itemId") == GUNBLADE_ID):
            gunblade_ms = e["timestamp"]
            break

    gunblade_window = None
    if gunblade_ms and enemy_mid_str:
        end_ms = gunblade_ms + 3*60*1000
        f_s = frame_at(frames, gunblade_ms)
        f_e = frame_at(frames, end_ms)

        def diff(key_fn, pid_a, pid_b):
            return (key_fn(pf(f_e,pid_a)) - key_fn(pf(f_s,pid_a))) - \
                   (key_fn(pf(f_e,pid_b)) - key_fn(pf(f_s,pid_b)))

        gold_created = diff(lambda p: p.get("totalGold",0), pid_str, enemy_mid_str)
        xp_created   = diff(lambda p: p.get("xp",0),        pid_str, enemy_mid_str)
        cs_created   = diff(cs,                               pid_str, enemy_mid_str)

        # Kills/deaths in window (context only)
        w_events = [e for e in events
                    if gunblade_ms <= e.get("timestamp",0) < end_ms
                    and e.get("type") == "CHAMPION_KILL"]
        kills  = sum(1 for e in w_events if e.get("killerId") == pid)
        deaths = sum(1 for e in w_events if e.get("victimId") == pid)

        gunblade_window = {
            "time_str":     ts(gunblade_ms),
            "time_s":       ms(gunblade_ms),
            "gold_created": gold_created,
            "xp_created":   xp_created,
            "cs_created":   cs_created,
            "kills":        kills,
            "deaths":       deaths,
        }

    # ── Level 6 ───────────────────────────────────────────────────────────────
    level6_ms = None
    for e in events:
        if (e.get("type") == "LEVEL_UP"
                and e.get("participantId") == pid
                and e.get("level") == 6):
            level6_ms = e["timestamp"]
            break

    # ── First item spike ──────────────────────────────────────────────────────
    first_completed_item_ms = None
    for e in events:
        if (e.get("type") == "ITEM_PURCHASED"
                and e.get("participantId") == pid):
            t_ms = e["timestamp"]
            f_b  = frame_at(frames, t_ms - 5000)
            f_a  = frame_at(frames, t_ms + 5000)
            spent = pf(f_b,pid_str).get("totalGold",0) - pf(f_a,pid_str).get("totalGold",0)
            if spent >= 2500:
                first_completed_item_ms = t_ms
                break

    # ── Kills / objectives ────────────────────────────────────────────────────
    kills_by_time = [{"t_s": ms(e["timestamp"])}
                     for e in events
                     if e.get("type")=="CHAMPION_KILL" and e.get("killerId")==pid]
    deaths_by_time = [{"t_s": ms(e["timestamp"])}
                      for e in events
                      if e.get("type")=="CHAMPION_KILL" and e.get("victimId")==pid]

    duration = match["info"]["gameDuration"]

    # ── 15-min ML features (no data leakage — only events at/before 15:00) ──
    CUTOFF_MS = 15 * 60 * 1000
    ml15 = None
    if duration >= 15 * 60:  # game lasted at least 15 minutes
        f15 = frame_at(frames, CUTOFF_MS)
        if f15 and enemy_mid_str:
            my15 = pf(f15, pid_str)
            em15 = pf(f15, enemy_mid_str)
            # Pre-15 kill/death/assist events only
            early_kills   = sum(1 for e in events
                                if e.get("type")=="CHAMPION_KILL"
                                and e.get("killerId")==pid
                                and e.get("timestamp",0) <= CUTOFF_MS)
            early_deaths  = sum(1 for e in events
                                if e.get("type")=="CHAMPION_KILL"
                                and e.get("victimId")==pid
                                and e.get("timestamp",0) <= CUTOFF_MS)
            early_assists = sum(1 for e in events
                                if e.get("type")=="CHAMPION_KILL"
                                and pid in e.get("assistingParticipantIds",[])
                                and e.get("timestamp",0) <= CUTOFF_MS)
            em_kills_15  = sum(1 for e in events
                               if e.get("type")=="CHAMPION_KILL"
                               and e.get("killerId")==int(enemy_mid_str)
                               and e.get("timestamp",0) <= CUTOFF_MS)
            em_deaths_15 = sum(1 for e in events
                               if e.get("type")=="CHAMPION_KILL"
                               and e.get("victimId")==int(enemy_mid_str)
                               and e.get("timestamp",0) <= CUTOFF_MS)
            ml15 = {
                "gold_lead_15":  my15.get("totalGold",0) - em15.get("totalGold",0),
                "xp_lead_15":    my15.get("xp",0)        - em15.get("xp",0),
                "cs_lead_15":    cs(my15)                 - cs(em15),
                "kills_15":      early_kills,
                "deaths_15":     early_deaths,
                "assists_15":    early_assists,
                "em_kills_15":   em_kills_15,
                "em_deaths_15":  em_deaths_15,
            }

    return {
        "match_id":        match["metadata"]["matchId"],
        "game_timestamp":  match["info"].get("gameCreation", 0),  # epoch ms, for chronological sort
        "win":             player["win"],
        "duration":        duration,
        "opponent":        opp_champ,
        "kda":             f"{player['kills']}/{player['deaths']}/{player['assists']}",
        "kills":           player["kills"],
        "deaths":          player["deaths"],
        "assists":         player["assists"],
        "cs_total":        player["totalMinionsKilled"] + player.get("neutralMinionsKilled",0),
        "damage":          player["totalDamageDealtToChampions"],

        # Lead timelines
        "gold_lead_timeline": gold_lead_timeline,
        "xp_lead_timeline":   xp_lead_timeline,
        "cs_lead_timeline":   cs_lead_timeline,

        # Snapshot leads
        "gold_lead_10":    gold_lead_10,
        "gold_lead_15":    gold_lead_15,
        "gold_lead_20":    gold_lead_20,

        # Key events
        "level6_s":        ms(level6_ms) if level6_ms else None,
        "gunblade_s":      ms(gunblade_ms) if gunblade_ms else None,
        "first_item_s":    ms(first_completed_item_ms) if first_completed_item_ms else None,

        # Spike windows
        "gunblade_window": gunblade_window,

        # Deaths
        "deaths_while_ahead":  deaths_while_ahead,
        "deaths_while_behind": deaths_while_behind,
        "n_deaths_ahead":      len(deaths_while_ahead),
        "n_deaths_behind":     len(deaths_while_behind),

        # Raw event lists
        "kills_by_time":   kills_by_time,
        "deaths_by_time":  deaths_by_time,

        # 15-min ML features (None if game < 15 min or missing enemy mid data)
        "ml15":            ml15,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not RIOT_API_KEY or not SUMMONER:
        print("ERROR: Set RIOT_API_KEY and SUMMONER in a .env file (copy .env.example)")
        return

    client = RiotClient(RIOT_API_KEY, REGION)

    print(f"Fetching PUUID for {SUMMONER}...")
    puuid = client.get_puuid(SUMMONER)
    print(f"PUUID: {puuid[:20]}...")

    print(f"\nFetching last {GAME_COUNT} ranked match IDs...")
    match_ids = client.get_match_ids(puuid, count=GAME_COUNT)
    print(f"Found {len(match_ids)} matches")

    games = []
    skipped = 0

    for i, mid in enumerate(match_ids):
        print(f"  [{i+1}/{len(match_ids)}] {mid}...", end=" ")
        try:
            match    = client.get_match(mid)
            timeline = client.get_timeline(mid)
            features = extract_features(match, timeline, puuid)

            if features is None:
                print("skip (not Akali)")
                skipped += 1
            else:
                games.append(features)
                print(f"✓  vs {features['opponent']}  "
                      f"{'W' if features['win'] else 'L'}  {features['kda']}")
        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(0.12)  # stay under rate limit

    print(f"\nDone. {len(games)} Akali games processed, {skipped} skipped.")

    # Sort oldest → newest so chronological train/test split is meaningful
    games.sort(key=lambda g: g.get("game_timestamp", 0))

    # Save
    with open("data/processed.json","w") as f:
        json.dump(games, f, indent=2)

    print(f"Saved to data/processed.json")
    print(f"\nQuick stats:")
    wins   = sum(1 for g in games if g["win"])
    print(f"  Win rate: {wins}/{len(games)} ({wins/len(games)*100:.0f}%)")
    gb_games = sum(1 for g in games if g["gunblade_window"])
    print(f"  Gunblade detected: {gb_games}/{len(games)} games")
    ahead_deaths = sum(g["n_deaths_ahead"] for g in games)
    print(f"  Total deaths while ahead: {ahead_deaths}")


if __name__ == "__main__":
    main()
