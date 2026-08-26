"""ML tests: feature contract, class balance, accuracy, predictive labelling."""
import numpy as np

import ml_model


def test_feature_vector_shape_and_names():
    history = [{"t": i, "cpu": 50, "mem": 40, "net": 60} for i in range(30)]
    feats = ml_model.extract_features(history)
    assert feats.shape == (1, len(ml_model.FEATURE_NAMES))
    assert np.isfinite(feats).all()


def test_empty_history_returns_zero_row():
    feats = ml_model.extract_features([])
    assert feats.shape == (1, len(ml_model.FEATURE_NAMES))
    assert np.count_nonzero(feats) == 0


def test_rolling_average_separates_burst_from_sustained():
    """The core insight: same latest CPU, different rolling averages."""
    burst = ([{"cpu": 20}] * 18 + [{"cpu": 90}])           # spike at the end
    sustained = [{"cpu": 88}] * 19                          # sustained load
    f_burst = ml_model.extract_features(burst)[0]
    f_sust = ml_model.extract_features(sustained)[0]
    avg1m_idx = ml_model.FEATURE_NAMES.index("cpu_avg_1m")
    assert f_burst[avg1m_idx] + 30 < f_sust[avg1m_idx]


def test_synthetic_dataset_balanced_enough():
    X, y = ml_model._synthetic_dataset(n_per_class=120, seed=7)
    counts = np.bincount(y, minlength=3)
    assert len(X) == len(y)
    assert counts.min() >= 100          # every class well represented
    assert list(np.unique(y)) == [0, 1, 2]


def test_model_accuracy_on_held_out_split():
    """Fresh forest on one seed must generalise to another (>95%)."""
    X_train, y_train = ml_model._synthetic_dataset(n_per_class=250, seed=101)
    X_test, y_test = ml_model._synthetic_dataset(n_per_class=150, seed=202)
    clf = ml_model.RandomForestClassifier(
        n_estimators=80, max_depth=8, random_state=0)
    clf.fit(X_train.values, y_train)
    acc = clf.score(X_test.values, y_test)
    assert acc > 0.95, f"accuracy too low: {acc:.3f}"


def test_predict_state_returns_known_labels_with_confidence():
    sim_history = [
        {"t": i * 3, "cpu": 85 + i, "mem": 76 + i * 0.5, "net": 65}
        for i in range(12)
    ]
    label, conf = ml_model.predict_state(sim_history)
    assert label in ml_model.CLASSES
    assert 0.0 <= conf <= 1.0


def test_model_info_payload():
    info = ml_model.model_info()
    assert info["classes"] == ml_model.CLASSES
    assert info["features"] == ml_model.FEATURE_NAMES
    assert len(info["feature_importances"]) == len(ml_model.FEATURE_NAMES)
    assert sum(info["feature_importances"].values()) > 0.99  # importances sum ~1
