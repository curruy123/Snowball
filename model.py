"""
Snowball — Win Probability Model
Predicts win probability from the game state at 15 minutes.
Compares a baseline, two logistic regressions and a random forest,
using a time-ordered train/test split plus time-series cross-validation.

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
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    log_loss, roc_auc_score, brier_score_loss, accuracy_score
)

os.makedirs("models", exist_ok=True)

# ── Feature definition ────────────────────────────────────────────────────────
# Order matters — must be consistent between training and inference
FEATURES = [
    "gold_lead_15",
    "xp_lead_15",
    "cs_lead_15",
    "kills_15",
    "deaths_15",
    "assists_15",
    "em_kills_15",
    "em_deaths_15",
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


class _ColumnModel:
    """Fits a model on a subset of columns (used to cross-validate the gold-only model)."""
    def __init__(self, model, cols):
        self.model, self.cols = model, cols
    def fit(self, X, y):
        self.model.fit(X[:, self.cols], y); return self
    def predict_proba(self, X):
        return self.model.predict_proba(X[:, self.cols])


def make_lr():
    return Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")),
    ])


def make_rf():
    # Shallow trees + a minimum leaf size keep the forest from memorizing a small dataset
    return RandomForestClassifier(
        n_estimators=400, max_depth=4, min_samples_leaf=5,
        class_weight="balanced", random_state=42, n_jobs=-1,
    )


def time_series_cv_auc(make_model, X, y, n_splits=5):
    """
    Average AUC across expanding time-ordered folds (always train on older games,
    test on newer ones). More stable than a single split when data is small.
    """
    scores = []
    for tr, te in TimeSeriesSplit(n_splits=n_splits).split(X):
        if len(set(y[te])) < 2 or len(set(y[tr])) < 2:
            continue
        m = make_model()
        m.fit(X[tr], y[tr])
        scores.append(roc_auc_score(y[te], m.predict_proba(X[te])[:, 1]))
    if not scores:
        return None
    return {"mean": round(float(np.mean(scores)), 4), "std": round(float(np.std(scores)), 4), "folds": len(scores)}


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

    # ── Model B: gold-lead-only logistic regression ──────────────────────────
    g_idx = FEATURES.index("gold_lead_15")
    pipe_gold = make_lr()
    pipe_gold.fit(X_tr[:, [g_idx]], y_tr)
    gp_te = pipe_gold.predict_proba(X_te[:, [g_idx]])[:, 1]
    gc_te = pipe_gold.predict(X_te[:, [g_idx]])
    metrics_gold = evaluate("Gold-lead-only LR", y_te, gp_te, gc_te, train_base)

    # ── Model C: full logistic regression (all features) ─────────────────────
    pipe_full = make_lr()
    pipe_full.fit(X_tr, y_tr)
    fp_te = pipe_full.predict_proba(X_te)[:, 1]
    fc_te = pipe_full.predict(X_te)
    metrics_full = evaluate("Full LR (all features)", y_te, fp_te, fc_te, train_base)

    # ── Model D: random forest (all features) ────────────────────────────────
    rf = make_rf()
    rf.fit(X_tr, y_tr)
    rp_te = rf.predict_proba(X_te)[:, 1]
    rc_te = rf.predict(X_te)
    metrics_rf = evaluate("Random forest", y_te, rp_te, rc_te, train_base)

    # ── Time-series cross-validation (more reliable on small data) ───────────
    cv = {
        "gold_only":     time_series_cv_auc(lambda: _ColumnModel(make_lr(), [g_idx]), X, y),
        "full":          time_series_cv_auc(make_lr, X, y),
        "random_forest": time_series_cv_auc(make_rf, X, y),
    }

    # ── Re-fit models on ALL data for deployment ─────────────────────────────
    pipe_deploy = make_lr()
    pipe_deploy.fit(X, y)
    rf_deploy = make_rf()
    rf_deploy.fit(X, y)
    rf_importance = sorted(
        zip(FEATURES, rf_deploy.feature_importances_.tolist()),
        key=lambda t: t[1], reverse=True,
    )

    # ── Coefficients ──────────────────────────────────────────────────────────
    scaler = pipe_deploy.named_steps["scaler"]
    lr     = pipe_deploy.named_steps["lr"]
    coefs  = lr.coef_[0].tolist()
    stds   = scaler.scale_.tolist()
    means  = scaler.mean_.tolist()

    # The pipeline standardizes inputs first, so lr.coef_ is already the effect of a
    # 1-standard-deviation change on the log-odds of winning (comparable across features).
    std_coefs = list(coefs)
    # Effect of a 1-unit change (e.g. +1 gold, +1 kill) in the original units
    unit_coefs = [c / s for c, s in zip(coefs, stds)]

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
    for m in [metrics_base, metrics_gold, metrics_full, metrics_rf]:
        auc_str = f"{m['roc_auc']:.4f}" if m["roc_auc"] is not None else "  n/a "
        print(f"{m['name']:<30} {m['log_loss']:>8.4f} {m['brier_score']:>7.4f} "
              f"{auc_str:>7} {m['accuracy']:>7.4f}")

    print("\nTIME-SERIES CROSS-VALIDATION (mean AUC across folds, 0.50 = coin flip)")
    for key, label in [("gold_only", "Gold-lead-only LR"), ("full", "Full LR"), ("random_forest", "Random forest")]:
        c = cv[key]
        print(f"  {label:<28} {c['mean']:.4f} ± {c['std']:.4f}  ({c['folds']} folds)" if c else f"  {label:<28} n/a")

    print("\nRANDOM FOREST FEATURE IMPORTANCE")
    for feat, imp in rf_importance:
        print(f"  {FEATURE_LABELS[feat]:<20} {imp:>6.3f}  {'█' * int(round(imp * 40))}")

    print("\nCOEFFICIENTS (full model, trained on all data)")
    print(f"  {'Feature':<20} {'Per 1 SD':>10} {'Per unit':>12}  Direction")
    print("  " + "-" * 70)
    for feat, std_c, unit_c in zip(FEATURES, std_coefs, unit_coefs):
        direction = "↑ win" if std_c > 0 else "↓ win"
        print(f"  {FEATURE_LABELS[feat]:<20} {std_c:>10.4f} {unit_c:>12.6f}  {direction}")
    print("  (Gold, XP and CS leads move together, so their individual signs can flip;")
    print("   read them as a group, and use the random forest importance for ranking.)")
    print(f"  {'Intercept':<20} {lr.intercept_[0]:>10.4f}")

    return {
        "pipe_deploy":   pipe_deploy,
        "metrics_base":  metrics_base,
        "metrics_gold":  metrics_gold,
        "metrics_full":  metrics_full,
        "metrics_rf":    metrics_rf,
        "cv_auc":        cv,
        "rf_deploy":     rf_deploy,
        "rf_importance": rf_importance,
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
            "random_forest": result["metrics_rf"],
        },
        "cv_auc": result["cv_auc"],
        "rf_feature_importance": [
            {"feature": f, "label": FEATURE_LABELS[f], "importance": round(i, 4)}
            for f, i in result["rf_importance"]
        ],
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
    joblib.dump(result["rf_deploy"], "models/random_forest.joblib")
    print("\nModels saved → models/win_probability.joblib, models/random_forest.joblib")

    # Export browser params
    export_browser_params(result)

    print("\nDone. Run python3 dashboard.py to regenerate the dashboard.")


if __name__ == "__main__":
    main()
