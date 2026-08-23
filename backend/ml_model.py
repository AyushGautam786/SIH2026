"""
ml_model.py — 3-class Random Forest classifier: healthy / transient_spike / at_risk.

For the prototype we train on synthetic data shaped to match the simulator's
scenarios (fast to demo, no dataset to ship). The feature contract below is
what matters for the upgrade path — point this same function at real
Prometheus/cAdvisor history later and nothing else in the pipeline changes.
"""
import numpy as np
from sklearn.ensemble import RandomForestClassifier

CLASSES = ["healthy", "transient_spike", "at_risk"]


def _synthetic_dataset(n_per_class: int = 1200, seed: int = 42):
    rng = np.random.default_rng(seed)
    rows, labels = [], []

    # healthy: low + stable everything
    cpu = rng.normal(20, 8, n_per_class).clip(0, 100)
    mem = rng.normal(30, 6, n_per_class).clip(0, 100)
    net = rng.normal(50, 10, n_per_class).clip(0, 100)
    cpu_avg = cpu + rng.normal(0, 4, n_per_class)
    mem_delta = rng.normal(0, 2, n_per_class)
    net_std = rng.normal(5, 2, n_per_class).clip(0, None)
    rows.append(np.column_stack([cpu, mem, net, cpu_avg, mem_delta, net_std]))
    labels += [0] * n_per_class

    # transient_spike: instantaneous CPU/net burst, rolling avg still moderate,
    # no memory growth — the distinguishing feature vs at_risk
    cpu = rng.normal(78, 10, n_per_class).clip(0, 100)
    mem = rng.normal(35, 8, n_per_class).clip(0, 100)
    net = rng.normal(85, 10, n_per_class).clip(0, 100)
    cpu_avg = rng.normal(45, 10, n_per_class).clip(0, 100)
    mem_delta = rng.normal(0, 3, n_per_class)
    net_std = rng.normal(15, 5, n_per_class).clip(0, None)
    rows.append(np.column_stack([cpu, mem, net, cpu_avg, mem_delta, net_std]))
    labels += [1] * n_per_class

    # at_risk: sustained high CPU + rolling avg high + memory growing (leak-like)
    cpu = rng.normal(85, 8, n_per_class).clip(0, 100)
    mem = rng.normal(78, 10, n_per_class).clip(0, 100)
    net = rng.normal(65, 12, n_per_class).clip(0, 100)
    cpu_avg = rng.normal(80, 8, n_per_class).clip(0, 100)
    mem_delta = rng.normal(5, 2, n_per_class).clip(0, None)
    net_std = rng.normal(8, 3, n_per_class).clip(0, None)
    rows.append(np.column_stack([cpu, mem, net, cpu_avg, mem_delta, net_std]))
    labels += [2] * n_per_class

    X = np.vstack(rows)
    y = np.array(labels)
    idx = rng.permutation(len(X))
    return X[idx], y[idx]


def train_model() -> RandomForestClassifier:
    X, y = _synthetic_dataset()
    clf = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42)
    clf.fit(X, y)
    return clf


def extract_features(history: list[dict]) -> np.ndarray:
    """Turn a container's recent metric history into the model's feature vector.

    Features (in order):
        cpu       — latest CPU reading
        mem       — latest memory reading
        net       — latest network reading
        cpu_avg   — rolling average CPU (catches sustained load vs. burst)
        mem_delta — memory growth over the window (catches leaks)
        net_std   — standard deviation of network (catches erratic patterns)
    """
    if not history:
        return np.array([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]])

    cpu_series = [h["cpu"] for h in history]
    mem_series = [h["mem"] for h in history]
    net_series = [h["net"] for h in history]

    cpu = cpu_series[-1]
    mem = mem_series[-1]
    net = net_series[-1]
    cpu_avg = float(np.mean(cpu_series))
    mem_delta = mem_series[-1] - mem_series[0] if len(mem_series) > 1 else 0.0
    net_std = float(np.std(net_series))

    return np.array([[cpu, mem, net, cpu_avg, mem_delta, net_std]])


# Train once at import — fast (~3600 rows, shallow forest) so startup stays instant.
MODEL = train_model()


def predict_state(history: list[dict]) -> tuple[str, float]:
    """Return (class_label, confidence) for the given metric history."""
    features = extract_features(history)
    pred = MODEL.predict(features)[0]
    proba = MODEL.predict_proba(features)[0][pred]
    return CLASSES[pred], float(proba)
