"""Build normalized indicators, rankings, and clusters for the project.

Outputs
-------
- data/processed/neighbourhood_indicators.csv
- data/processed/neighbourhood_indicators.geojson
- docs/indicators_and_clustering_report.md

This script does not build Streamlit visualizations.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DS_DEPS = PROJECT_ROOT / "work" / "ds_deps"
if LOCAL_DS_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DS_DEPS))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clustering import CLUSTER_FEATURES, describe_clusters, fit_neighbourhood_clusters
from src.index import (
    DEFAULT_INDEX_WEIGHTS,
    add_normalized_indicators,
    add_rankings,
    calculate_urban_quality_index,
)


MASTER_CSV_PATH = PROJECT_ROOT / "data" / "processed" / "neighbourhood_master_table.csv"
MASTER_GEOJSON_PATH = PROJECT_ROOT / "data" / "processed" / "neighbourhood_master.geojson"
INDICATORS_CSV_PATH = PROJECT_ROOT / "data" / "processed" / "neighbourhood_indicators.csv"
INDICATORS_GEOJSON_PATH = (
    PROJECT_ROOT / "data" / "processed" / "neighbourhood_indicators.geojson"
)
REPORT_PATH = PROJECT_ROOT / "docs" / "indicators_and_clustering_report.md"

GREEN_COLUMN = "green_area_total_m2"
NOISE_COLUMN = "noise_area_weighted_mean"
COMPLAINTS_COLUMN = "complaints_total"


def load_master_table() -> pd.DataFrame:
    """Load the neighbourhood master table with barrio codes as strings."""
    return pd.read_csv(
        MASTER_CSV_PATH,
        dtype={
            "objectid": "string",
            "barrio_unique_id": "string",
            "codbarrio": "string",
            "coddistbar": "string",
            "coddistrit": "string",
        },
    )


def validate_complaint_code_join() -> dict[str, Any]:
    """Validate complaint barrio codes against both barrio code candidates."""
    barrios_payload = json.loads(
        (PROJECT_ROOT / "data" / "raw" / "barris_barrios.geojson").read_text(
            encoding="utf-8"
        )
    )
    barrios = pd.DataFrame(
        [feature["properties"] for feature in barrios_payload.get("features", [])]
    )
    complaints = pd.read_csv(
        PROJECT_ROOT / "data" / "raw" / "quejas_sugerencias.csv",
        sep=";",
        encoding="utf-8-sig",
        dtype="string",
    )

    complaint_codes = set(clean_code(complaints["barrio_localización_código"]).dropna())
    barrios = barrios.copy()
    barrios["codbarrio_clean"] = clean_code(barrios["codbarrio"])
    barrios["coddistbar_clean"] = clean_code(barrios["coddistbar"])
    codbarrio_codes = set(barrios["codbarrio_clean"].dropna())
    coddistbar_codes = set(barrios["coddistbar_clean"].dropna())

    codbarrio_overlap = complaint_codes & codbarrio_codes
    coddistbar_overlap = complaint_codes & coddistbar_codes
    duplicated_coddistbar = (
        barrios.loc[barrios["coddistbar_clean"].duplicated(keep=False)]
        [["coddistbar_clean", "nombre"]]
        .sort_values(["coddistbar_clean", "nombre"])
    )
    correct_key = (
        "coddistbar" if len(coddistbar_overlap) > len(codbarrio_overlap) else "codbarrio"
    )

    return {
        "unique_complaint_neighbourhood_codes": len(complaint_codes),
        "unique_codbarrio_codes": len(codbarrio_codes),
        "unique_coddistbar_codes": len(coddistbar_codes),
        "overlap_with_codbarrio": len(codbarrio_overlap),
        "overlap_with_coddistbar": len(coddistbar_overlap),
        "complaint_codes_not_in_codbarrio": sorted(complaint_codes - codbarrio_codes),
        "complaint_codes_not_in_coddistbar": sorted(complaint_codes - coddistbar_codes),
        "barrios_without_complaint_code_match": sorted(coddistbar_codes - complaint_codes),
        "correct_key": correct_key,
        "coddistbar_is_unique": bool(duplicated_coddistbar.empty),
        "duplicated_coddistbar_rows": duplicated_coddistbar.to_dict("records"),
        "should_change_current_join": not duplicated_coddistbar.empty,
        "recommended_join_strategy": (
            "Use coddistbar for complaint code matching, but aggregate to a unique "
            "barrio row key and disambiguate duplicated coddistbar values by name."
        ),
    }


def clean_code(series: pd.Series) -> pd.Series:
    """Return numeric codes as zero-padded three-character strings."""
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.where(
        cleaned.map(lambda value: False if pd.isna(value) else str(value).isdigit()),
        pd.NA,
    )
    return cleaned.str.zfill(3)


def build_indicator_table(master: pd.DataFrame) -> pd.DataFrame:
    """Create normalized scores, index, ranks, and clusters."""
    indicators = add_normalized_indicators(
        master,
        green_column=GREEN_COLUMN,
        noise_column=NOISE_COLUMN,
        complaints_column=COMPLAINTS_COLUMN,
    )
    indicators = calculate_urban_quality_index(indicators, DEFAULT_INDEX_WEIGHTS)
    indicators = add_rankings(indicators)
    indicators = fit_neighbourhood_clusters(indicators, n_clusters=4)
    return indicators


def write_geojson_with_indicators(indicators: pd.DataFrame) -> None:
    """Merge indicator properties into the master GeoJSON and write output."""
    payload = json.loads(MASTER_GEOJSON_PATH.read_text(encoding="utf-8"))
    merge_key = "barrio_unique_id" if "barrio_unique_id" in indicators.columns else "coddistbar"
    indicator_properties = indicators.set_index(merge_key)
    indicator_properties = indicator_properties.where(pd.notna(indicator_properties), None)
    properties_by_code = indicator_properties.to_dict(orient="index")

    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        if merge_key == "barrio_unique_id":
            code = str(properties.get("barrio_unique_id", ""))
        else:
            code = str(properties.get("coddistbar", "")).zfill(3)
        if code not in properties_by_code:
            raise ValueError(f"GeoJSON feature has no indicator row for {merge_key}={code}")
        properties.update(properties_by_code[code])
        feature["properties"] = properties

    INDICATORS_GEOJSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def markdown_table(rows: list[list[Any]], headers: list[str]) -> str:
    """Render rows as a Markdown table."""
    output = ["| " + " | ".join(headers) + " |"]
    output.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(output)


def table_rows(data: pd.DataFrame, columns: list[str], n: int | None = None) -> list[list[Any]]:
    """Format DataFrame rows for Markdown."""
    frame = data[columns].copy()
    if n is not None:
        frame = frame.head(n)
    for column in frame.select_dtypes(include="number").columns:
        frame[column] = frame[column].round(2)
    return frame.values.tolist()


def render_report(
    indicators: pd.DataFrame,
    cluster_profiles: pd.DataFrame,
    join_validation: dict[str, Any],
) -> str:
    """Render the indicators and clustering report."""
    top10 = indicators.sort_values("urban_quality_index", ascending=False).head(10)
    bottom10 = indicators.sort_values("urban_quality_index", ascending=True).head(10)
    cluster_sizes = (
        indicators.groupby(["cluster", "cluster_label"], as_index=False)
        .size()
        .rename(columns={"size": "neighbourhoods"})
        .sort_values("cluster")
    )

    warnings = [
        "Green areas and complaints are absolute indicators, not per-capita "
        "indicators, because population data has not been added yet.",
        "Complaint counts may be influenced by reporting behaviour and municipal "
        "service intensity, not only by objective urban problems.",
        "Noise scores use the `gridcode` field from the night-noise map; the "
        "score is comparative across barrios, not a direct decibel value.",
    ]
    if join_validation["should_change_current_join"]:
        warnings.append(
            "`coddistbar` is the correct complaint code field, but it is not fully "
            "unique in the barrios layer. The master-table pipeline now uses a "
            "unique barrio row key and name disambiguation for duplicated codes."
        )
    else:
        warnings.append(
            "Complaint-code validation confirms that `coddistbar` is the correct "
            "key. The current master-table join should not be changed."
        )

    sections = [
        "# Indicators and Clustering Report",
        "",
        "Project: **Valencia Urban Equity Compass**",
        "",
        "Generated by `scripts/build_indicators.py`.",
        "",
        "## Complaint Code Validation",
        "",
        "- Unique complaint neighbourhood codes: "
        f"`{join_validation['unique_complaint_neighbourhood_codes']}`",
        "- Overlap with `codbarrio`: "
        f"`{join_validation['overlap_with_codbarrio']}` of "
        f"`{join_validation['unique_codbarrio_codes']}` unique `codbarrio` values",
        "- Overlap with `coddistbar`: "
        f"`{join_validation['overlap_with_coddistbar']}` of "
        f"`{join_validation['unique_coddistbar_codes']}` unique `coddistbar` values",
        f"- Correct key to use: `{join_validation['correct_key']}`",
        f"- Is `coddistbar` unique in the barrio layer? `{join_validation['coddistbar_is_unique']}`",
        "- Should the current join be changed? "
        f"`{join_validation['should_change_current_join']}`",
        f"- Recommended strategy: {join_validation['recommended_join_strategy']}",
        "",
        "## Columns Used",
        "",
        f"- Green area indicator: `{GREEN_COLUMN}`",
        f"- Noise indicator: `{NOISE_COLUMN}`",
        f"- Complaints indicator: `{COMPLAINTS_COLUMN}`",
        f"- Clustering features: `{', '.join(CLUSTER_FEATURES)}`",
        "",
        "## Normalization Method",
        "",
        "Each raw indicator is scaled to a 0-100 min-max score. For negative "
        "indicators, the score is reversed so that higher scores are always "
        "better for urban quality.",
        "",
        "- `green_score`: higher green area means higher score.",
        "- `low_noise_score`: higher noise means lower score.",
        "- `low_complaints_score`: higher complaints means lower score.",
        "",
        "## Index Formula",
        "",
        "`urban_quality_index = 0.40 * green_score + 0.30 * "
        "low_noise_score + 0.30 * low_complaints_score`",
        "",
        "## Top 10 Neighbourhoods by Urban Quality Index",
        "",
        markdown_table(
            table_rows(
                top10,
                [
                    "coddistbar",
                    "nombre",
                    "urban_quality_index",
                    "green_score",
                    "low_noise_score",
                    "low_complaints_score",
                    "cluster_label",
                ],
            ),
            [
                "coddistbar",
                "nombre",
                "urban_quality_index",
                "green_score",
                "low_noise_score",
                "low_complaints_score",
                "cluster_label",
            ],
        ),
        "",
        "## Bottom 10 Neighbourhoods by Urban Quality Index",
        "",
        markdown_table(
            table_rows(
                bottom10,
                [
                    "coddistbar",
                    "nombre",
                    "urban_quality_index",
                    "green_score",
                    "low_noise_score",
                    "low_complaints_score",
                    "cluster_label",
                ],
            ),
            [
                "coddistbar",
                "nombre",
                "urban_quality_index",
                "green_score",
                "low_noise_score",
                "low_complaints_score",
                "cluster_label",
            ],
        ),
        "",
        "## Cluster Sizes",
        "",
        markdown_table(
            table_rows(cluster_sizes, ["cluster", "cluster_label", "neighbourhoods"]),
            ["cluster", "cluster_label", "neighbourhoods"],
        ),
        "",
        "## Cluster Average Profiles",
        "",
        markdown_table(
            table_rows(
                cluster_profiles.sort_values("cluster"),
                [
                    "cluster",
                    "cluster_label",
                    "cluster_size",
                    "green_score_mean",
                    "low_noise_score_mean",
                    "low_complaints_score_mean",
                    "urban_quality_index_mean",
                ],
            ),
            [
                "cluster",
                "cluster_label",
                "cluster_size",
                "green_score_mean",
                "low_noise_score_mean",
                "low_complaints_score_mean",
                "urban_quality_index_mean",
            ],
        ),
        "",
        "## Cluster Labelling Logic",
        "",
        "Cluster IDs come from KMeans and have no inherent meaning. Labels are "
        "derived from cluster averages. A cluster is labelled as green/balanced "
        "only when all three score dimensions are above the overall cluster "
        "profile average. The lowest-index cluster is labelled as low-comfort; "
        "other labels reflect the strongest or weakest score dimensions.",
        "",
        "## Warnings and Limitations",
        "",
    ]
    sections.extend([f"- {warning}" for warning in warnings])
    sections.append("")
    return "\n".join(sections)


def main() -> int:
    """Run the indicator and clustering build workflow."""
    master = load_master_table()
    join_validation = validate_complaint_code_join()
    indicators = build_indicator_table(master)
    cluster_profiles = describe_clusters(indicators)

    INDICATORS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    indicators.to_csv(INDICATORS_CSV_PATH, index=False, encoding="utf-8")
    write_geojson_with_indicators(indicators)
    REPORT_PATH.write_text(
        render_report(indicators, cluster_profiles, join_validation),
        encoding="utf-8",
    )

    print(f"Wrote {INDICATORS_CSV_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {INDICATORS_GEOJSON_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
