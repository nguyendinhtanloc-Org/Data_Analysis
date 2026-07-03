"""Tests cho ML clustering module — không cần DB."""
import numpy as np
import pandas as pd

from src.ml.clustering import choose_best_k, assign_cluster_labels


def test_choose_best_k_small_data() -> None:
    x = np.random.randn(10, 3)
    best_k, score_df = choose_best_k(x, min_k=2, max_k=4)
    assert 2 <= best_k <= 4
    assert not score_df.empty
    assert list(score_df.columns) == ["k", "silhouette_score", "inertia"]


def test_choose_best_k_min_equals_max() -> None:
    x = np.random.randn(20, 3)
    best_k, score_df = choose_best_k(x, min_k=3, max_k=3)
    assert best_k == 3
    assert len(score_df) == 1


def test_choose_best_k_not_enough_samples() -> None:
    x = np.random.randn(2, 3)
    best_k, _ = choose_best_k(x, min_k=2, max_k=7)
    assert best_k == 2


def test_assign_cluster_labels_4_clusters() -> None:
    df = pd.DataFrame({
        "cluster_id": [0, 1, 2, 3],
        "recency_days": [10, 50, 30, 5],
        "frequency": [10, 2, 5, 15],
        "monetary": [1000, 200, 500, 2000],
    })
    labels = assign_cluster_labels(df)
    assert len(labels) == 4
    assert labels.nunique() == 4
    assert all(labels.notna())
    assert "Champions" in labels.values


def test_assign_cluster_labels_single_cluster() -> None:
    df = pd.DataFrame({
        "cluster_id": [0, 0, 0],
        "recency_days": [10, 20, 30],
        "frequency": [5, 5, 5],
        "monetary": [500, 500, 500],
    })
    labels = assign_cluster_labels(df)
    assert len(labels) == 3
    assert labels.nunique() == 1
