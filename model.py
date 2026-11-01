"""
Snowball — Win Probability Model
Trains a logistic regression on 15-minute game state to predict win probability.

Run AFTER pipeline.py:
    python3 model.py

Output:
    models/win_probability.joblib  — trained sklearn Pipeline (scaler + LR)
    models/model_params.json       — exported params for browser inference
"""

import json
import os
import math
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    log_loss, roc_auc_score, brier_score_loss, accuracy_score
)

os.makedirs("models", exist_ok=True)

# ── Feature definition ────────────────────────────────────────────────────────
# Order matters — must be consistent between training and inference
FEATURES = [
    "cs_lead_15",
]

FEATURE_LABELS = {
    "gold_lead_15":  "Gold Lead vs Mid",
    "xp_lead_15":    "XP Lead vs Mid",
    "cs_lead_15":    "CS Lead vs Mid",
    "kills_15":      "My Kills",
    "deaths_15":     "My Deaths",
    "assists_15":    "My Assists",
    "em_kills_15":   "Enemy Mid Kills",
    "em_deaths_15":  "Enemy Mid Deaths",
}


def load_data(path="data/processed.json"):
    with open(path) as f:
        games = json.load(f)

    rows = []
    for g in games:
        m = g.get("ml15")
        if m is None:
            continue  # game < 15 min or missing enemy mid — skip silently
        rows.append({
            **{feat: m.get(feat, 0) for feat in FEATURES},
            "win": int(g["win"]),
            "game_timestamp": g.get("game_timestamp", 0),
        })

    # Preserve chronological order (pipeline already sorted, but be explicit)
    rows.sort(key=lambda r: r["game_timestamp"])
    return rows


def build_matrices(rows):
    X = np.array([[r[f] for f in FEATURES] for r in rows], dtype=float)
    y = np.array([r["win"] for r in rows], dtype=int)
    return X, y


def evaluate(name, y_true, y_pred_proba, y_pred_class, base_rate):
    """Return dict of metrics with human-readable explanations."""
    both_classes = len(set(y_true)) == 2
    ll   = log_loss(y_true, y_pred_proba)
    bs   = brier_score_loss(y_true, y_pred_proba)
    acc  = accuracy_score(y_true, y_pred_class)
    auc  = roc_auc_score(y_true, y_pred_proba) if both_classes else None
    base_ll = log_loss(y_true, [base_rate] * len(y_true))
    return {
        "name":        name,
        "n":           len(y_true),
        "log_loss":    round(ll, 4),
        "base_log_loss": round(base_ll, 4),
        "ll_improvement": round(base_ll - ll, 4),
        "brier_score": round(bs, 4),
        "accuracy":    round(acc, 4),
        "roc_auc":     round(auc, 4) if auc is not None else None,
    }


def chronological_split(X, y, test_frac=0.2):
    """
    Hold out the most recent test_frac of games as the test set.
    Games are already sorted oldest→newest.
    """
    n_test  = max(1, int(len(X) * test_frac))
    n_train = len(X) - n_test
    return X[:n_train], X[n_train:], y[:n_train], y[n_train:]


def train_and_evaluate(rows):
    if len(rows) < 20:
        raise ValueError(
            f"Only {len(rows)} games with 15-min data — need at least 20 to train."
        )

    X, y = build_matrices(rows)
    base_rate = y.mean()

    print(f"\n{'='*60}")
    print(f"  Dataset: {len(rows)} games with 15-min features")
    print(f"  Win rate: {base_rate:.1%}  ({y.sum()} wins / {(1-y).sum().astype(int)} losses)")
    print(f"  Chronological split: 80% train / 20% test")
    print(f"{'='*60}")

    X_tr, X_te, y_tr, y_te = chronological_split(X, y)
    train_base = y_tr.mean()

    # ── Model A: constant-probability baseline ────────────────────────────────
    base_proba_tr = np.full(len(y_tr), train_base)
    base_proba_te = np.full(len(y_te), train_base)
    base_class_te = np.round(base_proba_te).astype(int)
    metrics_base = evaluate(
        "Baseline (constant train WR)", y_te, base_proba_te, base_class_te, train_base
    )

    # ── Model B: CS-only logistic regression ─────────────────────────────────
    cs_idx = FEATURES.index("cs_lead_15")
    pipe_gold = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")),
    ])
    pipe_gold.fit(X_tr[:, [cs_idx]], y_tr)
    gp_te = pipe_gold.predict_proba(X_te[:, [cs_idx]])[:, 1]
    gc_te = pipe_gold.predict(X_te[:, [cs_idx]])
    metrics_gold = evaluate("CS-only LR", y_te, gp_te, gc_te, train_base)

    # ── Model C: full logistic regression ────────────────────────────────────
    pipe_full = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")),
    ])
    pipe_full.fit(X_tr, y_tr)
    fp_te = pipe_full.predict_proba(X_te)[:, 1]
    fc_te = pipe_full.predict(X_te)
    metrics_full = evaluate("Full LR (all features)", y_te, fp_te, fc_te, train_base)

    # ── Re-fit full model on ALL data for deployment ─────────────────────────
    pipe_deploy = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")),
    ])
    pipe_deploy.fit(X, y)

    # ── Coefficients ──────────────────────────────────────────────────────────
    scaler = pipe_deploy.named_steps["scaler"]
    lr     = pipe_deploy.named_steps["lr"]
    coefs  = lr.coef_[0].tolist()
    stds   = scaler.scale_.tolist()
    means  = scaler.mean_.tolist()

    # Standardized coefficients = coef * std  (effect of 1-std-unit change on log-odds)
    std_coefs = [c * s for c, s in zip(coefs, stds)]

    # ── Calibration (test set, binned) ────────────────────────────────────────
    calibration = None
    if len(y_te) >= 20:
        bins = np.linspace(0, 1, 6)
        cal_data = []
        for lo, hi in zip(bins[:-1], bins[1:]):
            mask = (fp_te >= lo) & (fp_te < hi)
            if mask.sum() >= 3:
                cal_data.append({
                    "bin_mid":    round((lo + hi) / 2, 2),
                    "pred_mean":  round(float(fp_te[mask].mean()), 3),
                    "actual_wr":  round(float(y_te[mask].mean()), 3),
                    "n":          int(mask.sum()),
                })
        calibration = cal_data

    # ── Print results ─────────────────────────────────────────────────────────
    print("\nEVALUATION RESULTS (test set — most recent 20% of games)")
    print(f"{'Model':<30} {'LogLoss':>8} {'Brier':>7} {'AUC':>7} {'Acc':>7}")
    print("-" * 62)
    for m in [metrics_base, metrics_gold, metrics_full]:
        auc_str = f"{m['roc_auc']:.4f}" if m["roc_auc"] is not None else "  n/a "
        print(f"{m['name']:<30} {m['log_loss']:>8.4f} {m['brier_score']:>7.4f} "
              f"{auc_str:>7} {m['accuracy']:>7.4f}")

    print("\nCOEFFICIENTS (full model, trained on all data)")
    print(f"  {'Feature':<20} {'Raw coef':>10} {'Std coef':>10}  Interpretation")
    print("  " + "-" * 70)
    for feat, raw, std_c in zip(FEATURES, coefs, std_coefs):
        direction = "↑ win" if std_c > 0 else "↓ win"
        print(f"  {FEATURE_LABELS[feat]:<20} {raw:>10.4f} {std_c:>10.4f}  {direction}")
    print(f"  {'Intercept':<20} {lr.intercept_[0]:>10.4f}")

    return {
        "pipe_deploy":   pipe_deploy,
        "metrics_base":  metrics_base,
        "metrics_gold":  metrics_gold,
        "metrics_full":  metrics_full,
        "coefs":         coefs,
        "std_coefs":     std_coefs,
        "means":         means,
        "stds":          stds,
        "intercept":     float(lr.intercept_[0]),
        "base_rate":     float(base_rate),
        "n_games":       len(rows),
        "n_train":       len(X_tr),
        "n_test":        len(X_te),
        "calibration":   calibration,
    }


def export_browser_params(result, path="models/model_params.json"):
    """
    Export scaler + LR params as JSON so the static dashboard can run inference
    in the browser without any Python dependency.
    Browser formula:
        z_i = (x_i - mean_i) / std_i
        logit = intercept + sum(coef_i * z_i)
        prob  = 1 / (1 + exp(-logit))
    """
    params = {
        "features":   FEATURES,
        "labels":     FEATURE_LABELS,
        "means":      result["means"],
        "stds":       result["stds"],
        "coefs":      result["coefs"],
        "intercept":  result["intercept"],
        "base_rate":  result["base_rate"],
        "n_games":    result["n_games"],
        "n_train":    result["n_train"],
        "n_test":     result["n_test"],
        "std_coefs":  result["std_coefs"],
        "calibration": result["calibration"],
        "metrics": {
            "baseline": result["metrics_base"],
            "gold_only": result["metrics_gold"],
            "full": result["metrics_full"],
        },
    }
    with open(path, "w") as f:
        json.dump(params, f, indent=2)
    print(f"\nBrowser params exported → {path}")

    # Sanity-check: verify browser formula matches sklearn on a sample
    pipe  = result["pipe_deploy"]
    means = np.array(result["means"])
    stds  = np.array(result["stds"])
    coefs = np.array(result["coefs"])
    intcp = result["intercept"]

    sample = np.zeros((1, len(FEATURES)))
    sk_prob   = pipe.predict_proba(sample)[0, 1]
    z         = (sample[0] - means) / stds
    logit     = intcp + np.dot(coefs, z)
    browser_prob = 1 / (1 + math.exp(-logit))
    diff = abs(sk_prob - browser_prob)
    print(f"Browser vs sklearn check — sklearn: {sk_prob:.6f}  browser: {browser_prob:.6f}  diff: {diff:.2e}")
    assert diff < 1e-6, "Browser params do not match sklearn — check export logic"
    print("✓ Browser inference matches sklearn exactly")


def predict_win_prob(game_state: dict, params_path="models/model_params.json") -> float:
    """
    Reusable prediction function.
    game_state: dict with keys from FEATURES, e.g.
        {"gold_lead_15": 800, "xp_lead_15": 200, "cs_lead_15": 5, ...}
    Returns win probability as float 0–1.
    """
    with open(params_path) as f:
        params = json.load(f)
    means = params["means"]
    stds  = params["stds"]
    coefs = params["coefs"]
    intcp = params["intercept"]
    feats = params["features"]
    z = [(game_state.get(feat, 0) - means[i]) / stds[i]
         for i, feat in enumerate(feats)]
    logit = intcp + sum(c * zi for c, zi in zip(coefs, z))
    return 1 / (1 + math.exp(-logit))


def main():
    print("Loading data/processed.json ...")
    rows = load_data()
    print(f"Found {len(rows)} games with valid 15-min features")

    if len(rows) == 0:
        print("\nNo 15-min features found in processed.json.")
        print("Re-run pipeline.py to generate them, then run model.py again.")
        return

    result = train_and_evaluate(rows)

    # Save sklearn pipeline
    joblib.dump(result["pipe_deploy"], "models/win_probability.joblib")
    print("\nModel saved → models/win_probability.joblib")

    # Export browser params
    export_browser_params(result)

    print("\nDone. Run python3 dashboard.py to regenerate the dashboard.")


if __name__ == "__main__":
    main()
