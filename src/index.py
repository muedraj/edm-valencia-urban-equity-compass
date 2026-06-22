"""Urban Quality Index calculation utilities."""

from __future__ import annotations

import pandas as pd


DEFAULT_INDEX_WEIGHTS = {
    "green_score": 0.40,
    "low_noise_score": 0.30,
    "low_complaints_score": 0.30,
}


def min_max_score(series: pd.Series, reverse: bool = False) -> pd.Series:
    """Scale a numeric series to 0-100 with optional reversal.

    Parameters
    ----------
    series:
        Numeric input values.
    reverse:
        If True, high raw values receive low scores. Use this for negative
        indicators such as noise and complaints.

    Returns
    -------
    pandas.Series
        Score from 0 to 100. If all values are equal, every row receives 50.
    """
    values = pd.to_numeric(series, errors="coerce")
    minimum = values.min()
    maximum = values.max()

    if pd.isna(minimum) or pd.isna(maximum):
        return pd.Series(pd.NA, index=series.index, dtype="Float64")
    if maximum == minimum:
        return pd.Series(50.0, index=series.index)

    score = (values - minimum) / (maximum - minimum) * 100
    if reverse:
        score = 100 - score
    return score


def add_normalized_indicators(
    data: pd.DataFrame,
    green_column: str = "green_area_total_m2",
    noise_column: str = "noise_area_weighted_mean",
    complaints_column: str = "complaints_total",
) -> pd.DataFrame:
    """Add normalized indicator scores used by the first index version."""
    required = [green_column, noise_column, complaints_column]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Missing columns for normalized indicators: {missing}")

    scored = data.copy()
    scored["green_score"] = min_max_score(scored[green_column], reverse=False)
    scored["low_noise_score"] = min_max_score(scored[noise_column], reverse=True)
    scored["low_complaints_score"] = min_max_score(
        scored[complaints_column],
        reverse=True,
    )
    return scored


def calculate_urban_quality_index(
    data: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Calculate the composite Urban Quality Index.

    Parameters
    ----------
    data:
        Dataset containing normalized urban indicators.
    weights:
        Optional mapping from normalized indicator names to weights. If omitted,
        a default weighting scheme will be used once the final indicators are
        defined.

    Returns
    -------
    pandas.DataFrame
        Dataset with an added Urban Quality Index column.
    """
    selected_weights = validate_weights(weights or DEFAULT_INDEX_WEIGHTS)
    missing = [column for column in selected_weights if column not in data.columns]
    if missing:
        raise ValueError(f"Missing score columns for Urban Quality Index: {missing}")

    indexed = data.copy()
    indexed["urban_quality_index"] = 0.0
    for column, weight in selected_weights.items():
        indexed["urban_quality_index"] += pd.to_numeric(indexed[column]) * weight
    return indexed


def add_rankings(data: pd.DataFrame) -> pd.DataFrame:
    """Add ranking columns where rank 1 is the most favourable value."""
    required = [
        "urban_quality_index",
        "green_score",
        "low_noise_score",
        "low_complaints_score",
    ]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Missing columns for rankings: {missing}")

    ranked = data.copy()
    ranked["urban_quality_rank"] = ranked["urban_quality_index"].rank(
        ascending=False,
        method="min",
    )
    ranked["green_rank"] = ranked["green_score"].rank(ascending=False, method="min")
    ranked["noise_rank"] = ranked["low_noise_score"].rank(ascending=False, method="min")
    ranked["complaints_rank"] = ranked["low_complaints_score"].rank(
        ascending=False,
        method="min",
    )

    for column in [
        "urban_quality_rank",
        "green_rank",
        "noise_rank",
        "complaints_rank",
    ]:
        ranked[column] = ranked[column].astype("int64")
    return ranked


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    """Validate and normalize index weights.

    Parameters
    ----------
    weights:
        Mapping between indicator names and numeric weights.

    Returns
    -------
    dict[str, float]
        Validated weights summing to 1.0.
    """
    if not weights:
        raise ValueError("Weights cannot be empty.")

    numeric_weights = {key: float(value) for key, value in weights.items()}
    if any(value < 0 for value in numeric_weights.values()):
        raise ValueError("Weights must be non-negative.")

    total = sum(numeric_weights.values())
    if total <= 0:
        raise ValueError("At least one weight must be positive.")

    return {key: value / total for key, value in numeric_weights.items()}
