"""Download and inspect the core Valencia Urban Equity Compass datasets.

This script intentionally stops at data inspection and light preparation. It
does not build final app features or the Urban Quality Index.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from urllib.request import Request, urlopen

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_PATH = PROJECT_ROOT / "docs" / "data_inspection_report.md"
CKAN_BASE_URL = "https://opendata.vlci.valencia.es"


@dataclass(frozen=True)
class DatasetConfig:
    """Configuration for one CKAN resource to download and inspect."""

    key: str
    title: str
    package_slug: str
    resource_id: str
    expected_format: str
    output_filename: str


DATASETS = [
    DatasetConfig(
        key="barris_barrios",
        title="Barris / Barrios",
        package_slug="barris-barrios",
        resource_id="a6dde129-553f-4c7a-88dd-293577496987",
        expected_format="GeoJSON",
        output_filename="barris_barrios.geojson",
    ),
    DatasetConfig(
        key="districtes_distritos",
        title="Districtes / Distritos",
        package_slug="districtes-distritos",
        resource_id="0ae40a62-b909-46bb-8b7b-c5cdf56bf269",
        expected_format="GeoJSON",
        output_filename="districtes_distritos.geojson",
    ),
    DatasetConfig(
        key="espais_verds",
        title="Espais Verds / Espacios Verdes",
        package_slug="espais-verds-espacios-verdes",
        resource_id="80e9c2c1-6e6d-4519-ae96-a63dd7db5196",
        expected_format="GeoJSON",
        output_filename="espais_verds.geojson",
    ),
    DatasetConfig(
        key="mapa_soroll_nit",
        title="Mapa soroll nit / Mapa ruido noche",
        package_slug="mapa-soroll-nit-mapa-ruido-noche",
        resource_id="cd2dfd8f-0255-4269-816f-7fdef7a77a6b",
        expected_format="GeoJSON",
        output_filename="mapa_soroll_nit.geojson",
    ),
    DatasetConfig(
        key="quejas_sugerencias",
        title="Quejas y Sugerencias",
        package_slug="total-castellano",
        resource_id="b57d263a-867f-44c5-aeb9-3a1b301a368b",
        expected_format="CSV",
        output_filename="quejas_sugerencias.csv",
    ),
]


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch a JSON document from a URL."""
    request = Request(url, headers={"User-Agent": "ValenciaUrbanEquityCompass/0.1"})
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bytes(url: str) -> bytes:
    """Fetch raw bytes from a URL."""
    request = Request(url, headers={"User-Agent": "ValenciaUrbanEquityCompass/0.1"})
    with urlopen(request, timeout=180) as response:
        return response.read()


def resource_show_url(resource_id: str) -> str:
    """Build the CKAN resource_show URL for a resource ID."""
    return f"{CKAN_BASE_URL}/api/3/action/resource_show?id={resource_id}"


def get_resource_metadata(config: DatasetConfig) -> dict[str, Any]:
    """Fetch CKAN resource metadata for one dataset."""
    payload = fetch_json(resource_show_url(config.resource_id))
    if not payload.get("success"):
        raise RuntimeError(f"CKAN resource_show failed for {config.key}")
    return payload["result"]


def add_query_params(url: str, params: dict[str, Any]) -> str:
    """Return a URL with added or replaced query parameters."""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query.update({key: str(value) for key, value in params.items()})
    return urlunparse(parsed._replace(query=urlencode(query)))


def download_arcgis_geojson(url: str) -> dict[str, Any]:
    """Download an ArcGIS MapServer GeoJSON endpoint, handling pagination."""
    first_page = fetch_json(url)
    features = list(first_page.get("features", []))

    if not first_page.get("exceededTransferLimit"):
        return first_page

    page_size = 2000
    offset = len(features)
    while True:
        page_url = add_query_params(
            url,
            {"resultOffset": offset, "resultRecordCount": page_size},
        )
        page = fetch_json(page_url)
        page_features = page.get("features", [])
        if not page_features:
            break
        features.extend(page_features)
        offset += len(page_features)
        if not page.get("exceededTransferLimit"):
            break

    first_page["features"] = features
    first_page.pop("exceededTransferLimit", None)
    return first_page


def download_resource(config: DatasetConfig, metadata: dict[str, Any]) -> Path:
    """Download one resource to data/raw and return its path."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_DIR / config.output_filename
    url = metadata["url"]

    if config.expected_format.lower() == "geojson":
        geojson = download_arcgis_geojson(url)
        output_path.write_text(
            json.dumps(geojson, ensure_ascii=False),
            encoding="utf-8",
        )
        return output_path

    output_path.write_bytes(fetch_bytes(url))
    return output_path


def geojson_to_properties_frame(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load GeoJSON properties into a DataFrame and collect geometry metadata."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    rows = [feature.get("properties", {}) for feature in features]
    geometry_types = [
        (feature.get("geometry") or {}).get("type")
        for feature in features
        if feature.get("geometry")
    ]
    frame = pd.DataFrame(rows)
    geometry_summary = {
        "has_geometry": bool(geometry_types),
        "geometry_types": sorted(set(geometry_types)),
        "geometry_type_counts": pd.Series(geometry_types).value_counts().to_dict(),
    }
    return frame, geometry_summary


def detect_csv_separator(path: Path) -> str:
    """Detect CSV delimiter from a small sample."""
    sample = read_text_with_best_encoding(path, max_chars=4096)
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    return dialect.delimiter


def read_text_with_best_encoding(path: Path, max_chars: int | None = None) -> str:
    """Read text using the first encoding that preserves accented headers."""
    raw = path.read_bytes()
    if max_chars is not None:
        raw = raw[: max_chars * 4]

    best_text = ""
    best_score = -1
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        score = text.count("ó") + text.count("í") + text.count("á") + text.count("é")
        score -= text.count("Ã") * 5
        if score > best_score:
            best_text = text
            best_score = score

    return best_text[:max_chars] if max_chars is not None else best_text


def detect_csv_encoding(path: Path) -> str:
    """Detect a practical CSV encoding for Valencia Open Data exports."""
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


def load_csv_frame(path: Path) -> pd.DataFrame:
    """Load a CSV file with delimiter detection."""
    separator = detect_csv_separator(path)
    encoding = detect_csv_encoding(path)
    return pd.read_csv(path, sep=separator, encoding=encoding, dtype="string")


def normalize_for_matching(value: str) -> str:
    """Normalize text for column-name candidate detection."""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def candidate_columns(columns: list[str]) -> dict[str, list[str]]:
    """Detect possible identifier, district, neighbourhood, and geometry fields."""
    normalized = {column: normalize_for_matching(column) for column in columns}

    def is_area_field(clean: str) -> bool:
        return clean == "area" or clean.endswith("_area") or "_area_" in clean

    return {
        "neighbourhood_candidates": [
            column
            for column, clean in normalized.items()
            if not is_area_field(clean)
            and ("barri" in clean or "barrio" in clean or "codbar" in clean)
        ],
        "district_candidates": [
            column
            for column, clean in normalized.items()
            if not is_area_field(clean) and ("distr" in clean or "coddist" in clean)
        ],
        "id_candidates": [
            column
            for column, clean in normalized.items()
            if clean in {"id", "gid", "objectid"} or clean.startswith("cod")
        ],
        "coordinate_candidates": [
            column
            for column, clean in normalized.items()
            if clean in {"lat", "latitude", "lon", "lng", "longitud", "latitud"}
            or "geo" in clean
        ],
    }


def inspect_frame(
    config: DatasetConfig,
    path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Inspect a downloaded CSV or GeoJSON resource."""
    geometry_summary: dict[str, Any] = {}
    if config.expected_format.lower() == "geojson":
        frame, geometry_summary = geojson_to_properties_frame(path)
    else:
        frame = load_csv_frame(path)

    missing = frame.isna().sum().sort_values(ascending=False)
    dtypes = {column: str(dtype) for column, dtype in frame.dtypes.items()}

    return {
        "key": config.key,
        "title": config.title,
        "package_slug": config.package_slug,
        "resource_id": config.resource_id,
        "format": metadata.get("format") or config.expected_format,
        "download_url": metadata.get("url"),
        "local_path": str(path.relative_to(PROJECT_ROOT)),
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "dtypes": dtypes,
        "missing_values": {column: int(value) for column, value in missing.items()},
        "candidates": candidate_columns(list(frame.columns)),
        "geometry": geometry_summary,
    }


def markdown_table(rows: list[list[Any]], headers: list[str]) -> str:
    """Render a small Markdown table."""
    output = ["| " + " | ".join(headers) + " |"]
    output.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(output)


def render_dataset_report(profile: dict[str, Any]) -> str:
    """Render one dataset profile as Markdown."""
    missing_rows = [
        [column, dtype, profile["missing_values"].get(column, 0)]
        for column, dtype in profile["dtypes"].items()
    ]
    candidates = profile["candidates"]
    geometry = profile["geometry"]

    lines = [
        f"## {profile['title']}",
        "",
        f"- Package slug: `{profile['package_slug']}`",
        f"- Resource ID: `{profile['resource_id']}`",
        f"- Format: `{profile['format']}`",
        f"- Local raw file: `{profile['local_path']}`",
        f"- Rows: `{profile['rows']}`",
        f"- Columns: `{len(profile['columns'])}`",
        f"- Download URL: {profile['download_url']}",
        "",
        "### Join and Geometry Signals",
        "",
        f"- Neighbourhood candidates: `{', '.join(candidates['neighbourhood_candidates']) or 'None found'}`",
        f"- District candidates: `{', '.join(candidates['district_candidates']) or 'None found'}`",
        f"- ID candidates: `{', '.join(candidates['id_candidates']) or 'None found'}`",
        f"- Coordinate candidates: `{', '.join(candidates['coordinate_candidates']) or 'None found'}`",
    ]

    if geometry:
        lines.extend(
            [
                f"- Has geometry: `{geometry['has_geometry']}`",
                f"- Geometry types: `{', '.join(geometry['geometry_types'])}`",
                f"- Geometry type counts: `{geometry['geometry_type_counts']}`",
            ]
        )

    lines.extend(
        [
            "",
            "### Columns, Types, and Missing Values",
            "",
            markdown_table(missing_rows, ["Column", "Detected dtype", "Missing values"]),
            "",
        ]
    )
    return "\n".join(lines)


def render_report(profiles: list[dict[str, Any]]) -> str:
    """Render the full Markdown inspection report."""
    summary_rows = [
        [
            profile["title"],
            profile["format"],
            profile["rows"],
            len(profile["columns"]),
            "Yes" if profile["geometry"].get("has_geometry") else "No",
            ", ".join(profile["candidates"]["neighbourhood_candidates"]) or "None",
            ", ".join(profile["candidates"]["district_candidates"]) or "None",
        ]
        for profile in profiles
    ]

    sections = [
        "# Data Inspection Report",
        "",
        "Project: **Valencia Urban Equity Compass**",
        "",
        "This report was generated by `notebooks/01_download_and_inspect_data.py`.",
        "It documents the raw schemas found in the first core datasets and gives",
        "recommendations for building a neighbourhood-level master table.",
        "",
        "## Summary",
        "",
        markdown_table(
            summary_rows,
            [
                "Dataset",
                "Format",
                "Rows",
                "Columns",
                "Geometry",
                "Neighbourhood fields",
                "District fields",
            ],
        ),
        "",
        "## Dataset Details",
        "",
    ]

    for profile in profiles:
        sections.append(render_dataset_report(profile))

    sections.extend(
        [
            "## Usability and Join Recommendations",
            "",
            "- Use `Barris / Barrios` as the canonical neighbourhood geometry layer.",
            "- Use `Districtes / Distritos` as the district reference layer and for",
            "  validation of district codes/names.",
            "- Join `Quejas y Sugerencias` directly through its real barrio/distrito",
            "  code or name columns after standardizing text values.",
            "- Aggregate `Espais Verds / Espacios Verdes` spatially to barrios. If",
            "  polygons are available, compute area after projecting in a metric CRS.",
            "- Aggregate `Mapa soroll nit / Mapa ruido noche` spatially to barrios.",
            "  Use its real noise-level field rather than inventing a new category.",
            "- The next step should create `data/processed/neighbourhood_master.csv`",
            "  or `.geojson` with one row per barrio and only validated, reproducible",
            "  features.",
            "",
            "## Next Step",
            "",
            "Build a neighbourhood-level master table by:",
            "",
            "1. Loading the barrio GeoJSON as the base table.",
            "2. Standardizing barrio and district identifiers.",
            "3. Aggregating complaints by barrio/district fields.",
            "4. Performing spatial joins for green spaces and night-noise polygons.",
            "5. Saving intermediate validation tables before calculating any index.",
            "",
        ]
    )

    return "\n".join(sections)


def main() -> int:
    """Run the download and inspection workflow."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    profiles: list[dict[str, Any]] = []
    for config in DATASETS:
        print(f"Downloading and inspecting: {config.title}")
        metadata = get_resource_metadata(config)
        path = download_resource(config, metadata)
        profiles.append(inspect_frame(config, path, metadata))

    REPORT_PATH.write_text(render_report(profiles), encoding="utf-8")
    print(f"Report written to {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
