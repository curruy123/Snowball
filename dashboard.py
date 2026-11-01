"""
Snowball — Dashboard Generator
Reads data/processed.json and produces dashboard/index.html

Run:  python3 dashboard.py
Then: open dashboard/index.html
"""

import json
import os
import statistics
from collections import defaultdict

os.makedirs("dashboard", exist_ok=True)

with open("data/processed.json") as f:
    games = json.load(f)

wins   = [g for g in games if g["win"]]
losses = [g for g in games if not g["win"]]
total  = len(games)
wr_pct = round(len(wins)/total*100, 1)

print(f"Loaded {total} games  ({len(wins)}W / {len(losses)}L)")


# ── Stat helpers ──────────────────────────────────────────────────────────────

def avg(lst): return round(sum(lst)/len(lst), 1) if lst else 0
def signed(n): return f"+{n}" if n >= 0 else str(n)


# ── 1. Lead Decay Curve data ──────────────────────────────────────────────────
# Average gold lead per minute, split by win/loss

def avg_lead_at_minute(game_list, minute):
    leads = []
    for g in game_list:
        tl = g.get("gold_lead_timeline", [])
        entry = next((e for e in tl if e["t_s"] == minute*60), None)
        if entry:
            leads.append(entry["lead"])
    return avg(leads)

minutes = list(range(0, 26))

win_curve  = [avg_lead_at_minute(wins,   m) for m in minutes]
loss_curve = [avg_lead_at_minute(losses, m) for m in minutes]

# Also XP
def avg_xp_at_minute(game_list, minute):
    leads = []
    for g in game_list:
        tl = g.get("xp_lead_timeline", [])
        entry = next((e for e in tl if e["t_s"] == minute*60), None)
        if entry:
            leads.append(entry["lead"])
    return avg(leads)

win_xp_curve  = [avg_xp_at_minute(wins,   m) for m in minutes]
loss_xp_curve = [avg_xp_at_minute(losses, m) for m in minutes]


# ── 2. Gunblade Window data ───────────────────────────────────────────────────

gb_wins   = [g for g in wins   if g.get("gunblade_window")]
gb_losses = [g for g in losses if g.get("gunblade_window")]

def gb_scatter(game_list, outcome_label):
    points = []
    for g in game_list:
        w = g["gunblade_window"]
        if w:
            points.append({
                "x":       w["gold_created"],
                "y":       w["xp_created"],
                "cs":      w["cs_created"],
                "opp":     g["opponent"],
                "kda":     g["kda"],
                "time":    w["time_str"],
                "outcome": outcome_label,
                "kills":   w["kills"],
                "deaths":  w["deaths"],
            })
    return points

gb_win_points  = gb_scatter(gb_wins,   "WIN")
gb_loss_points = gb_scatter(gb_losses, "LOSS")

avg_gb_gold_win  = avg([p["x"] for p in gb_win_points])
avg_gb_gold_loss = avg([p["x"] for p in gb_loss_points])
avg_gb_xp_win    = avg([p["y"] for p in gb_win_points])
avg_gb_xp_loss   = avg([p["y"] for p in gb_loss_points])


# ── 3. Deaths While Ahead ─────────────────────────────────────────────────────

win_dwa  = avg([g["n_deaths_ahead"] for g in wins])
loss_dwa = avg([g["n_deaths_ahead"] for g in losses])

# Death timing distribution
ahead_death_times_win  = [d["t_s"]//60 for g in wins   for d in g["deaths_while_ahead"]]
ahead_death_times_loss = [d["t_s"]//60 for g in losses for d in g["deaths_while_ahead"]]

def minute_distribution(times, max_min=30):
    dist = [0] * max_min
    for t in times:
        if 0 <= t < max_min:
            dist[t] += 1
    return dist

dwa_win_dist  = minute_distribution(ahead_death_times_win)
dwa_loss_dist = minute_distribution(ahead_death_times_loss)


# ── 4. Key snapshot stats ─────────────────────────────────────────────────────

gl10_wins  = avg([g["gold_lead_10"] for g in wins  if g["gold_lead_10"] is not None])
gl10_loss  = avg([g["gold_lead_10"] for g in losses if g["gold_lead_10"] is not None])
gl15_wins  = avg([g["gold_lead_15"] for g in wins  if g["gold_lead_15"] is not None])
gl15_loss  = avg([g["gold_lead_15"] for g in losses if g["gold_lead_15"] is not None])

gb_time_wins  = avg([g["gunblade_s"]//60 for g in wins   if g.get("gunblade_s")])
gb_time_losses= avg([g["gunblade_s"]//60 for g in losses if g.get("gunblade_s")])
l6_time_wins  = avg([g["level6_s"]       for g in wins   if g.get("level6_s")])
l6_time_losses= avg([g["level6_s"]       for g in losses if g.get("level6_s")])


# ── 5. Per-game table data ────────────────────────────────────────────────────

game_rows = []
for g in sorted(games, key=lambda x: x.get("game_timestamp",0), reverse=True)[:50]:
    gb = g.get("gunblade_window")
    game_rows.append({
        "opponent":    g["opponent"],
        "outcome":     "W" if g["win"] else "L",
        "kda":         g["kda"],
        "gl15":        signed(g.get("gold_lead_15", 0)),
        "gb_gold":     signed(gb["gold_created"]) if gb else "—",
        "dwa":         g["n_deaths_ahead"],
        "duration":    f"{g['duration']//60}:{g['duration']%60:02d}",
    })


# ── Build HTML ────────────────────────────────────────────────────────────────

# Build table rows (avoids nested f-string issues)
def _row(r):
    win_cls = "win-badge" if r["outcome"]=="W" else "loss-badge"
    gl_cls  = "green" if r["gl15"].startswith("+") else "red"
    gb_val  = r["gb_gold"]
    if gb_val != "—":
        gb_cls = "green" if gb_val.startswith("+") else "red"
        gb_txt = gb_val + "g"
    else:
        gb_cls = ""
        gb_txt = "—"
    dwa_cls = "red" if int(r["dwa"]) > 0 else "green"
    return (f"        <tr>"
            f"<td>{r['opponent']}</td>"
            f"<td class=\"{win_cls}\">{r['outcome']}</td>"
            f"<td>{r['kda']}</td>"
            f"<td class=\"{gl_cls}\">{r['gl15']}g</td>"
            f"<td class=\"{gb_cls}\">{gb_txt}</td>"
            f"<td class=\"{dwa_cls}\">{r['dwa']}</td>"
            f"<td>{r['duration']}</td>"
            f"</tr>\n")

table_rows = "".join(_row(r) for r in game_rows)


# ── Lead Conversion Rate ──────────────────────────────────────────────────────
LEAD_THRESHOLD = 300   # gold ahead = "ahead"

def categorize_lead(gold_lead):
    if gold_lead >= LEAD_THRESHOLD:   return "ahead"
    if gold_lead <= -LEAD_THRESHOLD:  return "behind"
    return "even"

def lead_conversion(game_list, minute):
    ahead_wins = ahead_total = 0
    behind_wins = behind_total = 0
    even_wins = even_total = 0
    for g in game_list:
        tl = g.get("gold_lead_timeline", [])
        entry = next((e for e in tl if e["t_s"] == minute*60), None)
        if not entry: continue
        cat = categorize_lead(entry["lead"])
        won = g["win"]
        if cat == "ahead":
            ahead_total += 1
            if won: ahead_wins += 1
        elif cat == "behind":
            behind_total += 1
            if won: behind_wins += 1
        else:
            even_total += 1
            if won: even_wins += 1
    return {
        "ahead":  {"wins": ahead_wins,  "total": ahead_total,
                   "pct": round(ahead_wins/ahead_total*100)   if ahead_total  else 0},
        "behind": {"wins": behind_wins, "total": behind_total,
                   "pct": round(behind_wins/behind_total*100) if behind_total else 0},
        "even":   {"wins": even_wins,   "total": even_total,
                   "pct": round(even_wins/even_total*100)     if even_total   else 0},
    }

conv_10 = lead_conversion(games, 10)
conv_15 = lead_conversion(games, 15)
conv_20 = lead_conversion(games, 20)

# ── Game Length Distribution ───────────────────────────────────────────────────
BUCKETS = [
    ("< 20 min",  0,    20*60),
    ("20–25 min", 20*60, 25*60),
    ("25–30 min", 25*60, 30*60),
    ("30–35 min", 30*60, 35*60),
    ("35–40 min", 35*60, 40*60),
    ("> 40 min",  40*60, 9999*60),
]

def game_length_buckets(game_list):
    counts = [0] * len(BUCKETS)
    for g in game_list:
        d = g.get("duration", 0)
        for i, (_, lo, hi) in enumerate(BUCKETS):
            if lo <= d < hi:
                counts[i] += 1
                break
    return counts

bucket_labels   = [b[0] for b in BUCKETS]
win_len_counts  = game_length_buckets(wins)
loss_len_counts = game_length_buckets(losses)
all_len_counts  = [w+l for w,l in zip(win_len_counts, loss_len_counts)]

# Win rate per bucket
len_wr = []
for w, a in zip(win_len_counts, all_len_counts):
    len_wr.append(round(w/a*100) if a else 0)

avg_duration_wins  = avg([g["duration"] for g in wins])
avg_duration_losses= avg([g["duration"] for g in losses])

all_games_json = json.dumps([{'win': g['win'], 'n_deaths_ahead': g['n_deaths_ahead']} for g in games])

# ── Throw Indicator ───────────────────────────────────────────────────────────
THROW_LABELS = {
    'clean_throw':       'Clean Throw',
    'shutdown_punished': 'Shutdown Punished',
    'spiral':            'Spiral',
    'absorbed':          'Absorbed',
    'recovered':         'Recovered',
}
THROW_COLORS = {
    'clean_throw':       '#ff2d4e',
    'shutdown_punished': '#ff8c00',
    'spiral':            '#c43aff',
    'absorbed':          '#2ed87a',
    'recovered':         '#28d4d4',
}

throw_counts = {k: 0 for k in THROW_LABELS}
throw_win    = {k: 0 for k in THROW_LABELS}
throw_loss   = {k: 0 for k in THROW_LABELS}

for g in games:
    for d in g.get("deaths_while_ahead", []):
        outcome = d.get("throw_outcome")
        if outcome in throw_counts:
            throw_counts[outcome] += 1
            if g["win"]:
                throw_win[outcome]  += 1
            else:
                throw_loss[outcome] += 1

total_ahead_deaths = sum(throw_counts.values())

throw_rows_html = ""
for k, label in THROW_LABELS.items():
    count   = throw_counts[k]
    pct     = round(count / total_ahead_deaths * 100) if total_ahead_deaths else 0
    t_wins  = throw_win[k]
    t_losses= throw_loss[k]
    wr      = round(t_wins / count * 100) if count else 0
    color   = THROW_COLORS[k]
    wr_cls  = "green" if wr >= 50 else "red"
    throw_rows_html += (
        f'<tr>'
        f'<td><span style="color:{color};font-weight:700">{label}</span></td>'
        f'<td>{count} <span style="color:#666">({pct}%)</span></td>'
        f'<td style="color:#2ed87a">{t_wins}W</td>'
        f'<td style="color:#ff2d4e">{t_losses}L</td>'
        f'<td class="{wr_cls}">{wr}%</td>'
        f'</tr>\n'
    )

throw_chart_labels = json.dumps([THROW_LABELS[k] for k in THROW_LABELS])
throw_chart_counts = json.dumps([throw_counts[k] for k in THROW_LABELS])
throw_chart_colors = json.dumps([THROW_COLORS[k] for k in THROW_LABELS])


# ── Win Probability (Section 7) ───────────────────────────────────────────────
_MODEL_PARAMS_PATH = "models/model_params.json"
# ── VOD Review Moments (Section 7) ───────────────────────────────────────────
def _fmt_ts(s):
    return f"{s//60}:{s%60:02d}"

def _find_lead_drop(timeline, window_mins=3):
    if not timeline or len(timeline) < window_mins + 1:
        return None
    best = None
    for i in range(len(timeline)):
        t_start = timeline[i]
        for j in range(i + 1, min(i + window_mins + 1, len(timeline))):
            drop = t_start['lead'] - timeline[j]['lead']
            if drop > 0 and (best is None or drop > best['drop']):
                best = {
                    'peak_t_s':    t_start['t_s'],
                    'trough_t_s':  timeline[j]['t_s'],
                    'peak_lead':   t_start['lead'],
                    'trough_lead': timeline[j]['lead'],
                    'drop':        drop,
                }
    return best

# Review moments come from the MOST RECENT game, so there is always something
# fresh to watch. Each death is scored by how much lead was lost in the 2 minutes
# after it (extra weight if you died while ahead). Lead drops without a death are
# also considered. A fallback guarantees at least one moment per game.
from datetime import datetime as _dt

def _lead_at(timeline, t_s):
    """Gold lead at the last snapshot at or before t_s."""
    pts = [p for p in timeline if p['t_s'] <= t_s]
    return pts[-1]['lead'] if pts else (timeline[0]['lead'] if timeline else 0)

def _min_lead_after(timeline, t_s, window_s=150):
    pts = [p for p in timeline if t_s < p['t_s'] <= t_s + window_s]
    if not pts:
        return None
    low = min(pts, key=lambda p: p['lead'])
    return low

def _review_candidates(g):
    tl = g.get('gold_lead_timeline') or []
    if not tl:
        return []
    cands = []
    # 1) Deaths, scored by what they cost
    for d in g.get('deaths_by_time') or []:
        t = d['t_s']
        before = _lead_at(tl, t)
        low = _min_lead_after(tl, t)
        after = low['lead'] if low else before
        swing = max(0, before - after)
        ahead = before >= 300
        game_end = g.get('duration') or 0
        decisive = (not g.get('win')) and game_end and (game_end - t) <= 90
        # Bigger leads are more costly to throw; a death right before a loss likely decided it
        score = (swing + (600 + 0.25 * before if ahead else 0)
                 + (300 if before > 0 and after < 0 else 0) + (1500 if decisive else 0))
        if decisive:
            label, why = 'Game-deciding death', (
                f"You died at {_fmt_ts(t)} with your lead at {before:+,}g, "
                f"and the game ended {game_end - t} seconds later in a loss.")
            ask = 'What was the call here? Was this fight or objective worth contesting, and where was your team?'
        elif ahead:
            label, why = 'Died while ahead', (
                f"You died at {_fmt_ts(t)} while {before:+,}g ahead. "
                f"Over the next 2 minutes your lead went to {after:+,}g.")
            ask = 'Was this fight worth taking with a lead? Check vision, enemy jungler position and summoner spells before you went in.'
        elif swing >= 300:
            label, why = 'Costly death', (
                f"You died at {_fmt_ts(t)} and lost {swing:,}g of lead in the next 2 minutes "
                f"({before:+,}g → {after:+,}g).")
            ask = 'What did the death cost: a wave, a plate, an objective? Could you have backed earlier?'
        else:
            label, why = 'Death', f"You died at {_fmt_ts(t)} with your lead at {before:+,}g."
            ask = 'Was there a warning sign before this death you could have played around?'
        cands.append({'type': 'death', 'label': label, 'why': why, 'ask': ask, 'score': score,
                      'end_note': f"Lost {game_end - t}s later" if decisive else None,
                      't_s': t, 'lead_before': before, 'lead_after': after, 'swing': swing,
                      'start_s': max(0, t - 25), 'end_s': t + 10})
    # 2) Lead slipping away without needing a death
    drop = _find_lead_drop(tl, window_mins=3)
    if drop and drop['drop'] >= 300:
        cands.append({'type': 'drop', 'label': 'Lead slipped away',
                      'why': (f"Your gold lead fell from {drop['peak_lead']:+,}g at {_fmt_ts(drop['peak_t_s'])} "
                              f"to {drop['trough_lead']:+,}g at {_fmt_ts(drop['trough_t_s'])}."),
                      'ask': 'Look at waves, back timings and rotations in this window. Where did the gold go?',
                      'score': drop['drop'] + (300 if drop['peak_lead'] >= 300 else 0),
                      't_s': drop['peak_t_s'], 'lead_before': drop['peak_lead'],
                      'lead_after': drop['trough_lead'], 'swing': drop['drop'],
                      'start_s': max(0, drop['peak_t_s'] - 30), 'end_s': drop['trough_t_s'] + 30})
    # 3) Fallback: a clean game still gets one moment to study
    if not cands:
        if drop:
            cands.append({'type': 'drop', 'label': 'Biggest swing',
                          'why': (f"No deaths and no big drops, but your lead dipped most between "
                                  f"{_fmt_ts(drop['peak_t_s'])} and {_fmt_ts(drop['trough_t_s'])} "
                                  f"({drop['peak_lead']:+,}g → {drop['trough_lead']:+,}g)."),
                          'ask': 'Even in a clean game, what gave the enemy room to catch up here?',
                          'score': drop['drop'], 't_s': drop['peak_t_s'],
                          'lead_before': drop['peak_lead'], 'lead_after': drop['trough_lead'],
                          'swing': drop['drop'], 'start_s': max(0, drop['peak_t_s'] - 30),
                          'end_s': drop['trough_t_s'] + 30})
        else:
            low = min(tl, key=lambda p: p['lead'])
            cands.append({'type': 'low', 'label': 'Weakest point',
                          'why': f"Your lead was lowest at {_fmt_ts(low['t_s'])} ({low['lead']:+,}g).",
                          'ask': 'What was happening in lane right before this?',
                          'score': 0, 't_s': low['t_s'], 'lead_before': low['lead'],
                          'lead_after': low['lead'], 'swing': 0,
                          'start_s': max(0, low['t_s'] - 60), 'end_s': low['t_s'] + 15})
    # Don't show a death and a lead drop that are really the same moment twice
    cands.sort(key=lambda c: c['score'], reverse=True)
    picked = []
    for c in cands:
        if all(abs(c['t_s'] - p['t_s']) > 60 for p in picked):
            picked.append(c)
    for c in picked:
        c['time'] = _fmt_ts(c['t_s'])
        c['replay_start'] = _fmt_ts(c['start_s'])
        c['replay_end'] = _fmt_ts(c['end_s'])
    return picked

_review = None
for _g in sorted(games, key=lambda g: g.get('game_timestamp', 0), reverse=True):
    _picked = _review_candidates(_g)
    if _picked:
        _ts = _g.get('game_timestamp')
        _review = {
            'opponent': _g.get('opponent', '?'),
            'win':      _g['win'],
            'kda':      _g.get('kda', ''),
            'date':     _dt.fromtimestamp(_ts / 1000).strftime('%b %-d') if _ts else '',
            'duration': _fmt_ts(_g.get('duration', 0)),
            'top':      _picked[0],
            'more':     _picked[1:3],
        }
        break
_vod_json = json.dumps(_review)
print(f"Review moment — most recent game vs {_review['opponent']}: {_review['top']['label']} at {_review['top']['time']}" if _review else "Review moment — none found")



# ── Key insight: what happens to leads you hold vs leads you throw ──────────
# Only games that reached 15 minutes with a valid lane matchup (same set the model uses)
_ahead15 = [g for g in games if g.get('ml15') and g['ml15']['gold_lead_15'] >= 500]
_held    = [g for g in _ahead15 if g.get('n_deaths_ahead', 0) == 0]
_thrown  = [g for g in _ahead15 if g.get('n_deaths_ahead', 0) >= 2]
def _wr(lst): return round(sum(1 for g in lst if g['win']) / len(lst) * 100) if lst else 0
held_wr, held_n     = _wr(_held), len(_held)
thrown_wr, thrown_n = _wr(_thrown), len(_thrown)
ahead_wr, ahead_n   = _wr(_ahead15), len(_ahead15)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Snowball: Do Early Leads Win Games?</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>


<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:      #0b0d12;
    --surface: #12151c;
    --raised:  #181c25;
    --border:  #232836;
    --text:    #eceef3;
    --muted:   #8b93a7;
    --faint:   #5b6275;
    --red:     #ff4d5e;
    --green:   #34d399;
    --gold:    #f5b94a;
    --cyan:    #38bdf8;
    --orange:  #fb923c;
    --radius:  16px;
    /* legacy names used by inline styles */
    --void: #07080c; --base: var(--bg); --panel: var(--surface); --card: var(--surface);
    --silver: var(--muted); --smoke: var(--faint); --white: var(--text); --off: #c9cdd8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; scroll-padding-top: 76px; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
          font-size: 14px; line-height: 1.6; -webkit-font-smoothing: antialiased; }}
  ::selection {{ background: var(--red); color: #fff; }}

  /* Top bar */
  .topbar {{ position: sticky; top: 0; z-index: 20; background: rgba(11,13,18,.82); backdrop-filter: blur(14px);
             -webkit-backdrop-filter: blur(14px); border-bottom: 1px solid var(--border); }}
  .topbar-inner {{ max-width: 1180px; margin: 0 auto; padding: 0 28px; height: 60px; display: flex; align-items: center; gap: 28px; }}
  .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 16px; letter-spacing: -.01em; }}
  .brand-mark {{ width: 22px; height: 22px; border-radius: 50%; background: radial-gradient(circle at 35% 30%, #fff 0 18%, #dfe7ff 30%, #9fb2e8 70%, #6b7fbf 100%);
                 box-shadow: 0 0 0 3px rgba(255,255,255,.06); }}
  .tabs {{ display: flex; gap: 4px; overflow-x: auto; scrollbar-width: none; min-width: 0; }}
  .tabs::-webkit-scrollbar {{ display: none; }}
  .tabs a {{ color: var(--muted); text-decoration: none; font-size: 13px; font-weight: 600; padding: 7px 12px; border-radius: 999px;
             white-space: nowrap; transition: background .2s, color .2s; }}
  .tabs a:hover {{ color: var(--text); background: var(--raised); }}
  .tabs a.active {{ color: var(--text); background: var(--raised); box-shadow: inset 0 0 0 1px var(--border); }}
  .topbar-meta {{ margin-left: auto; font-size: 12px; color: var(--muted); white-space: nowrap; }}
  .topbar-meta b {{ color: var(--text); font-weight: 600; }}

  /* Layout */
  .container {{ max-width: 1180px; margin: 0 auto; padding: 0 28px 40px; }}
  section.block {{ padding: 72px 0 0; }}
  .eyebrow {{ display: inline-flex; align-items: center; gap: 8px; font-family: 'JetBrains Mono', monospace; font-size: 11px;
              font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin-bottom: 12px; }}
  .eyebrow::before {{ content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--red); }}
  .block-title {{ font-size: 28px; font-weight: 700; letter-spacing: -.02em; line-height: 1.2; margin-bottom: 8px; }}
  .block-sub {{ font-size: 15px; color: var(--muted); max-width: 640px; margin-bottom: 28px; }}

  /* Hero */
  .hero {{ padding: 64px 0 8px; }}
  .hero h1 {{ font-size: clamp(32px, 5vw, 52px); font-weight: 800; letter-spacing: -.035em; line-height: 1.05; max-width: 15ch; }}
  .hero h1 span {{ background: linear-gradient(90deg, #dfe7ff, #8fa6e6); -webkit-background-clip: text; background-clip: text; color: transparent; }}
  .hero p {{ font-size: 16px; color: var(--muted); max-width: 560px; margin-top: 16px; }}

  .insight-hero {{ margin-top: 36px; display: grid; grid-template-columns: 1.1fr 1fr 1fr; gap: 1px; background: var(--border);
                   border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }}
  .insight-hero > div {{ background: var(--surface); padding: 26px 28px; }}
  .insight-hero .lead {{ background: linear-gradient(160deg, #1a1f2b, var(--surface)); }}
  .ih-label {{ font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 10px; }}
  .ih-text {{ font-size: 18px; font-weight: 600; line-height: 1.4; letter-spacing: -.01em; }}
  .ih-num {{ font-size: 44px; font-weight: 800; letter-spacing: -.03em; line-height: 1; }}
  .ih-sub {{ font-size: 12px; color: var(--muted); margin-top: 8px; }}
  .bar {{ height: 6px; border-radius: 99px; background: var(--raised); margin-top: 14px; overflow: hidden; }}
  .bar i {{ display: block; height: 100%; border-radius: 99px; }}

  /* KPI tiles */
  .pills {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 16px; }}
  .pill {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 18px 20px; }}
  .pill-label {{ font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }}
  .pill-value {{ font-size: 26px; font-weight: 800; letter-spacing: -.02em; line-height: 1; }}
  .pill-sub {{ font-size: 12px; color: var(--faint); margin-top: 6px; }}
  .green {{ color: var(--green); }} .red {{ color: var(--red); }} .gold {{ color: var(--gold); }}
  .cyan {{ color: var(--cyan); }} .white {{ color: var(--text); }}

  /* Cards & charts */
  .chart-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
  .chart-grid + .chart-grid {{ margin-top: 16px; }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; min-width: 0;
                 transition: border-color .2s; }}
  .chart-card:hover {{ border-color: #2f3646; }}
  .chart-card.wide {{ grid-column: 1 / -1; }}
  .chart-title {{ font-size: 15px; font-weight: 700; letter-spacing: -.01em; margin-bottom: 4px; }}
  .chart-sub {{ font-size: 13px; color: var(--muted); margin-bottom: 20px; }}
  .chart-container {{ position: relative; height: 280px; }}
  .chart-container.tall {{ height: 360px; }}
  .insight {{ position: relative; background: var(--raised); border-radius: 12px; padding: 14px 16px 14px 42px; margin-top: 18px;
              font-size: 13px; color: var(--off); line-height: 1.55; }}
  .insight::before {{ content: "💡"; position: absolute; left: 16px; top: 14px; font-size: 14px; line-height: 1.4; }}
  .insight strong {{ color: var(--text); }}

  /* Tables */
  .table-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }}
  .table-header {{ padding: 20px 24px; border-bottom: 1px solid var(--border); }}
  .table-scroll {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ font-size: 11px !important; font-weight: 600 !important; letter-spacing: .04em !important; text-transform: uppercase;
        color: var(--muted) !important; padding: 12px 18px !important; text-align: left; background: var(--raised) !important; }}
  td {{ padding: 12px 18px; border-top: 1px solid var(--border); font-size: 13px; color: var(--off);
        font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }}
  tbody tr {{ transition: background .15s; }}
  tbody tr:hover td {{ background: rgba(255,255,255,.025); }}
  .win-badge  {{ color: var(--green); font-weight: 700; }}
  .loss-badge {{ color: var(--red);   font-weight: 700; }}

  .divider {{ display: none; }}
  .footer {{ text-align: center; padding: 48px 28px; color: var(--faint); font-size: 12px; border-top: 1px solid var(--border); margin-top: 72px; }}
  .footer span {{ color: var(--muted); }}

  @media (max-width: 900px) {{
    .insight-hero {{ grid-template-columns: 1fr; }}
    .pills {{ grid-template-columns: repeat(2, 1fr); }}
    .chart-grid {{ grid-template-columns: 1fr; }}
    .topbar-meta {{ display: none; }}
    .topbar-inner {{ gap: 16px; padding: 0 16px; }}
    .container {{ padding: 0 16px 32px; }}
    section.block {{ padding-top: 56px; }}
    .block-title {{ font-size: 24px; }}
  }}
  @media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
</style>
</head>
<body>

<header class="topbar">
  <div class="topbar-inner">
    <div class="brand"><span class="brand-mark" aria-hidden="true"></span>Snowball</div>
    <nav class="tabs" aria-label="Sections">
      <a href="#overview">Overview</a>
      <a href="#review">Review</a>
      <a href="#leads">Leads</a>
      <a href="#conversion">Conversion</a>
      <a href="#deaths">Deaths</a>
      <a href="#gunblade">Gunblade</a>
      <a href="#length">Game length</a>
      <a href="#games">Games</a>
    </nav>
    <div class="topbar-meta"><b>{total}</b> Akali games · <b class="{'green' if wr_pct >= 50 else 'red'}">{wr_pct}%</b> WR</div>
  </div>
</header>

<div class="container">
  <section class="hero" id="overview">
    <div class="eyebrow">Overview</div>
    <h1>Do early leads in League <span>actually win games?</span></h1>
    <p>A look at {total} of my ranked Akali games: when my leads turn into wins, when I throw them, and which moment from my latest game is worth reviewing.</p>

    <div class="insight-hero">
      <div class="lead">
        <div class="ih-label">Key finding</div>
        <div class="ih-text">Getting ahead matters. <strong>Staying alive while ahead</strong> matters more.</div>
        <div class="ih-sub">Games where I was 500g+ ahead at 15 minutes ({ahead_n} games, {ahead_wr}% win rate)</div>
      </div>
      <div>
        <div class="ih-label">Never died while ahead</div>
        <div class="ih-num green">{held_wr}%</div>
        <div class="ih-sub">win rate · {held_n} games</div>
        <div class="bar"><i style="width:{held_wr}%;background:var(--green)"></i></div>
      </div>
      <div>
        <div class="ih-label">Died 2+ times while ahead</div>
        <div class="ih-num red">{thrown_wr}%</div>
        <div class="ih-sub">win rate · {thrown_n} games</div>
        <div class="bar"><i style="width:{thrown_wr}%;background:var(--red)"></i></div>
      </div>
    </div>

    <div class="pills">
    <div class="pill">
      <div class="pill-label">Win Rate</div>
      <div class="pill-value {'green' if wr_pct >= 50 else 'red'}">{wr_pct}%</div>
      <div class="pill-sub">{len(wins)}W / {len(losses)}L</div>
    </div>
    <div class="pill">
      <div class="pill-label">Gold Lead @15 (wins)</div>
      <div class="pill-value gold">{signed(int(gl15_wins))}g</div>
      <div class="pill-sub">vs {signed(int(gl15_loss))}g in losses</div>
    </div>
    <div class="pill">
      <div class="pill-label">Avg Gunblade Time</div>
      <div class="pill-value cyan">{int(gb_time_wins)}:00</div>
      <div class="pill-sub">{int(gb_time_losses)}:00 in losses</div>
    </div>
    <div class="pill">
      <div class="pill-label">Deaths While Ahead</div>
      <div class="pill-value {'green' if win_dwa < loss_dwa else 'red'}">{win_dwa}</div>
      <div class="pill-sub">{loss_dwa} avg in losses</div>
    </div>
    <div class="pill">
      <div class="pill-label">GB Gold Created (wins)</div>
      <div class="pill-value gold">{signed(int(avg_gb_gold_win))}g</div>
      <div class="pill-sub">{signed(int(avg_gb_gold_loss))}g in losses</div>
    </div>
  </div>

  
  </section>

  <section class="block" id="review">
    <div class="eyebrow">01 · Review</div>
    <h2 class="block-title">Review this moment</h2>
    <p class="block-sub">The most costly moment from my latest game, picked automatically. Open the replay in the client and jump to the window below.</p>
    <!-- Section 7: VOD Review -->
  
  <div id="vod-section">
  </div>

  
  </section>

  <section class="block" id="leads">
    <div class="eyebrow">02 · Leads</div>
    <h2 class="block-title">How leads grow or slip</h2>
    <p class="block-sub">Average gold and XP lead over the enemy mid laner, split by wins and losses. Where the lines split is where games are decided.</p>
    <!-- Section 1: Lead Decay Curves -->
  

  <div class="chart-grid">
    <div class="chart-card">
      <div class="chart-title">Gold Lead Over Time</div>
      <div class="chart-sub">Average gold advantage vs enemy mid laner · 0–25 minutes</div>
      <div class="chart-container">
        <canvas id="goldLeadChart"></canvas>
      </div>
      <div class="insight">
        <strong>Wins avg {signed(int(gl15_wins))}g ahead at 15 min</strong>
        vs {signed(int(gl15_loss))}g in losses.
        The gap between lines shows how much your laning phase matters to the outcome.
      </div>
    </div>

    <div class="chart-card">
      <div class="chart-title">XP Lead Over Time</div>
      <div class="chart-sub">Average XP advantage vs enemy mid laner · 0–25 minutes</div>
      <div class="chart-container">
        <canvas id="xpLeadChart"></canvas>
      </div>
      <div class="insight">
        XP lead tracks level advantage — critical for Akali whose power spikes are
        level-gated (level 6, level 9, level 11).
      </div>
    </div>
  </div>

  
  </section>

  <section class="block" id="conversion">
    <div class="eyebrow">03 · Conversion</div>
    <h2 class="block-title">How often a lead becomes a win</h2>
    <p class="block-sub">Win rate when I was ahead, even or behind at 10, 15 and 20 minutes.</p>
    <!-- Section 5: Lead Conversion Rate -->
  

  <div class="chart-grid">
    <div class="chart-card wide">
      <div class="chart-title">Lead State → Win Rate</div>
      <div class="chart-sub">When ahead, behind, or even at key timestamps — what % did you win?</div>

      <!-- Conversion table -->
      <div style="overflow-x:auto">
      <table style="width:100%; border-collapse:collapse; margin-bottom:16px">
        <thead>
          <tr>
            <th style="padding:10px 16px; text-align:left; font-size:10px; font-weight:700; letter-spacing:2px; color:var(--gold); background:var(--panel); text-transform:uppercase">State</th>
            <th style="padding:10px 16px; text-align:center; font-size:10px; font-weight:700; letter-spacing:2px; color:var(--gold); background:var(--panel); text-transform:uppercase">@ 10 min</th>
            <th style="padding:10px 16px; text-align:center; font-size:10px; font-weight:700; letter-spacing:2px; color:var(--gold); background:var(--panel); text-transform:uppercase">@ 15 min</th>
            <th style="padding:10px 16px; text-align:center; font-size:10px; font-weight:700; letter-spacing:2px; color:var(--gold); background:var(--panel); text-transform:uppercase">@ 20 min</th>
          </tr>
        </thead>
        <tbody>
          <tr style="background:var(--card)">
            <td style="padding:12px 16px; color:var(--green); font-weight:700; font-size:13px">Ahead (≥300g)</td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--green)">{conv_10["ahead"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_10["ahead"]["wins"]}/{conv_10["ahead"]["total"]} games</span></td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--green)">{conv_15["ahead"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_15["ahead"]["wins"]}/{conv_15["ahead"]["total"]} games</span></td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--green)">{conv_20["ahead"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_20["ahead"]["wins"]}/{conv_20["ahead"]["total"]} games</span></td>
          </tr>
          <tr style="background:var(--raised)">
            <td style="padding:12px 16px; color:var(--silver); font-weight:700; font-size:13px">Even (±300g)</td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--silver)">{conv_10["even"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_10["even"]["wins"]}/{conv_10["even"]["total"]} games</span></td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--silver)">{conv_15["even"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_15["even"]["wins"]}/{conv_15["even"]["total"]} games</span></td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--silver)">{conv_20["even"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_20["even"]["wins"]}/{conv_20["even"]["total"]} games</span></td>
          </tr>
          <tr style="background:var(--card)">
            <td style="padding:12px 16px; color:var(--red); font-weight:700; font-size:13px">Behind (≥300g)</td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--red)">{conv_10["behind"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_10["behind"]["wins"]}/{conv_10["behind"]["total"]} games</span></td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--red)">{conv_15["behind"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_15["behind"]["wins"]}/{conv_15["behind"]["total"]} games</span></td>
            <td style="padding:12px 16px; text-align:center; font-family:monospace; font-size:14px; font-weight:700; color:var(--red)">{conv_20["behind"]["pct"]}%<br><span style="font-size:11px; color:var(--silver); font-weight:400">{conv_20["behind"]["wins"]}/{conv_20["behind"]["total"]} games</span></td>
          </tr>
        </tbody>
      </table>
      </div>
      <div class="insight">
        The gap between "ahead at 15" and "ahead at 20" win rates tells you how much
        lead you throw between those two windows. If ahead@15 WR is high but ahead@20 is lower,
        the 15–20 minute window is where leads are being lost.
      </div>
    </div>
  </div>

  
  </section>

  <section class="block" id="deaths">
    <div class="eyebrow">04 · Deaths</div>
    <h2 class="block-title">Dying while ahead</h2>
    <p class="block-sub">Every death while holding a 300g+ lead: when it happened, and what it cost.</p>
    <!-- Section 3: Deaths While Ahead -->
  

  <div class="chart-grid">
    <div class="chart-card">
      <div class="chart-title">Deaths While Ahead — Distribution</div>
      <div class="chart-sub">When in the game do ahead-deaths occur? · By minute</div>
      <div class="chart-container">
        <canvas id="dwaChart"></canvas>
      </div>
      <div class="insight">
        Wins average <strong>{win_dwa} deaths while ahead</strong> vs
        <strong>{loss_dwa} in losses</strong>.
        {'This is a meaningful gap — dying while ahead is strongly associated with losses.' if abs(win_dwa - loss_dwa) > 0.3 else 'The gap is small — deaths while ahead may not be your primary throw mechanism.'}
      </div>
    </div>

    <div class="chart-card">
      <div class="chart-title">Deaths While Ahead — Per Game</div>
      <div class="chart-sub">Distribution across all games</div>
      <div class="chart-container">
        <canvas id="dwaHistChart"></canvas>
      </div>
      <div class="insight">
        Games with 0 deaths while ahead vs games with 1+ —
        does the distribution differ by outcome?
      </div>
    </div>
  </div>

  
    <div style="height:16px"></div>
    <!-- Throw Indicator -->
  

  <div class="chart-grid">
    <div class="chart-card">
      <div class="chart-title">Death Outcome Breakdown</div>
      <div class="chart-sub">How each ahead-death classified across {total_ahead_deaths} total deaths while leading</div>
      <div class="chart-container">
        <canvas id="throwChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Win Rate by Death Type</div>
      <div class="chart-sub">Do you tend to win or lose games where this death type occurs?</div>
      <div class="table-scroll"><table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px">
        <thead>
          <tr style="color:#aaa;border-bottom:1px solid #222">
            <th style="text-align:left;padding:6px 0">Outcome</th>
            <th style="text-align:left;padding:6px 0">Count</th>
            <th style="text-align:left;padding:6px 0">Wins</th>
            <th style="text-align:left;padding:6px 0">Losses</th>
            <th style="text-align:left;padding:6px 0">WR</th>
          </tr>
        </thead>
        <tbody>
          {throw_rows_html}
        </tbody>
      </table></div>
      <div class="insight" style="margin-top:16px">
        <strong style="color:#ff2d4e">Clean Throw</strong> = death caused both objective loss and lead collapse. 
        <strong style="color:#2ed87a">Absorbed</strong> = lead barely moved, team held.
        <strong style="color:#28d4d4">Recovered</strong> = lead dipped but stabilized.
      </div>
    </div>
  </div>

  
  </section>

  <section class="block" id="gunblade">
    <div class="eyebrow">05 · Power spike</div>
    <h2 class="block-title">The Gunblade window</h2>
    <p class="block-sub">How much lead I built in the 3 minutes after finishing Hextech Gunblade. Each dot is one game.</p>
    <!-- Section 2: Gunblade Window -->
  

  <div class="chart-grid">
    <div class="chart-card wide">
      <div class="chart-title">Gold vs XP Created in Gunblade Window</div>
      <div class="chart-sub">
        Each point = one game · Green = win · Red = loss ·
        Wins avg {signed(int(avg_gb_gold_win))}g created vs {signed(int(avg_gb_gold_loss))}g in losses
      </div>
      <div class="chart-container tall">
        <canvas id="gbScatterChart"></canvas>
      </div>
      <div class="insight">
        <strong>Wins create an average of {signed(int(avg_gb_gold_win))}g more</strong>
        than losses in the Gunblade window.
        Points in the top-right (high gold + high XP created) cluster heavily toward wins.
      </div>
    </div>
  </div>

  
  </section>

  <section class="block" id="length">
    <div class="eyebrow">06 · Game length</div>
    <h2 class="block-title">Closing games out</h2>
    <p class="block-sub">Do I win more short games or long ones?</p>
    <!-- Section 6: Game Length Distribution -->
  

  <div class="chart-grid">
    <div class="chart-card">
      <div class="chart-title">Game Count by Duration</div>
      <div class="chart-sub">How many wins vs losses fall in each game-length bucket</div>
      <div class="chart-container">
        <canvas id="gameLenChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Win Rate by Game Length</div>
      <div class="chart-sub">Does your win rate change as games get longer?</div>
      <div class="chart-container">
        <canvas id="gameLenWrChart"></canvas>
      </div>
      <div class="insight">
        Wins avg <strong>{int(avg_duration_wins)//60}:{int(avg_duration_wins)%60:02d}</strong>
        vs losses avg <strong>{int(avg_duration_losses)//60}:{int(avg_duration_losses)%60:02d}</strong>.
        {'Wins are shorter — you close out leads effectively.' if avg_duration_wins < avg_duration_losses else 'Losses are shorter — you may be getting snowballed rather than throwing leads.'}
      </div>
    </div>
  </div>


  
  </section>

  <section class="block" id="games">
    <div class="eyebrow">07 · Games</div>
    <h2 class="block-title">Recent games</h2>
    <p class="block-sub">My 50 most recent games with key stats.</p>
    <!-- Section 4: Per-game table -->
  

  <div class="table-card">
    <div class="table-header">
      <div class="chart-title">Recent Games</div>
    </div>
    <div class="table-scroll"><table>
      <thead>
        <tr>
          <th>Opponent</th>
          <th>W/L</th>
          <th>KDA</th>
          <th>Gold Lead @15</th>
          <th>GB Gold Created</th>
          <th>Deaths Ahead</th>
          <th>Duration</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table></div>
  </div>


  
  </section>

  <section class="block">
    <!-- Caveats -->
  <div style="background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 24px 28px;">
    <div class="chart-title" style="margin-bottom: 8px">Methodology &amp; caveats</div>
    <p style="color: var(--silver); font-size: 13px; line-height: 1.8;">
      This analysis is based on {total} ranked games from a single player's Akali history.
      All findings should be treated as <strong style="color: var(--white)">exploratory hypotheses</strong>
      about personal decision patterns, not generalizable claims about Akali as a champion.
      Economic differentials are measured against the enemy mid laner using position data
      from the Riot Match Timeline API (60-second snapshots). "Deaths while ahead" requires
      ≥300g gold lead at time of death.
      With a sample of {total} games, no claims of statistical significance are made.
    </p>
  </div>
  </section>

</div>

<!-- Footer -->
<footer class="footer">
  <p>Snowball · League of Legends Lead Analysis</p>
  <p style="margin-top: 4px">Built with Riot Games API · <span>{total} games analyzed</span></p>
</footer>

<!-- Charts -->
<script>
const GREEN = '#34d399';
const RED   = '#ff4d5e';
const GOLD  = '#f5b94a';
const CYAN  = '#38bdf8';
const SILVER= '#8b93a7';
const CARD  = '#12151c';

Chart.defaults.color = '#8b93a7';
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.legend.labels.padding = 16;
Chart.defaults.plugins.tooltip.backgroundColor = '#1f2430';
Chart.defaults.plugins.tooltip.borderColor = '#2f3646';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.titleFont = {{ weight: '600' }};
Chart.defaults.elements.point.radius = 0;
Chart.defaults.elements.point.hoverRadius = 5;
Chart.defaults.elements.bar.borderRadius = 6;
Chart.defaults.scale.grid.color = 'rgba(255,255,255,0.05)';

// Highlight the tab for the section in view
(function() {{
  const tabs = [...document.querySelectorAll('.tabs a')];
  const map = Object.fromEntries(tabs.map(a => [a.getAttribute('href').slice(1), a]));
  const io = new IntersectionObserver(es => es.forEach(e => {{
    if (e.isIntersecting && map[e.target.id]) {{
      tabs.forEach(t => t.classList.remove('active'));
      map[e.target.id].classList.add('active');
      // Keep the active tab visible by scrolling only the tab bar sideways (never the page)
      const bar = map[e.target.id].parentElement, t = map[e.target.id];
      if (t.offsetLeft < bar.scrollLeft || t.offsetLeft + t.offsetWidth > bar.scrollLeft + bar.clientWidth) {{
        bar.scrollTo({{ left: t.offsetLeft - 16, behavior: 'smooth' }});
      }}
    }}
  }}), {{ rootMargin: '-40% 0px -55% 0px' }});
  Object.keys(map).forEach(id => {{ const el = document.getElementById(id); if (el) io.observe(el); }});
}})();

// ── 1. Gold Lead Chart ────────────────────────────────────────────────────────
new Chart(document.getElementById('goldLeadChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(minutes)},
    datasets: [
      {{
        label: 'Wins',
        data: {json.dumps(win_curve)},
        borderColor: GREEN,
        backgroundColor: GREEN + '18',
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        borderWidth: 2,
      }},
      {{
        label: 'Losses',
        data: {json.dumps(loss_curve)},
        borderColor: RED,
        backgroundColor: RED + '18',
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        borderWidth: 2,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'top' }},
      tooltip: {{
        callbacks: {{
          label: ctx => `${{ctx.dataset.label}}: ${{ctx.parsed.y > 0 ? '+' : ''}}${{Math.round(ctx.parsed.y)}}g`
        }}
      }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Minute' }} }},
      y: {{
        title: {{ display: true, text: 'Gold Lead vs Enemy Mid' }},
        
      }}
    }}
  }}
}});

// ── 2. XP Lead Chart ─────────────────────────────────────────────────────────
new Chart(document.getElementById('xpLeadChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(minutes)},
    datasets: [
      {{
        label: 'Wins',
        data: {json.dumps(win_xp_curve)},
        borderColor: CYAN,
        backgroundColor: CYAN + '18',
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        borderWidth: 2,
      }},
      {{
        label: 'Losses',
        data: {json.dumps(loss_xp_curve)},
        borderColor: GOLD,
        backgroundColor: GOLD + '18',
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        borderWidth: 2,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Minute' }} }},
      y: {{
        title: {{ display: true, text: 'XP Lead vs Enemy Mid' }},
        
      }}
    }}
  }}
}});

// ── 3. Gunblade Scatter ───────────────────────────────────────────────────────
const gbWinData  = {json.dumps(gb_win_points)};
const gbLossData = {json.dumps(gb_loss_points)};

new Chart(document.getElementById('gbScatterChart'), {{
  type: 'scatter',
  data: {{
    datasets: [
      {{
        label: 'Win',
        data: gbWinData.map(p => ({{ x: p.x, y: p.y }})),
        backgroundColor: GREEN + 'aa',
        pointRadius: 7,
        pointHoverRadius: 10,
      }},
      {{
        label: 'Loss',
        data: gbLossData.map(p => ({{ x: p.x, y: p.y }})),
        backgroundColor: RED + 'aa',
        pointRadius: 7,
        pointHoverRadius: 10,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'top' }},
      tooltip: {{
        callbacks: {{
          label: (ctx) => {{
            const d = ctx.datasetIndex === 0
              ? gbWinData[ctx.dataIndex]
              : gbLossData[ctx.dataIndex];
            return [
              `vs ${{d.opp}} (${{d.outcome}})`,
              `Gold: ${{d.x > 0 ? '+' : ''}}${{d.x}}g`,
              `XP: ${{d.y > 0 ? '+' : ''}}${{d.y}}`,
              `CS: ${{d.cs > 0 ? '+' : ''}}${{d.cs}}`,
              `KDA: ${{d.kda}} @ ${{d.time}}`,
            ];
          }}
        }}
      }}
    }},
    scales: {{
      x: {{
        title: {{ display: true, text: 'Gold Lead Created in 3-min Gunblade Window' }},
        
      }},
      y: {{
        title: {{ display: true, text: 'XP Lead Created in 3-min Gunblade Window' }},
        
      }}
    }}
  }}
}});

// ── 4. Deaths While Ahead Distribution ───────────────────────────────────────
new Chart(document.getElementById('dwaChart'), {{
  type: 'bar',
  data: {{
    labels: Array.from({{length: 25}}, (_, i) => i),
    datasets: [
      {{
        label: 'Wins',
        data: {json.dumps(dwa_win_dist[:25])},
        backgroundColor: GREEN + '99',
        borderColor: GREEN,
        borderWidth: 1,
      }},
      {{
        label: 'Losses',
        data: {json.dumps(dwa_loss_dist[:25])},
        backgroundColor: RED + '99',
        borderColor: RED,
        borderWidth: 1,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Minute' }}, stacked: false }},
      y: {{ title: {{ display: true, text: 'Count' }}, grid: {{ color: '#1e1e2c' }} }},
    }}
  }}
}});

// ── 5. DWA Histogram ─────────────────────────────────────────────────────────
function dwaHist(games) {{
  const counts = [0,0,0,0,0];
  games.forEach(g => {{
    const n = Math.min(g.n_deaths_ahead || 0, 4);
    counts[n]++;
  }});
  return counts;
}}

const allGames = {all_games_json};
const winGames  = allGames.filter(g => g.win);
const lossGames = allGames.filter(g => !g.win);

new Chart(document.getElementById('dwaHistChart'), {{
  type: 'bar',
  data: {{
    labels: ['0', '1', '2', '3', '4+'],
    datasets: [
      {{
        label: 'Wins',
        data: dwaHist(winGames),
        backgroundColor: GREEN + '99',
        borderColor: GREEN,
        borderWidth: 1,
      }},
      {{
        label: 'Losses',
        data: dwaHist(lossGames),
        backgroundColor: RED + '99',
        borderColor: RED,
        borderWidth: 1,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Deaths While Ahead (per game)' }} }},
      y: {{ title: {{ display: true, text: 'Games' }}, grid: {{ color: '#1e1e2c' }} }},
    }}
  }}
}});

// ── Game Length Charts ────────────────────────────────────────────────────────
new Chart(document.getElementById('gameLenChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(bucket_labels)},
    datasets: [
      {{
        label: 'Wins',
        data: {json.dumps(win_len_counts)},
        backgroundColor: GREEN + '99',
        borderColor: GREEN,
        borderWidth: 1,
      }},
      {{
        label: 'Losses',
        data: {json.dumps(loss_len_counts)},
        backgroundColor: RED + '99',
        borderColor: RED,
        borderWidth: 1,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Game Duration' }} }},
      y: {{ title: {{ display: true, text: 'Games' }}, grid: {{ color: '#1e1e2c' }} }},
    }}
  }}
}});

new Chart(document.getElementById('gameLenWrChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(bucket_labels)},
    datasets: [
      {{
        label: 'Win Rate %',
        data: {json.dumps(len_wr)},
        backgroundColor: {json.dumps(len_wr)}.map(v => v >= 50 ? GREEN + 'cc' : RED + 'cc'),
        borderColor:     {json.dumps(len_wr)}.map(v => v >= 50 ? GREEN : RED),
        borderWidth: 1,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y + '%' }} }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Game Duration' }} }},
      y: {{
        min: 0, max: 100,
        title: {{ display: true, text: 'Win Rate %' }},
        
        ticks: {{ callback: v => v + '%' }}
      }},
    }}
  }}
}});


new Chart(document.getElementById('throwChart'), {{
  type: 'doughnut',
  data: {{
    labels: {throw_chart_labels},
    datasets: [{{
      data: {throw_chart_counts},
      backgroundColor: {throw_chart_colors},
      borderColor: '#0a0a0e',
      borderWidth: 3,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'right', labels: {{ color: '#aaa', font: {{ size: 12 }} }} }},
      tooltip: {{
        callbacks: {{
          label: function(ctx) {{
            const total = ctx.dataset.data.reduce((a,b) => a+b, 0);
            const pct   = total ? Math.round(ctx.parsed/total*100) : 0;
            return ctx.label + ': ' + ctx.parsed + ' (' + pct + '%)';
          }}
        }}
      }}
    }}
  }}
}});

// ── 7. Review This Moment (most recent game) ────────────────────────────────
(function() {{
  const R = {_vod_json};
  const section = document.getElementById('vod-section');
  if (!R) {{
    section.innerHTML = `<div style="background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:40px;text-align:center;color:var(--silver)">
      No games with timeline data yet. Run pipeline.py to fetch games.</div>`;
    return;
  }}
  const g = v => (v >= 0 ? '+' : '') + v.toLocaleString() + 'g';
  const col = v => v >= 0 ? 'var(--green)' : 'var(--red)';
  const tagColor = l => (l === 'Died while ahead' || l === 'Game-deciding death') ? '#ff2d4e' : (l === 'Costly death' || l === 'Lead slipped away') ? '#d4a843' : '#5b6b8c';
  const t = R.top;
  const outcome = R.win ? '✓ Won' : '✗ Lost';
  const outcomeColor = R.win ? 'var(--green)' : 'var(--red)';
  const label = s => `<div style="font-size:10px;font-weight:700;letter-spacing:2px;color:var(--silver);text-transform:uppercase;margin-bottom:6px">${{s}}</div>`;

  let html = `
  <div style="background:var(--panel);border:1px solid rgba(255,45,78,0.45);border-radius:12px;overflow:hidden;margin-bottom:16px">
    <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border)">
      <div>
        <div style="font-size:10px;font-weight:700;letter-spacing:2px;color:var(--silver);text-transform:uppercase">Most recent game · ${{R.date}} · ${{R.duration}}</div>
        <div style="font-size:16px;font-weight:800;color:var(--white);margin-top:4px">Akali vs ${{R.opponent}}</div>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font-size:12px;color:var(--silver)">${{R.kda}}</span>
        <span style="font-size:12px;font-weight:700;color:${{outcomeColor}}">${{outcome}}</span>
        <span style="background:${{tagColor(t.label)}};color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px">${{t.label}}</span>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));border-bottom:1px solid var(--border)">
      <div style="padding:18px 22px;border-right:1px solid var(--border)">${{label('Replay window')}}<div style="font-size:24px;font-weight:900;color:var(--white)">${{t.replay_start}} – ${{t.replay_end}}</div></div>
      <div style="padding:18px 22px;border-right:1px solid var(--border)">${{label('Lead at the time')}}<div style="font-size:24px;font-weight:900;color:${{col(t.lead_before)}}">${{g(t.lead_before)}}</div></div>
      ${{t.end_note
        ? `<div style="padding:18px 22px">${{label('What happened')}}<div style="font-size:24px;font-weight:900;color:var(--red)">${{t.end_note}}</div></div>`
        : `<div style="padding:18px 22px">${{label('Lead 2 min later')}}<div style="font-size:24px;font-weight:900;color:${{col(t.lead_after)}}">${{g(t.lead_after)}}</div></div>`}}
    </div>
    <div style="padding:18px 22px;font-size:14px;color:var(--white);line-height:1.55">${{t.why}}</div>
    <div style="padding:0 22px 18px;font-size:13px;color:var(--silver);line-height:1.55"><strong style="color:var(--gold)">Ask yourself:</strong> ${{t.ask}}</div>
  </div>`;

  if (R.more && R.more.length) {{
    html += `<div style="font-size:10px;font-weight:700;letter-spacing:2px;color:var(--silver);text-transform:uppercase;margin:22px 0 10px">Also worth a look in this game</div>`;
    R.more.forEach(m => {{
      html += `
      <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px 18px;margin-bottom:10px">
        <div style="display:flex;align-items:center;gap:12px">
          <span style="background:${{tagColor(m.label)}};color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px">${{m.label}}</span>
          <span style="font-size:13px;color:var(--white)">${{m.why}}</span>
        </div>
        <span style="font-size:13px;font-weight:700;color:var(--white);white-space:nowrap">▶ ${{m.replay_start}} – ${{m.replay_end}}</span>
      </div>`;
    }});
  }}
  section.innerHTML = html;
}})();

</script>

</body>
</html>"""

with open("dashboard/index.html", "w") as f:
    f.write(html)

print(f"\nDashboard built → dashboard/index.html")
print(f"Open it with:  open dashboard/index.html")
print(f"\nKey numbers:")
print(f"  Win rate:              {wr_pct}%")
print(f"  Gold lead @15 (wins):  {signed(int(gl15_wins))}g")
print(f"  Gold lead @15 (losses):{signed(int(gl15_loss))}g")
print(f"  Gunblade gold created (wins):  {signed(int(avg_gb_gold_win))}g")
print(f"  Gunblade gold created (losses):{signed(int(avg_gb_gold_loss))}g")
print(f"  Avg deaths while ahead (wins): {win_dwa}")
print(f"  Avg deaths while ahead (losses):{loss_dwa}")
