"""Feature engineering functions for urban quality indicators.

This module is reserved for reusable feature engineering logic. The current
master-table construction is implemented in `scripts/build_master_table.py`
because it is a reproducible batch workflow rather than a Streamlit runtime
operation.
"""

from __future__ import annotations

import pandas as pd


def build_neighbourhood_features(data: pd.DataFrame) -> pd.DataFrame:
    """Create neighbourhood-level urban indicators.

    Parameters
    ----------
    data:
        Cleaned and merged neighbourhood-level dataset.

    Returns
    -------
    pandas.DataFrame
        Dataset with engineered features ready for normalization and modelling.

    Notes
    -----
    TODO: Add real indicators after confirming available fields, for example
    green space per resident, tree density, noise exposure, complaint rate, and
    mobility pressure.
    """
    raise NotImplementedError("Feature engineering will be implemented later.")


def normalize_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize urban indicators to comparable scales.

    Parameters
    ----------
    data:
        Dataset containing raw engineered indicators.

    Returns
    -------
    pandas.DataFrame
        Dataset containing normalized indicators.

    Notes
    -----
    TODO: Decide between min-max scaling and robust scaling after inspecting
    distributions and outliers.
    """
    raise NotImplementedError("Indicator normalization will be implemented later.")
