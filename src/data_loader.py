"""Data loading utilities for the Valencia Urban Equity Compass project.

The functions in this module are intentionally generic. They load raw files and
CKAN metadata without assuming final feature columns that have not yet been
validated.
"""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd


CKAN_BASE_URL = "https://opendata.vlci.valencia.es"

DATASET_RESOURCES: dict[str, dict[str, str]] = {
    "barris_barrios": {
        "title": "Barris / Barrios",
        "package_slug": "barris-barrios",
        "resource_id": "a6dde129-553f-4c7a-88dd-293577496987",
        "format": "GeoJSON",
        "raw_filename": "barris_barrios.geojson",
    },
    "districtes_distritos": {
        "title": "Districtes / Distritos",
        "package_slug": "districtes-distritos",
        "resource_id": "0ae40a62-b909-46bb-8b7b-c5cdf56bf269",
        "format": "GeoJSON",
        "raw_filename": "districtes_distritos.geojson",
    },
    "espais_verds": {
        "title": "Espais Verds / Espacios Verdes",
        "package_slug": "espais-verds-espacios-verdes",
        "resource_id": "80e9c2c1-6e6d-4519-ae96-a63dd7db5196",
        "format": "GeoJSON",
        "raw_filename": "espais_verds.geojson",
    },
    "mapa_soroll_nit": {
        "title": "Mapa soroll nit / Mapa ruido noche",
        "package_slug": "mapa-soroll-nit-mapa-ruido-noche",
        "resource_id": "cd2dfd8f-0255-4269-816f-7fdef7a77a6b",
        "format": "GeoJSON",
        "raw_filename": "mapa_soroll_nit.geojson",
    },
    "quejas_sugerencias": {
        "title": "Quejas y Sugerencias",
        "package_slug": "total-castellano",
        "resource_id": "b57d263a-867f-44c5-aeb9-3a1b301a368b",
        "format": "CSV",
        "raw_filename": "quejas_sugerencias.csv",
    },
}


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch JSON from a URL using only the Python standard library."""
    request = Request(url, headers={"User-Agent": "ValenciaUrbanEquityCompass/0.1"})
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_ckan_resource_metadata(resource_id: str) -> dict[str, Any]:
    """Fetch CKAN metadata for a resource ID.

    Parameters
    ----------
    resource_id:
        CKAN resource identifier.

    Returns
    -------
    dict[str, Any]
        CKAN resource metadata, including the real `url` download field.
    """
    url = f"{CKAN_BASE_URL}/api/3/action/resource_show?id={resource_id}"
    payload = fetch_json(url)
    if not payload.get("success"):
        raise RuntimeError(f"CKAN resource_show failed for {resource_id}")
    return payload["result"]


def get_dataset_resource(dataset_key: str) -> dict[str, str]:
    """Return local configuration for a known project dataset."""
    try:
        return DATASET_RESOURCES[dataset_key]
    except KeyError as exc:
        known = ", ".join(sorted(DATASET_RESOURCES))
        raise KeyError(f"Unknown dataset key '{dataset_key}'. Known keys: {known}") from exc


def detect_csv_encoding(path: str | Path) -> str:
    """Detect a practical encoding for CSV exports with Spanish headers."""
    path = Path(path)
    raw = path.read_bytes()[:8192]
    best_encoding = "utf-8-sig"
    best_score = -1
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        score = text.count("ó") + text.count("í") + text.count("á") + text.count("é")
        score -= text.count("Ã") * 5
        if score > best_score:
            best_encoding = encoding
            best_score = score
    return best_encoding


def detect_csv_separator(path: str | Path) -> str:
    """Detect a CSV separator from a small file sample."""
    path = Path(path)
    sample = path.read_bytes()[:8192].decode(detect_csv_encoding(path), errors="replace")
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    return dialect.delimiter


def load_raw_dataset(path: str | Path, **read_kwargs: Any) -> pd.DataFrame:
    """Load a raw CSV or GeoJSON dataset from disk.

    Parameters
    ----------
    path:
        Path to a raw CSV or GeoJSON file.
    **read_kwargs:
        Optional keyword arguments passed to the underlying pandas reader.

    Returns
    -------
    pandas.DataFrame
        Loaded dataset. For GeoJSON, the returned table contains feature
        properties plus a `_geometry_type` helper column.

    Notes
    -----
    This function does not assume final validated column names.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        read_options = {
            "sep": detect_csv_separator(path),
            "encoding": detect_csv_encoding(path),
            "dtype": "string",
        }
        read_options.update(read_kwargs)
        return pd.read_csv(path, **read_options)

    if suffix in {".geojson", ".json"}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for feature in payload.get("features", []):
            properties = dict(feature.get("properties", {}))
            properties["_geometry_type"] = (feature.get("geometry") or {}).get("type")
            rows.append(properties)
        return pd.DataFrame(rows)

    raise ValueError(f"Unsupported raw dataset format: {path.suffix}")


def load_processed_neighbourhood_metrics(path: str | Path) -> pd.DataFrame:
    """Load the processed neighbourhood-level metrics table.

    Parameters
    ----------
    path:
        Path to the processed dataset used by the Streamlit app.

    Returns
    -------
    pandas.DataFrame
        One row per neighbourhood, with engineered urban indicators.

    Notes
    -----
    TODO: Implement once `data/processed/` contains the final app dataset.
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported processed dataset format: {path.suffix}")
