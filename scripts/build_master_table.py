"""Build the neighbourhood-level master table for the Streamlit app.

Outputs
-------
- data/processed/neighbourhood_master_table.csv
- data/processed/neighbourhood_master.geojson
- docs/master_table_validation_report.md

This script creates reliable base indicators only. It does not calculate the
Urban Quality Index.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_GEO_DEPS = PROJECT_ROOT / "work" / "geo_deps"
if LOCAL_GEO_DEPS.exists():
    sys.path.insert(0, str(LOCAL_GEO_DEPS))

try:
    import geopandas as gpd
except ImportError as exc:  # pragma: no cover - only reached in missing envs.
    raise SystemExit(
        "Missing geospatial dependencies. Install them with "
        "`pip install -r requirements.txt` before running this script."
    ) from exc


RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_PATH = PROJECT_ROOT / "docs" / "master_table_validation_report.md"

BARRIOS_PATH = RAW_DIR / "barris_barrios.geojson"
GREEN_PATH = RAW_DIR / "espais_verds.geojson"
COMPLAINTS_PATH = RAW_DIR / "quejas_sugerencias.csv"
NOISE_PATH = RAW_DIR / "mapa_soroll_nit.geojson"

MASTER_CSV_PATH = PROCESSED_DIR / "neighbourhood_master_table.csv"
MASTER_GEOJSON_PATH = PROCESSED_DIR / "neighbourhood_master.geojson"

WGS84_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:25830"


def normalize_text_for_join(value: object) -> str:
    """Normalize names for robust joins without inventing new semantic fields."""
    if pd.isna(value):
        return ""
    text = str(value).strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def compact_name_for_match(value: object) -> str:
    """Normalize names for duplicate-code disambiguation."""
    text = normalize_text_for_join(value)
    # The source has variants such as `Mauella` vs `MAHUELLA-TAULADELLA`.
    text = text.replace("H", "")
    return "".join(char for char in text if char.isalnum())


def load_geojson(path: Path) -> gpd.GeoDataFrame:
    """Load a GeoJSON file and ensure it has a CRS."""
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        # The Valencia Geoportal GeoJSON exports are longitude/latitude.
        gdf = gdf.set_crs(WGS84_CRS)
    return gdf


def load_complaints(path: Path) -> pd.DataFrame:
    """Load the complaints CSV with the real accented column names preserved."""
    return pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype="string")


def clean_code_series(series: pd.Series) -> pd.Series:
    """Keep valid barrio codes as zero-padded text and mark non-codes as missing."""
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.where(cleaned.str.fullmatch(r"\d+"), pd.NA)
    return cleaned.str.zfill(3)


def prepare_barrios() -> gpd.GeoDataFrame:
    """Load the canonical barrios layer and keep the required base columns."""
    barrios = load_geojson(BARRIOS_PATH)
    required_columns = [
        "objectid",
        "codbarrio",
        "nombre",
        "coddistbar",
        "coddistrit",
        "geometry",
    ]
    missing = [column for column in required_columns if column not in barrios.columns]
    if missing:
        raise ValueError(f"Missing required barrio columns: {missing}")

    barrios = barrios[required_columns].copy()
    barrios["barrio_unique_id"] = barrios["objectid"].astype("string")
    barrios["codbarrio"] = clean_code_series(barrios["codbarrio"])
    barrios["coddistbar"] = clean_code_series(barrios["coddistbar"])
    barrios["coddistrit"] = clean_code_series(barrios["coddistrit"]).str.lstrip("0")
    barrios["barrio_name_norm"] = barrios["nombre"].map(normalize_text_for_join)
    return barrios


def aggregate_green_spaces(
    barrios: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate green spaces to barrios using spatial intersections.

    Assumption
    ----------
    `espais_verds.geojson` contains `barrio` names but no barrio code. Because
    the names are not always identical to `barris_barrios.nombre`, geometry is
    used as the reliable aggregation method. The real `objectid`, `barrio`,
    `sup_total`, and `st_area(shape)` columns are still inspected for
    diagnostics and validation.
    """
    green = load_geojson(GREEN_PATH)
    required_columns = ["barrio", "sup_total", "st_area(shape)"]
    missing = [column for column in required_columns if column not in green.columns]
    if missing:
        raise ValueError(f"Missing required green-space columns: {missing}")

    green = green.copy()
    green["barrio_name_norm"] = green["barrio"].map(normalize_text_for_join)
    green["green_area_source_m2"] = pd.to_numeric(green["sup_total"], errors="coerce")
    green["green_area_source_m2"] = green["green_area_source_m2"].fillna(
        pd.to_numeric(green["st_area(shape)"], errors="coerce")
    )

    barrio_lookup = barrios[
        ["barrio_unique_id", "coddistbar", "nombre", "barrio_name_norm"]
    ].drop_duplicates()
    green_name_joined = green.merge(
        barrio_lookup,
        on="barrio_name_norm",
        how="left",
        suffixes=("_green", "_barrio"),
    )

    barrios_metric = make_valid_geometries(
        barrios[["barrio_unique_id", "coddistbar", "nombre", "geometry"]].to_crs(
            METRIC_CRS
        )
    )
    green_metric = make_valid_geometries(
        green[["objectid", "barrio", "green_area_source_m2", "geometry"]].to_crs(
            METRIC_CRS
        )
    )
    intersections = gpd.overlay(
        barrios_metric,
        green_metric,
        how="intersection",
        keep_geom_type=False,
    )

    if intersections.empty:
        aggregation = pd.DataFrame(
            columns=["barrio_unique_id", "green_spaces_count", "green_area_total_m2"]
        )
    else:
        intersections["green_intersection_area_m2"] = intersections.geometry.area
        intersections = intersections[intersections["green_intersection_area_m2"] > 0]
        aggregation = (
            intersections.groupby("barrio_unique_id", as_index=False)
            .agg(
                green_spaces_count=("objectid", "nunique"),
                green_area_total_m2=("green_intersection_area_m2", "sum"),
            )
        )

    # Diagnostic only: this shows why spatial overlay is preferred to names.
    unmatched = (
        green_name_joined.loc[green_name_joined["coddistbar"].isna(), ["barrio"]]
        .drop_duplicates()
        .sort_values("barrio")
    )
    return aggregation, unmatched


def assign_complaints_to_unique_barrios(
    complaints: pd.DataFrame,
    barrios: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Assign complaint rows to a unique barrio row.

    Most complaint codes map cleanly to one `coddistbar`. The official barrios
    layer currently contains one duplicated code, `175`, so rows with duplicated
    codes are disambiguated using `barrio_localización` against barrio names.
    """
    lookup = barrios[["barrio_unique_id", "coddistbar", "nombre"]].copy()
    lookup["name_compact"] = lookup["nombre"].map(compact_name_for_match)
    code_counts = lookup["coddistbar"].value_counts()
    unique_code_map = (
        lookup.loc[lookup["coddistbar"].map(code_counts).eq(1)]
        .set_index("coddistbar")["barrio_unique_id"]
        .to_dict()
    )
    duplicate_lookup = {
        code: frame
        for code, frame in lookup.loc[lookup["coddistbar"].map(code_counts).gt(1)].groupby(
            "coddistbar"
        )
    }

    assigned_ids: list[str | pd.NA] = []
    for _, row in complaints.iterrows():
        code = row["coddistbar"]
        if pd.isna(code):
            assigned_ids.append(pd.NA)
            continue
        if code in unique_code_map:
            assigned_ids.append(unique_code_map[code])
            continue

        candidates = duplicate_lookup.get(code)
        complaint_name = compact_name_for_match(row["barrio_localización"])
        matched_id = pd.NA
        if candidates is not None and complaint_name:
            for _, candidate in candidates.iterrows():
                barrio_name = candidate["name_compact"]
                if complaint_name in barrio_name or barrio_name in complaint_name:
                    matched_id = candidate["barrio_unique_id"]
                    break
        assigned_ids.append(matched_id)

    assigned = complaints.copy()
    assigned["barrio_unique_id"] = assigned_ids
    return assigned


def aggregate_complaints(
    barrios: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Aggregate complaints by `barrio_localización_código`.

    Assumption
    ----------
    `barrio_localización_código` is the city-wide barrio code and should match
    `barris_barrios.coddistbar`. Rows with values like `No consta` are excluded
    from neighbourhood-level counts and reported as unmatched.
    """
    complaints = load_complaints(COMPLAINTS_PATH)
    required_columns = [
        "barrio_localización_código",
        "barrio_localización",
        "tema",
    ]
    missing = [column for column in required_columns if column not in complaints.columns]
    if missing:
        raise ValueError(f"Missing required complaints columns: {missing}")

    complaints = complaints.copy()
    complaints["coddistbar"] = clean_code_series(complaints["barrio_localización_código"])
    valid = complaints.dropna(subset=["coddistbar"]).copy()
    assigned = assign_complaints_to_unique_barrios(valid, barrios)
    assigned_valid = assigned.dropna(subset=["barrio_unique_id"]).copy()

    totals = (
        assigned_valid.groupby("barrio_unique_id", as_index=False)
        .size()
        .rename(columns={"size": "complaints_total"})
    )

    theme_counts = (
        assigned_valid.groupby(["barrio_unique_id", "tema"], as_index=False)
        .size()
        .sort_values(["barrio_unique_id", "size", "tema"], ascending=[True, False, True])
    )
    top_theme = theme_counts.drop_duplicates("barrio_unique_id").rename(
        columns={
            "tema": "complaints_most_frequent_tema",
            "size": "complaints_most_frequent_tema_count",
        }
    )

    aggregation = totals.merge(
        top_theme[
            [
                "barrio_unique_id",
                "complaints_most_frequent_tema",
                "complaints_most_frequent_tema_count",
            ]
        ],
        on="barrio_unique_id",
        how="left",
    )
    aggregation["complaints_by_neighbourhood"] = aggregation["complaints_total"]

    diagnostics = {
        "rows_total": int(len(complaints)),
        "rows_with_valid_barrio_code": int(len(valid)),
        "rows_without_valid_barrio_code": int(len(complaints) - len(valid)),
        "rows_with_unique_barrio_assignment": int(len(assigned_valid)),
        "rows_unresolved_after_duplicate_code_disambiguation": int(
            len(valid) - len(assigned_valid)
        ),
        "invalid_code_values": sorted(
            complaints.loc[complaints["coddistbar"].isna(), "barrio_localización_código"]
            .dropna()
            .unique()
            .tolist()
        ),
    }
    return aggregation, diagnostics


def make_valid_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Repair invalid geometries using a conservative zero-width buffer."""
    repaired = gdf.copy()
    repaired["geometry"] = repaired.geometry.buffer(0)
    repaired = repaired[~repaired.geometry.is_empty & repaired.geometry.notna()].copy()
    return repaired


def aggregate_noise(barrios: gpd.GeoDataFrame) -> pd.DataFrame:
    """Aggregate night-noise polygons to barrio level using area weighting."""
    noise = load_geojson(NOISE_PATH)
    required_columns = ["gridcode", "geometry"]
    missing = [column for column in required_columns if column not in noise.columns]
    if missing:
        raise ValueError(f"Missing required noise columns: {missing}")

    barrios_metric = make_valid_geometries(
        barrios[["barrio_unique_id", "coddistbar", "nombre", "geometry"]].to_crs(
            METRIC_CRS
        )
    )
    noise_metric = make_valid_geometries(noise[["gridcode", "geometry"]].to_crs(METRIC_CRS))
    noise_metric["gridcode"] = pd.to_numeric(noise_metric["gridcode"], errors="coerce")

    intersections = gpd.overlay(
        barrios_metric,
        noise_metric.dropna(subset=["gridcode"]),
        how="intersection",
        keep_geom_type=False,
    )
    if intersections.empty:
        return pd.DataFrame(
            columns=["coddistbar", "noise_mean", "noise_max", "noise_area_weighted_mean"]
        )

    intersections["intersection_area_m2"] = intersections.geometry.area
    intersections = intersections[intersections["intersection_area_m2"] > 0].copy()
    intersections["weighted_noise"] = (
        intersections["gridcode"] * intersections["intersection_area_m2"]
    )

    aggregation = (
        intersections.groupby("barrio_unique_id", as_index=False)
        .agg(
            noise_mean=("gridcode", "mean"),
            noise_max=("gridcode", "max"),
            noise_intersection_area_m2=("intersection_area_m2", "sum"),
            weighted_noise_sum=("weighted_noise", "sum"),
        )
    )
    aggregation["noise_area_weighted_mean"] = (
        aggregation["weighted_noise_sum"] / aggregation["noise_intersection_area_m2"]
    )
    return aggregation.drop(columns=["weighted_noise_sum"])


def build_master_table() -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Build and return the full neighbourhood-level master GeoDataFrame."""
    barrios = prepare_barrios()
    green_agg, unmatched_green = aggregate_green_spaces(barrios)
    complaints_agg, complaints_diagnostics = aggregate_complaints(barrios)
    noise_agg = aggregate_noise(barrios)

    master = barrios.merge(green_agg, on="barrio_unique_id", how="left")
    master = master.merge(complaints_agg, on="barrio_unique_id", how="left")
    master = master.merge(noise_agg, on="barrio_unique_id", how="left")

    zero_fill_columns = [
        "green_spaces_count",
        "green_area_total_m2",
        "complaints_total",
        "complaints_by_neighbourhood",
        "complaints_most_frequent_tema_count",
    ]
    for column in zero_fill_columns:
        if column in master.columns:
            master[column] = master[column].fillna(0)

    integer_columns = [
        "green_spaces_count",
        "complaints_total",
        "complaints_by_neighbourhood",
        "complaints_most_frequent_tema_count",
    ]
    for column in integer_columns:
        if column in master.columns:
            master[column] = master[column].astype("int64")

    diagnostics = {
        "unmatched_green_barrio_names": unmatched_green["barrio"].dropna().tolist(),
        "complaints": complaints_diagnostics,
        "barrios_without_complaints": master.loc[
            master["complaints_total"].eq(0), ["coddistbar", "nombre"]
        ].to_dict("records"),
        "barrios_without_green_spaces": master.loc[
            master["green_spaces_count"].eq(0), ["coddistbar", "nombre"]
        ].to_dict("records"),
        "barrios_without_noise_overlap": master.loc[
            master["noise_mean"].isna(), ["coddistbar", "nombre"]
        ].to_dict("records"),
    }
    return master, diagnostics


def markdown_table(rows: list[list[Any]], headers: list[str]) -> str:
    """Render a compact Markdown table."""
    output = ["| " + " | ".join(headers) + " |"]
    output.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(output)


def top_rows(
    master: gpd.GeoDataFrame,
    sort_column: str,
    display_columns: list[str],
    n: int = 10,
) -> list[list[Any]]:
    """Return top rows for validation report tables."""
    rows = (
        master.sort_values(sort_column, ascending=False)
        .head(n)[display_columns]
        .copy()
    )
    for column in rows.select_dtypes(include="number").columns:
        rows[column] = rows[column].round(2)
    return rows.values.tolist()


def render_validation_report(
    master: gpd.GeoDataFrame,
    diagnostics: dict[str, Any],
) -> str:
    """Create a Markdown validation report for the processed master table."""
    non_geometry = master.drop(columns="geometry")
    missing_rows = [
        [column, int(non_geometry[column].isna().sum())] for column in non_geometry.columns
    ]

    warnings: list[str] = []
    if diagnostics["unmatched_green_barrio_names"]:
        warnings.append(
            "Some green-space `barrio` names do not match the canonical barrio "
            "names. Green-space indicators were calculated by spatial "
            "intersection, not by direct name join. Unmatched diagnostic names: "
            + ", ".join(diagnostics["unmatched_green_barrio_names"])
        )
    if diagnostics["complaints"]["rows_without_valid_barrio_code"]:
        warnings.append(
            f"{diagnostics['complaints']['rows_without_valid_barrio_code']} complaint "
            "rows had no valid `barrio_localización_código` and were excluded from "
            "neighbourhood-level complaint counts."
        )
    if diagnostics["barrios_without_noise_overlap"]:
        warnings.append(
            "Some barrios have no overlap with the night-noise polygons and keep "
            "missing noise values rather than being filled with 0."
        )

    sections = [
        "# Master Table Validation Report",
        "",
        "Project: **Valencia Urban Equity Compass**",
        "",
        "Generated by `scripts/build_master_table.py`.",
        "",
        "## Output Files",
        "",
        f"- CSV: `{MASTER_CSV_PATH.relative_to(PROJECT_ROOT)}`",
        f"- GeoJSON: `{MASTER_GEOJSON_PATH.relative_to(PROJECT_ROOT)}`",
        "",
        "## Final Table Shape",
        "",
        f"- Number of barrios: `{len(master)}`",
        f"- Number of non-geometry columns: `{len(non_geometry.columns)}`",
        "",
        "## Missing Values",
        "",
        markdown_table(missing_rows, ["Column", "Missing values"]),
        "",
        "## Top 10 Barrios by Green Area",
        "",
        markdown_table(
            top_rows(
                master,
                "green_area_total_m2",
                ["coddistbar", "nombre", "green_spaces_count", "green_area_total_m2"],
            ),
            ["coddistbar", "nombre", "green_spaces_count", "green_area_total_m2"],
        ),
        "",
        "## Top 10 Barrios by Complaints",
        "",
        markdown_table(
            top_rows(
                master,
                "complaints_total",
                [
                    "coddistbar",
                    "nombre",
                    "complaints_total",
                    "complaints_most_frequent_tema",
                ],
            ),
            [
                "coddistbar",
                "nombre",
                "complaints_total",
                "complaints_most_frequent_tema",
            ],
        ),
        "",
        "## Top 10 Barrios by Noise Mean",
        "",
        markdown_table(
            top_rows(
                master,
                "noise_mean",
                ["coddistbar", "nombre", "noise_mean", "noise_max"],
            ),
            ["coddistbar", "nombre", "noise_mean", "noise_max"],
        ),
        "",
        "## Join Diagnostics",
        "",
        f"- Complaint rows total: `{diagnostics['complaints']['rows_total']}`",
        "- Complaint rows with valid barrio code: "
        f"`{diagnostics['complaints']['rows_with_valid_barrio_code']}`",
        "- Complaint rows assigned to a unique barrio: "
        f"`{diagnostics['complaints']['rows_with_unique_barrio_assignment']}`",
        "- Complaint rows unresolved after duplicate-code disambiguation: "
        f"`{diagnostics['complaints']['rows_unresolved_after_duplicate_code_disambiguation']}`",
        "- Complaint rows without valid barrio code: "
        f"`{diagnostics['complaints']['rows_without_valid_barrio_code']}`",
        f"- Barrios without complaints: `{len(diagnostics['barrios_without_complaints'])}`",
        f"- Barrios without green spaces: `{len(diagnostics['barrios_without_green_spaces'])}`",
        f"- Barrios without noise overlap: `{len(diagnostics['barrios_without_noise_overlap'])}`",
        "",
        "## Warnings",
        "",
    ]

    if warnings:
        sections.extend([f"- {warning}" for warning in warnings])
    else:
        sections.append("- No major warnings detected.")

    sections.extend(
        [
            "",
            "## Method Notes",
            "",
            "- `coddistbar` is used as the canonical city-wide barrio code.",
            "- Green-space indicators use spatial intersections between `Espais",
            "  Verds` polygons and barrio polygons. This avoids unreliable joins",
            "  caused by barrio-name variants in `espais_verds.barrio`.",
            "- Complaint counts use the real `barrio_localización_código` field.",
            "- Noise aggregation uses intersections between barrio polygons and",
            "  night-noise polygons. `noise_area_weighted_mean` weights `gridcode`",
            "  by intersection area in EPSG:25830.",
            "- Missing noise values are preserved as missing because no overlap is",
            "  different from measured zero noise.",
            "",
        ]
    )
    return "\n".join(sections)


def write_outputs(master: gpd.GeoDataFrame, diagnostics: dict[str, Any]) -> None:
    """Write processed CSV, GeoJSON, and validation report."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    csv_table = master.drop(columns="geometry").copy()
    csv_table.to_csv(MASTER_CSV_PATH, index=False, encoding="utf-8")
    master.to_file(MASTER_GEOJSON_PATH, driver="GeoJSON")
    REPORT_PATH.write_text(render_validation_report(master, diagnostics), encoding="utf-8")


def main() -> int:
    """Run the master-table build workflow."""
    master, diagnostics = build_master_table()
    write_outputs(master, diagnostics)
    print(f"Wrote {MASTER_CSV_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {MASTER_GEOJSON_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
