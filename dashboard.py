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

_vod_moments = []
for _g in games:
    _tl = _g.get('gold_lead_timeline', [])
    _drop = _find_lead_drop(_tl, window_mins=3)
    if _drop and _drop['peak_lead'] >= 300:
        _replay_start_s = max(0, _drop['peak_t_s'] - 30)
        _replay_end_s   = _drop['trough_t_s'] + 30
        _drop_val = _drop['drop']
        _vod_moments.append({
            'opponent':     _g.get('opponent', '?'),
            'win':          _g['win'],
            'kda':          _g.get('kda', ''),
            'peak_t':       _fmt_ts(_drop['peak_t_s']),
            'trough_t':     _fmt_ts(_drop['trough_t_s']),
            'peak_lead':    _drop['peak_lead'],
            'trough_lead':  _drop['trough_lead'],
            'drop':         _drop_val,
            'replay_start': _fmt_ts(_replay_start_s),
            'replay_end':   _fmt_ts(_replay_end_s),
            'label':        'Major lead loss' if _drop_val >= 1000 else 'Lead loss',
            'label_color':  '#ff2d4e' if _drop_val >= 1000 else '#d4a843',
        })

_vod_moments.sort(key=lambda m: m['drop'], reverse=True)
_vod_moments = _vod_moments[:10]
_vod_json = json.dumps(_vod_moments)
print(f"VOD moments computed — {len(_vod_moments)} review moments found")


html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Snowball: Do Early Leads Win Games?</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>


<style>
  :root {{
    --void:   #050507;
    --base:   #0a0a0e;
    --panel:  #0f0f15;
    --card:   #14141c;
    --raised: #1a1a24;
    --red:    #ff2d4e;
    --gold:   #d4a843;
    --silver: #8090a8;
    --smoke:  #404858;
    --white:  #f4f4fc;
    --off:    #c8c8dc;
    --green:  #2ed87a;
    --orange: #f07832;
    --cyan:   #28d4d4;
    --border: #1e1e2c;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--base);
    color: var(--white);
    font-family: 'Segoe UI', -apple-system, sans-serif;
    font-size: 14px;
    line-height: 1.6;
  }}

  /* ── Header ── */
  .header {{
    background: var(--void);
    border-bottom: 2px solid var(--red);
    padding: 0;
  }}
  .header-inner {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 32px;
    height: 72px;
    display: flex;
    align-items: center;
    gap: 20px;
  }}
  .logo {{
    font-size: 28px;
    font-weight: 900;
    letter-spacing: -1px;
  }}
  .logo span {{ color: var(--red); }}
  .tagline {{
    color: var(--silver);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
  }}
  .header-right {{
    margin-left: auto;
    text-align: right;
  }}
  .header-right .wr {{
    font-size: 20px;
    font-weight: 800;
    color: var(--gold);
  }}
  .header-right .sub {{
    font-size: 11px;
    color: var(--silver);
  }}

  /* ── Layout ── */
  .container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 40px 32px;
  }}

  .section-title {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 8px;
  }}
  .section-desc {{
    font-size: 13px;
    color: var(--silver);
    margin-bottom: 24px;
    max-width: 600px;
  }}

  /* ── Stat pills ── */
  .pills {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 40px;
  }}
  .pill {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 24px;
    min-width: 140px;
  }}
  .pill-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    color: var(--silver);
    text-transform: uppercase;
    margin-bottom: 6px;
  }}
  .pill-value {{
    font-size: 26px;
    font-weight: 900;
    line-height: 1;
  }}
  .pill-sub {{
    font-size: 11px;
    color: var(--smoke);
    margin-top: 4px;
  }}
  .green {{ color: var(--green); }}
  .red   {{ color: var(--red);   }}
  .gold  {{ color: var(--gold);  }}
  .cyan  {{ color: var(--cyan);  }}
  .white {{ color: var(--white); }}

  /* ── Chart cards ── */
  .chart-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 40px;
  }}
  .chart-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
  }}
  .chart-card.wide {{
    grid-column: 1 / -1;
  }}
  .chart-title {{
    font-size: 14px;
    font-weight: 700;
    color: var(--white);
    margin-bottom: 4px;
  }}
  .chart-sub {{
    font-size: 12px;
    color: var(--silver);
    margin-bottom: 20px;
  }}
  .chart-container {{
    position: relative;
    height: 280px;
  }}
  .chart-container.tall {{
    height: 360px;
  }}

  /* ── Insight callouts ── */
  .insight {{
    background: var(--raised);
    border-left: 3px solid var(--red);
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
    margin-top: 16px;
    font-size: 13px;
    color: var(--off);
  }}
  .insight strong {{ color: var(--white); }}

  /* ── Table ── */
  .table-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 40px;
  }}
  .table-header {{
    padding: 20px 24px 12px;
    border-bottom: 1px solid var(--border);
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
  }}
  th {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--gold);
    padding: 10px 16px;
    text-align: left;
    background: var(--panel);
  }}
  td {{
    padding: 10px 16px;
    border-top: 1px solid var(--border);
    font-size: 13px;
    color: var(--off);
    font-family: 'Courier New', monospace;
  }}
  tr:hover td {{ background: var(--raised); }}
  .win-badge  {{ color: var(--green); font-weight: 700; }}
  .loss-badge {{ color: var(--red);   font-weight: 700; }}

  /* ── Section divider ── */
  .divider {{
    height: 1px;
    background: var(--border);
    margin: 48px 0;
  }}

  /* ── Footer ── */
  .footer {{
    text-align: center;
    padding: 40px;
    color: var(--smoke);
    font-size: 12px;
    border-top: 1px solid var(--border);
  }}
  .footer span {{ color: var(--silver); }}
</style>
</head>
<body>

<!-- Header -->
<header class="header">
  <div class="header-inner">
    <div class="logo">SNOW<span>BALL</span></div>
    <div class="tagline">Do early leads in League actually win games?</div>
    <div class="header-right">
      <div class="wr">{wr_pct}% WR</div>
      <div class="sub">{total} Akali games · Ranked Solo/Duo</div>
    </div>
  </div>
</header>

<div class="container">

  <!-- Summary pills -->
  <div style="margin-bottom: 12px">
    <div class="section-title">Overview</div>
    <div class="section-desc">
      Exploratory analysis of {total} ranked Akali games.
      Findings are hypotheses about personal decision patterns, not generalizable conclusions.
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

  <div class="divider"></div>

  <!-- Section 1: Lead Decay Curves -->
  <div class="section-title">01 — Lead Decay Curve</div>
  <div class="section-desc">
    Average gold and XP lead over the enemy mid laner, split by game outcome.
    The divergence point reveals when leads are created — or lost.
  </div>

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

  <div class="divider"></div>

  <!-- Section 2: Gunblade Window -->
  <div class="section-title">02 — Gunblade Spike Window</div>
  <div class="section-desc">
    How much economic lead did you create vs the enemy mid laner
    in the 3 minutes after completing Hextech Gunblade?
    Each dot is one game.
  </div>

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

  <div class="divider"></div>

  <!-- Section 3: Deaths While Ahead -->
  <div class="section-title">03 — Deaths While Ahead</div>
  <div class="section-desc">
    How many times did you die while holding a gold lead (≥300g)?
    This is the "throwing leads" detector.
  </div>

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

  <div class="divider"></div>

  <!-- Section 4: Per-game table -->
  <div class="section-title">04 — Game Log</div>
  <div class="section-desc">Most recent 50 games with key metrics.</div>

  <div class="table-card">
    <div class="table-header">
      <div class="chart-title">Recent Games</div>
    </div>
    <table>
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
    </table>
  </div>


  <div class="divider"></div>

  <!-- Section 5: Lead Conversion Rate -->
  <div class="section-title">05 — Lead Conversion Rate</div>
  <div class="section-desc">
    Of the games where you were ahead/even/behind at 10, 15, and 20 minutes —
    how often did you convert that state into a win?
    This directly answers the core question.
  </div>

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

  <div class="divider"></div>

  <!-- Section 6: Game Length Distribution -->
  <div class="section-title">06 — Game Length Distribution</div>
  <div class="section-desc">
    Do you win more short games or long games?
    Akali is a snowball champion — this reveals whether you close out leads or let games drag.
    Average game length: wins {int(avg_duration_wins)//60}:{int(avg_duration_wins)%60:02d} · losses {int(avg_duration_losses)//60}:{int(avg_duration_losses)%60:02d}
  </div>

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


  <!-- Throw Indicator -->
  <div class="section-header">
    <div class="section-title">THROW INDICATOR</div>
    <div class="section-sub">What happened after each death while ahead — did it matter?</div>
  </div>

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
      <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px">
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
      </table>
      <div class="insight" style="margin-top:16px">
        <strong style="color:#ff2d4e">Clean Throw</strong> = death caused both objective loss and lead collapse. 
        <strong style="color:#2ed87a">Absorbed</strong> = lead barely moved, team held.
        <strong style="color:#28d4d4">Recovered</strong> = lead dipped but stabilized.
      </div>
    </div>
  </div>

  <div class="divider"></div>

  <!-- Section 7: VOD Review -->
  <div class="section-header">
    <div class="section-title">Priority Review Moments</div>
    <div class="section-sub">Games where your gold lead dropped the most — sorted by severity. Jump to the replay window to review what went wrong.</div>
  </div>
  <div id="vod-section">
  </div>

  <div class="divider"></div>

  <!-- Caveats -->
  <div style="background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-bottom: 40px;">
    <div class="section-title" style="margin-bottom: 12px">Methodology & Caveats</div>
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

</div>

<!-- Footer -->
<footer class="footer">
  <p>Snowball · League of Legends Lead Analysis</p>
  <p style="margin-top: 4px">Built with Riot Games API · <span>{total} games analyzed</span></p>
</footer>

<!-- Charts -->
<script>
const GREEN = '#2ed87a';
const RED   = '#ff2d4e';
const GOLD  = '#d4a843';
const CYAN  = '#28d4d4';
const SILVER= '#8090a8';
const CARD  = '#14141c';

Chart.defaults.color = '#8090a8';
Chart.defaults.borderColor = '#1e1e2c';
Chart.defaults.font.family = "'Segoe UI', -apple-system, sans-serif";

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
        grid: {{ color: '#1e1e2c' }},
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
        grid: {{ color: '#1e1e2c' }},
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
        grid: {{ color: '#1e1e2c' }},
      }},
      y: {{
        title: {{ display: true, text: 'XP Lead Created in 3-min Gunblade Window' }},
        grid: {{ color: '#1e1e2c' }},
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
        grid: {{ color: '#1e1e2c' }},
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

// ── 7. VOD Review ────────────────────────────────────────────────────────────
(function() {{
  const MOMENTS = {_vod_json};
  const section = document.getElementById('vod-section');

  if (!MOMENTS || MOMENTS.length === 0) {{
    section.innerHTML = `
      <div style="background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:40px;text-align:center;color:var(--silver)">
        <div style="font-size:32px;margin-bottom:12px">📹</div>
        <div style="font-size:14px;font-weight:700;color:var(--white);margin-bottom:8px">No review moments found</div>
        <div style="font-size:13px">Need games with gold lead data. Re-run pipeline.py to fetch more games.</div>
      </div>`;
    return;
  }}

  function fmtGold(n) {{
    const sign = n >= 0 ? '+' : '';
    return sign + n.toLocaleString() + 'g';
  }}

  let html = '';
  MOMENTS.forEach((m, i) => {{
    const rank = i + 1;
    const changeAmt = m.trough_lead - m.peak_lead;
    const changeStr = changeAmt.toLocaleString() + 'g';
    const peakColor   = m.peak_lead   >= 0 ? 'var(--green)' : 'var(--red)';
    const troughColor = m.trough_lead >= 0 ? 'var(--green)' : 'var(--red)';
    const outcome      = m.win ? '✓ Won' : '✗ Lost';
    const outcomeColor = m.win ? 'var(--green)' : 'var(--red)';
    const isTop = rank === 1;

    html += `
    <div style="background:var(--panel);border:1px solid ${{isTop ? 'rgba(255,45,78,0.4)' : 'var(--border)'}};border-radius:12px;
                margin-bottom:16px;overflow:hidden">
      <div style="display:flex;align-items:center;justify-content:space-between;
                  padding:16px 20px;border-bottom:1px solid var(--border)">
        <div style="font-size:15px;font-weight:800;color:var(--white)">
          #${{rank}} — Akali vs ${{m.opponent}}
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <span style="font-size:11px;color:var(--silver)">${{m.kda}}</span>
          <span style="font-size:12px;font-weight:700;color:${{outcomeColor}}">${{outcome}}</span>
          <span style="background:${{m.label_color}};color:#fff;font-size:11px;font-weight:700;
                       padding:3px 10px;border-radius:20px">${{m.label}}</span>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--border)">
        <div style="padding:20px 24px;border-right:1px solid var(--border)">
          <div style="font-size:10px;font-weight:700;letter-spacing:2px;color:var(--silver);
                      text-transform:uppercase;margin-bottom:8px">GOLD LEAD · ${{m.peak_t}}</div>
          <div style="font-size:28px;font-weight:900;color:${{peakColor}}">${{fmtGold(m.peak_lead)}}</div>
        </div>
        <div style="padding:20px 24px">
          <div style="font-size:10px;font-weight:700;letter-spacing:2px;color:var(--silver);
                      text-transform:uppercase;margin-bottom:8px">GOLD LEAD · ${{m.trough_t}}</div>
          <div style="font-size:28px;font-weight:900;color:${{troughColor}}">${{fmtGold(m.trough_lead)}}</div>
        </div>
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;
                  padding:16px 24px;border-bottom:1px solid var(--border)">
        <div>
          <div style="font-size:10px;font-weight:700;letter-spacing:2px;color:var(--silver);
                      text-transform:uppercase;margin-bottom:4px">LEAD CHANGE</div>
          <div style="font-size:20px;font-weight:900;color:var(--red)">${{changeStr}}</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:10px;font-weight:700;letter-spacing:2px;color:var(--silver);
                      text-transform:uppercase;margin-bottom:4px">REPLAY WINDOW</div>
          <div style="font-size:18px;font-weight:700;color:var(--white)">${{m.replay_start}} – ${{m.replay_end}}</div>
        </div>
      </div>
      <div style="padding:14px 24px;font-size:13px;color:var(--silver);line-height:1.5">
        Review: What happened before the decline? Was there a death, missed wave, bad rotation, or enemy play that explains the swing?
      </div>
    </div>`;
  }});

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
