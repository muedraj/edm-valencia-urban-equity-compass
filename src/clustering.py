"""Neighbourhood clustering utilities."""

from __future__ import annotations

import pandas as pd


CLUSTER_FEATURES = ["green_score", "low_noise_score", "low_complaints_score"]


def fit_neighbourhood_clusters(
    data: pd.DataFrame,
    n_clusters: int = 4,
) -> pd.DataFrame:
    """Assign neighbourhoods to clusters based on urban indicators.

    Parameters
    ----------
    data:
        Dataset containing normalized indicators.
    n_clusters:
        Number of clusters to fit.

    Returns
    -------
    pandas.DataFrame
        Dataset with an added cluster label.
    """
    missing = [column for column in CLUSTER_FEATURES if column not in data.columns]
    if missing:
        raise ValueError(f"Missing columns for clustering: {missing}")

    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    clustered = data.copy()
    matrix = clustered[CLUSTER_FEATURES].astype(float)
    scaled = StandardScaler().fit_transform(matrix)

    model = KMeans(n_clusters=n_clusters, random_state=42, n_init=20)
    clustered["cluster"] = model.fit_predict(scaled).astype(int)
    profiles = describe_clusters(clustered)
    label_map = profiles.set_index("cluster")["cluster_label"].to_dict()
    clustered["cluster_label"] = clustered["cluster"].map(label_map)
    return clustered


def describe_clusters(data: pd.DataFrame) -> pd.DataFrame:
    """Create human-readable summaries for each cluster.

    Parameters
    ----------
    data:
        Dataset containing neighbourhood indicators and cluster labels.

    Returns
    -------
    pandas.DataFrame
        Cluster-level summary table.
    """
    required = [*CLUSTER_FEATURES, "cluster"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Missing columns for cluster description: {missing}")

    profiles = (
        data.groupby("cluster")
        .agg(
            cluster_size=("cluster", "size"),
            green_score_mean=("green_score", "mean"),
            low_noise_score_mean=("low_noise_score", "mean"),
            low_complaints_score_mean=("low_complaints_score", "mean"),
        )
        .reset_index()
    )
    profiles["urban_quality_index_mean"] = (
        0.40 * profiles["green_score_mean"]
        + 0.30 * profiles["low_noise_score_mean"]
        + 0.30 * profiles["low_complaints_score_mean"]
    )
    profiles["cluster_label"] = assign_cluster_labels(profiles)
    return profiles


def assign_cluster_labels(profiles: pd.DataFrame) -> list[str]:
    """Assign labels from cluster averages rather than fixed cluster IDs.

    Labels come from relative cluster strengths and weaknesses. A cluster is only
    labelled as green/balanced when all three score dimensions are above the
    overall cluster-profile average.
    """
    labels: dict[int, str] = {}
    worst_cluster = int(
        profiles.sort_values("urban_quality_index_mean", ascending=True).iloc[0][
            "cluster"
        ]
    )
    overall = {
        "green_score_mean": profiles["green_score_mean"].mean(),
        "low_noise_score_mean": profiles["low_noise_score_mean"].mean(),
        "low_complaints_score_mean": profiles["low_complaints_score_mean"].mean(),
    }

    labels[worst_cluster] = "Low-comfort neighbourhoods"

    weakness_columns = {
        "green_score_mean": "Low-green comfort areas",
        "low_noise_score_mean": "Noisy urban pressure areas",
        "low_complaints_score_mean": "Complaint hotspots",
    }
    used_labels = set(labels.values())

    for _, row in profiles.sort_values("cluster").iterrows():
        cluster = int(row["cluster"])
        if cluster in labels:
            continue

        above_green = row["green_score_mean"] >= overall["green_score_mean"]
        above_noise = row["low_noise_score_mean"] >= overall["low_noise_score_mean"]
        above_complaints = (
            row["low_complaints_score_mean"] >= overall["low_complaints_score_mean"]
        )

        if above_green and above_noise and above_complaints:
            candidate = "Green and balanced areas"
        elif above_noise and above_complaints and not above_green:
            candidate = "Quiet low-complaint areas"
        elif above_green and (not above_noise or not above_complaints):
            candidate = "Green but pressured areas"
        else:
            weakest_column = min(weakness_columns, key=lambda column: row[column])
            candidate = weakness_columns[weakest_column]

        if candidate in used_labels:
            candidate = f"{candidate} ({cluster})"
        labels[cluster] = candidate
        used_labels.add(candidate)

    return [labels[int(cluster)] for cluster in profiles["cluster"]]
