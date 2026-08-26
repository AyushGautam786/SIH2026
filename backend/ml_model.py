"""
ml_model.py — 3-class Random Forest classifier: healthy / transient_spike / at_risk.

For the prototype we train on synthetic data shaped to match the simulator's
scenarios (fast to demo, no dataset to ship). The feature contract below is
what matters for the upgrade path — point this same function at real
Prometheus/cAdvisor history later and nothing else in the pipeline changes.

Feature vector (fixed order — PPTX slides 10/13):
    cpu           latest CPU %
    mem           latest memory %
    net           latest aggregate network load %
    cpu_avg_1m    rolling mean CPU over ~1 minute (20 ticks @3s)
                  -> separates bursts (low avg) from sustained load (high avg)
    cpu_avg_5m    rolling mean CPU over ~5 minutes (up to 100 ticks)
                  -> exposes slow ramps toward failure
    mem_delta_30s memory change over ~30 s -> leak detection (monotonic rise)
    net_std_1m    std-dev of network over ~1 minute -> erratic traffic spikes
    cpu_mem_ratio CPU/MEM imbalance -> CPU maxed while RAM idle anomalies

Predictive labelling strategy (PPTX slide 13): training samples drawn from the
window immediately preceding a simulated crash are labelled `at_risk`, so the
model learns failure *precursors* — proactive remediation, not reactive.

The trained forest is persisted to models/rf_model.joblib (joblib) so startup
loads it instead of retraining; delete the file to force a retrain.
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

CLASSES = ["healthy", "transient_spike", "at_risk"]
FEATURE_NAMES = [
    "cpu", "mem", "net",
    "cpu_avg_1m", "cpu_avg_5m",
    "mem_delta_30s", "net_std_1m",
    "cpu_mem_ratio",
]

MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "rf_model.joblib"

TICK_SECONDS = 3          # must match simulator cadence
AVG_1M_TICKS = 20         # ~60 s @ 3 s/tick
AVG_5M_TICKS = 100        # ~300 s @ 3 s/tick
DELTA_30S_TICKS = 10      # ~30 s
STD_1M_TICKS = 20


def extract_features(history: list[dict]) -> np.ndarray:
    """Turn a container's recent metric history into the model's feature row.

    Pure numpy (hot path — called once per container per tick fleet-wide);
    pandas is used upstream in the dataset builder where convenience beats
    microsecond latency."""
    if not history:
        return np.array([[0.0] * len(FEATURE_NAMES)])

    arr = np.asarray(
        [
            [
                float(h.get("cpu", 0.0)),
                float(h.get("mem", 0.0)),
                float(h.get("net", 0.0)),
            ]
            for h in history
        ],
        dtype=float,
    )
    cpu, mem, net = arr[:, 0], arr[:, 1], arr[:, 2]
    n = len(arr)
    row = [
        cpu[-1],
        mem[-1],
        net[-1],
        cpu[-AVG_1M_TICKS:].mean(),
        cpu[-AVG_5M_TICKS:].mean(),
        mem[-1] - mem[-min(DELTA_30S_TICKS, n)],
        net[-STD_1M_TICKS:].std(),
        cpu[-1] / max(1.0, mem[-1]),
    ]
    return np.array([row])


def predict_batch(histories: list[list[dict]]) -> list[tuple[str, float]]:
    """Classify many containers in ONE forest pass (fleet-scale hot path).

    Feature extraction stays per-container; the model call is batched so a
    300+ container fleet costs one predict() invocation per tick."""
    if not histories:
        return []
    X = np.vstack([extract_features(h) for h in histories])
    preds = MODEL.predict(X)
    probas = MODEL.predict_proba(X)
    return [
        (CLASSES[int(p)], float(probas[i][p]))
        for i, p in enumerate(preds)
    ]



def _features_from_series(rng, n, cpu_mu, cpu_sd, mem_mu, mem_sd, net_mu,
                          net_sd, avg1m_bias=0.0, mem_slope=0.0):
    """Generate `n` correlated raw series and engineer features from them."""
    length = AVG_5M_TICKS + 8   # enough runway for all rolling windows
    rows = []
    for _ in range(n):
        cpu = rng.normal(cpu_mu, cpu_sd, length).clip(0, 100)
        mem = (rng.normal(mem_mu, mem_sd, length).clip(0, 100)
               + np.linspace(0.0, mem_slope * DELTA_30S_TICKS, length))
        net = rng.normal(net_mu, net_sd, length).clip(0, 100)
        hist = pd.DataFrame({"cpu": cpu, "mem": mem, "net": net})
        feats = extract_features(hist.to_dict("records"))[0].copy()
        feats[3] += rng.normal(avg1m_bias, 3.0)      # decouple avg from latest
        feats[4] += rng.normal(avg1m_bias * 0.6, 3.0)
        rows.append(feats)
    return np.vstack(rows)


def _synthetic_dataset(n_per_class: int = 1200, seed: int = 42):
    """Synthetic incident corpus shaped like the simulator's three scenarios,
    including the PPTX predictive-labelling twist: part of `at_risk` comes from
    the 'impending crash' precursor window (~3 min before failure) where
    readings are not yet extreme but the trend is already climbing."""
    rng = np.random.default_rng(seed)
    X_parts, y_parts = [], []

    def add(X, label):
        X_parts.append(X)
        y_parts.append(np.full(len(X), label, dtype=int))

    # ---- healthy ----------------------------------------------------------
    add(_features_from_series(rng, n_per_class, 20, 8, 30, 6, 50, 10), 0)

    # ---- transient spike (burst now, rolling average still moderate) ------
    add(_features_from_series(rng, int(n_per_class * 0.7),
                              78, 10, 35, 8, 85, 10, avg1m_bias=-25), 1)
    add(_features_from_series(rng, int(n_per_class * 0.3),
                              55, 12, 33, 8, 70, 14, avg1m_bias=-15), 1)

    # ---- at risk (sustained overload + memory growth) ----------------------
    add(_features_from_series(rng, int(n_per_class * 0.65),
                              85, 8, 78, 10, 65, 12,
                              mem_slope=2.2, avg1m_bias=4), 2)
    # IMPENDING-CRASH precursors — the ~3-minute pre-failure window (slide 13).
    add(_features_from_series(rng, int(n_per_class * 0.35),
                              62, 10, 58, 9, 60, 10,
                              mem_slope=3.5, avg1m_bias=18), 2)

    X = np.vstack(X_parts)
    y = np.concatenate(y_parts)
    idx = rng.permutation(len(X))
    return pd.DataFrame(X[idx], columns=FEATURE_NAMES), y[idx]


def train_model() -> RandomForestClassifier:
    X, y = _synthetic_dataset()
    clf = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42)
    clf.fit(X.values, y)
    return clf


def _load_or_train() -> RandomForestClassifier:
    """Load the persisted forest; train + persist on first run (PPTX slide 10:
    'trained offline on historical stress-test telemetry, loaded for live
    inference')."""
    if MODEL_PATH.exists():
        try:
            return joblib.load(MODEL_PATH)
        except Exception:
            pass  # corrupt/stale artifact — fall through to retrain
    clf = train_model()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    return clf


# Load once at import — persisted artifact is instant; first run trains ~1-2 s.
MODEL = _load_or_train()


def predict_state(history: list[dict]) -> tuple[str, float]:
    """Return (class_label, confidence) for the given metric history.
    Signature is frozen — this is the interface contract used by main.py."""
    features = extract_features(history)
    pred = MODEL.predict(features)[0]
    proba = MODEL.predict_proba(features)[0][pred]
    return CLASSES[int(pred)], float(proba)


def predict_features(features_row) -> tuple[str, float]:
    """Classify an already-engineered feature row (tests / analysis tools)."""
    pred = MODEL.predict(features_row)[0]
    proba = MODEL.predict_proba(features_row)[0][pred]
    return CLASSES[int(pred)], float(proba)


def model_info() -> dict:
    """Introspection payload for GET /api/model/info."""
    importances = sorted(
        zip(FEATURE_NAMES, MODEL.feature_importances_),
        key=lambda kv: kv[1], reverse=True,
    )
    return {
        "classes": CLASSES,
        "features": FEATURE_NAMES,
        "n_estimators": getattr(MODEL, "n_estimators", None),
        "max_depth": getattr(MODEL, "max_depth", None),
        "feature_importances": {
            name: round(float(imp), 4) for name, imp in importances
        },
        "artifact": str(MODEL_PATH.relative_to(Path(__file__).parent)),
        "trained_on": "synthetic incident corpus with predictive labels",
    }
