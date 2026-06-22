"""Streamlit app for València Urban Equity Compass."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.plots import (
    DISPLAY_LABELS,
    build_kpi_summary,
    create_choropleth_map,
    create_correlation_heatmap,
    create_index_distribution,
    create_ranking_chart,
    create_scatterplot,
    create_score_bar_chart,
    label_for,
)


APP_TITLE = "València Urban Equity Compass"
APP_SUBTITLE = "Neighbourhood quality, environmental stress and civic complaints"
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_CSV = PROJECT_ROOT / "data" / "processed" / "neighbourhood_indicators.csv"
DATA_GEOJSON = PROJECT_ROOT / "data" / "processed" / "neighbourhood_indicators.geojson"

METRIC_OPTIONS = {
    "Urban Quality Index": "urban_quality_index",
    "Green score": "green_score",
    "Low-noise score": "low_noise_score",
    "Low-complaints score": "low_complaints_score",
    "Total complaints": "complaints_total",
    "Area-weighted night noise": "noise_area_weighted_mean",
    "Green area total (m2)": "green_area_total_m2",
}

NUMERIC_ANALYSIS_COLUMNS = [
    "urban_quality_index",
    "green_score",
    "low_noise_score",
    "low_complaints_score",
    "green_area_total_m2",
    "complaints_total",
    "noise_area_weighted_mean",
    "noise_mean",
]

CORE_CORRELATION_COLUMNS = [
    "urban_quality_index",
    "green_score",
    "low_noise_score",
    "low_complaints_score",
]


@st.cache_data
def load_indicator_data() -> tuple[pd.DataFrame, dict]:
    """Load processed indicator CSV and GeoJSON."""
    data = pd.read_csv(
        DATA_CSV,
        dtype={
            "objectid": "string",
            "barrio_unique_id": "string",
            "codbarrio": "string",
            "coddistbar": "string",
            "coddistrit": "string",
        },
    )
    data["barrio_unique_id"] = data["barrio_unique_id"].astype(str)
    data["coddistbar"] = data["coddistbar"].str.zfill(3)
    data["codbarrio"] = data["codbarrio"].str.zfill(3)
    data["coddistrit"] = data["coddistrit"].astype(str)

    if "complaints_most_frequent_tema" in data:
        data["complaints_most_frequent_tema"] = data[
            "complaints_most_frequent_tema"
        ].fillna("No complaint topic assigned")

    numeric_columns = data.select_dtypes(include="number").columns
    data[numeric_columns] = data[numeric_columns].fillna(0)

    with DATA_GEOJSON.open(encoding="utf-8") as file:
        geojson = json.load(file)
    return data, geojson


def filter_geojson(geojson: dict, barrio_ids: set[str]) -> dict:
    """Return a GeoJSON FeatureCollection filtered to selected barrio IDs."""
    return {
        "type": "FeatureCollection",
        "features": [
            feature
            for feature in geojson.get("features", [])
            if str(feature.get("properties", {}).get("barrio_unique_id")) in barrio_ids
        ],
    }


def available_options(options: dict[str, str], data: pd.DataFrame) -> dict[str, str]:
    """Keep only UI options backed by real dataset columns."""
    return {label: column for label, column in options.items() if column in data.columns}


def display_table(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Return a table with user-facing column labels."""
    existing = [column for column in columns if column in data.columns]
    table = data[existing].copy()
    return table.rename(columns={column: label_for(column) for column in existing})


def district_filter_options(data: pd.DataFrame) -> dict[str, str]:
    """Return user-friendly district filter labels mapped to stored codes."""
    if "coddistrit" not in data.columns:
        return {"All districts": "All districts"}

    possible_name_columns = [
        "district_name",
        "nombre_distrito",
        "nom_districte",
        "distrito",
        "district",
    ]
    name_column = next(
        (column for column in possible_name_columns if column in data.columns),
        None,
    )

    district_data = data[["coddistrit"]].dropna().copy()
    district_data["coddistrit"] = district_data["coddistrit"].astype(str)
    if name_column:
        district_data[name_column] = data[name_column]
        district_data = district_data.drop_duplicates("coddistrit")
        labels = {
            f"{row[name_column]} ({row['coddistrit']})": row["coddistrit"]
            for _, row in district_data.sort_values("coddistrit").iterrows()
            if pd.notna(row[name_column])
        }
    else:
        labels = {
            f"District {code}": code
            for code in sorted(
                district_data["coddistrit"].unique(),
                key=lambda value: int(value) if value.isdigit() else value,
            )
        }
    return {"All districts": "All districts", **labels}


def render_header() -> None:
    """Render consistent page header."""
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)


def render_sidebar() -> str:
    """Render sidebar navigation."""
    st.sidebar.title("App navigation")
    section = st.sidebar.radio(
        "Choose a section",
        (
            "Overview",
            "Urban Quality Map",
            "Rankings",
            "Neighbourhood Profile",
            "Data Science",
            "Methodology",
        ),
    )
    st.sidebar.divider()
    st.sidebar.markdown(
        """
        **Data scope**

        88 neighbourhood geometries with green-space, night-noise and complaint
        indicators aggregated to barrio level.
        """
    )
    return section


def render_overview(data: pd.DataFrame) -> None:
    """Render the overview page."""
    st.subheader("Urban Equity Overview")
    st.markdown(
        """
        This dashboard compares neighbourhoods in València using official open
        data. It is designed as a decision-support view: users can inspect where
        green-space comfort, night-noise pressure and civic complaint intensity
        differ across the city.
        """
    )

    kpis = build_kpi_summary(data)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Neighbourhoods", kpis["neighbourhoods"])
    col2.metric("Average Index", kpis["avg_index"])
    col3.metric("Best index", kpis["best_score"])
    col3.caption(kpis["best_name"])
    col4.metric("Lowest index", kpis["lowest_score"])
    col4.caption(kpis["lowest_name"])
    col5.metric("Urban profiles", kpis["clusters"])

    st.divider()
    left, right = st.columns([1.25, 1])
    with left:
        st.subheader("Top Urban Quality Scores")
        st.plotly_chart(
            create_ranking_chart(data, "urban_quality_index", n=10),
            use_container_width=True,
        )
        st.caption(
            "The chart ranks neighbourhoods by the composite Urban Quality Index."
        )
    with right:
        st.subheader("How the Index Works")
        st.markdown(
            """
            The index combines three normalized scores:

            - 40% green-space score
            - 30% low-noise score
            - 30% low-complaints score

            Scores range from 0 to 100. For noise and complaints, the direction
            is reversed so that higher values always indicate better urban
            quality.
            """
        )
        cluster_table = (
            data.groupby("cluster_label", as_index=False)
            .size()
            .rename(columns={"cluster_label": "Urban profile", "size": "Neighbourhoods"})
            .sort_values("Neighbourhoods", ascending=False)
        )
        st.dataframe(cluster_table, use_container_width=True, hide_index=True)

    st.info(
        "Interpretation: the index is most useful for comparing relative patterns "
        "between neighbourhoods, not for declaring a single definitive winner."
    )


def render_map(data: pd.DataFrame, geojson: dict) -> None:
    """Render the interactive choropleth map."""
    st.subheader("Interactive Urban Quality Map")
    metric_options = available_options(METRIC_OPTIONS, data)
    if not metric_options:
        st.error("No numeric map metrics are available in the processed dataset.")
        return

    district_options = district_filter_options(data)
    col1, col2 = st.columns([1, 1])
    selected_metric_label = col1.selectbox("Map metric", list(metric_options))
    selected_district_label = col2.selectbox("District filter", list(district_options))
    selected_district = district_options[selected_district_label]
    metric = metric_options[selected_metric_label]

    filtered = data.copy()
    if selected_district != "All districts":
        filtered = filtered[filtered["coddistrit"] == selected_district]
    if filtered.empty:
        st.warning("No neighbourhoods match the selected filter.")
        return

    filtered_geojson = filter_geojson(geojson, set(filtered["barrio_unique_id"]))
    st.plotly_chart(
        create_choropleth_map(
            filtered,
            filtered_geojson,
            metric,
            selected_metric_label,
        ),
        use_container_width=True,
    )
    st.caption(
        "Hover over a neighbourhood to inspect its index, component scores, "
        "complaint count and urban profile. District filtering uses the official "
        "district code from the barrios layer."
    )
    st.info(
        "Interpretation: spatial clusters of low scores point to areas where "
        "urban comfort pressures concentrate geographically."
    )


def render_rankings(data: pd.DataFrame) -> None:
    """Render ranking tables."""
    st.subheader("Neighbourhood Rankings")
    sort_options = available_options(
        {
            "Urban Quality Index": "urban_quality_index",
            "Green score": "green_score",
            "Low-noise score": "low_noise_score",
            "Low-complaints score": "low_complaints_score",
            "Total complaints": "complaints_total",
            "Area-weighted night noise": "noise_area_weighted_mean",
        },
        data,
    )
    selected_label = st.selectbox("Sort ranking by", list(sort_options))
    sort_column = sort_options[selected_label]
    ascending = sort_column in {"complaints_total", "noise_area_weighted_mean"}

    display_columns = [
        "urban_quality_rank",
        "nombre",
        "coddistbar",
        "coddistrit",
        "urban_quality_index",
        "green_score",
        "low_noise_score",
        "low_complaints_score",
        "complaints_total",
        "noise_area_weighted_mean",
        "green_area_total_m2",
        "cluster_label",
    ]
    ranked = data.sort_values(sort_column, ascending=ascending)
    st.dataframe(
        display_table(ranked, display_columns),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download full processed indicators CSV",
        data=data.to_csv(index=False).encode("utf-8"),
        file_name="neighbourhood_indicators.csv",
        mime="text/csv",
    )

    top, bottom = st.columns(2)
    with top:
        st.markdown("#### Top 10 by Urban Quality Index")
        top10 = data.sort_values("urban_quality_index", ascending=False).head(10)
        st.dataframe(
            display_table(top10, ["nombre", "urban_quality_index", "cluster_label"]),
            use_container_width=True,
            hide_index=True,
        )
    with bottom:
        st.markdown("#### Bottom 10 by Urban Quality Index")
        bottom10 = data.sort_values("urban_quality_index", ascending=True).head(10)
        st.dataframe(
            display_table(bottom10, ["nombre", "urban_quality_index", "cluster_label"]),
            use_container_width=True,
            hide_index=True,
        )

    st.info(
        "Interpretation: rankings are a quick screening tool; the component "
        "scores should be checked before drawing policy conclusions."
    )


def render_profile(data: pd.DataFrame) -> None:
    """Render neighbourhood profile comparison."""
    st.subheader("Neighbourhood Profile")
    names = data.sort_values("nombre")["nombre"].tolist()
    default_name = data.sort_values("urban_quality_rank").iloc[0]["nombre"]
    selected = st.multiselect(
        "Select one or two neighbourhoods",
        names,
        default=[default_name],
        max_selections=2,
    )
    if not selected:
        st.info("Select at least one neighbourhood to view its profile.")
        return

    selected_data = data[data["nombre"].isin(selected)].copy()
    if selected_data.empty:
        st.warning("The selected neighbourhood could not be found.")
        return

    st.plotly_chart(create_score_bar_chart(selected_data), use_container_width=True)
    st.caption("Comparison of normalized component scores. All scores range from 0 to 100.")

    for _, row in selected_data.sort_values("nombre").iterrows():
        st.markdown(f"#### {row['nombre']}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Urban Quality Index", f"{row['urban_quality_index']:.1f}")
        col2.metric("Overall rank", f"#{int(row['urban_quality_rank'])}")
        col3.metric("Cluster", f"{int(row['cluster'])}")
        col3.caption(str(row["cluster_label"]))
        col4.metric("Complaints", f"{int(row['complaints_total']):,}")
        st.write(
            "Most frequent complaint topic: "
            f"**{row['complaints_most_frequent_tema']}** "
            f"({int(row['complaints_most_frequent_tema_count'])} records)."
        )

    st.info(
        "Interpretation: comparing one or two neighbourhoods reveals whether "
        "differences come mainly from greenery, night noise or complaint pressure."
    )


def render_data_science(data: pd.DataFrame) -> None:
    """Render data science diagnostics."""
    st.subheader("Data Science Layer")
    st.markdown(
        """
        The analytical layer turns raw neighbourhood indicators into comparable
        scores, an Urban Quality Index, rankings and KMeans urban profiles.
        These views are included to make the methodology inspectable rather than
        hiding the model behind a single score.
        """
    )

    available_numeric = [column for column in NUMERIC_ANALYSIS_COLUMNS if column in data]
    heatmap_columns = [
        column for column in CORE_CORRELATION_COLUMNS if column in data.columns
    ]
    if len(heatmap_columns) >= 2:
        st.markdown("#### Correlation Heatmap")
        st.plotly_chart(
            create_correlation_heatmap(data, heatmap_columns),
            use_container_width=True,
        )
        st.caption(
            "Correlation among the composite index and its three normalized "
            "component scores."
        )

    else:
        st.warning("Not enough core score columns are available for correlation analysis.")

    if len(available_numeric) >= 2:
        col1, col2 = st.columns(2)
        x_axis = col1.selectbox(
            "Scatterplot X axis",
            available_numeric,
            format_func=label_for,
            index=min(1, len(available_numeric) - 1),
        )
        y_axis = col2.selectbox(
            "Scatterplot Y axis",
            available_numeric,
            format_func=label_for,
            index=available_numeric.index("urban_quality_index")
            if "urban_quality_index" in available_numeric
            else 0,
        )
        st.plotly_chart(create_scatterplot(data, x_axis, y_axis), use_container_width=True)
    else:
        st.warning("Not enough numeric columns are available for scatterplot analysis.")

    left, right = st.columns([1, 1])
    with left:
        st.markdown("#### Cluster Summary")
        cluster_summary = (
            data.groupby(["cluster", "cluster_label"], as_index=False)
            .agg(
                neighbourhoods=("nombre", "count"),
                avg_green_score=("green_score", "mean"),
                avg_low_noise_score=("low_noise_score", "mean"),
                avg_low_complaints_score=("low_complaints_score", "mean"),
                avg_urban_quality_index=("urban_quality_index", "mean"),
            )
            .round(2)
            .sort_values("cluster")
            .rename(
                columns={
                    "cluster": "Cluster",
                    "cluster_label": "Urban profile",
                    "neighbourhoods": "Neighbourhoods",
                    "avg_green_score": "Average green score",
                    "avg_low_noise_score": "Average low-noise score",
                    "avg_low_complaints_score": "Average low-complaints score",
                    "avg_urban_quality_index": "Average Urban Quality Index",
                }
            )
        )
        st.dataframe(cluster_summary, use_container_width=True, hide_index=True)
    with right:
        st.markdown("#### Index Distribution")
        st.plotly_chart(create_index_distribution(data), use_container_width=True)

    st.info(
        "Interpretation: the diagnostics make the index transparent by showing "
        "how scores relate to each other and how KMeans groups similar profiles."
    )


def render_methodology() -> None:
    """Render project methodology."""
    st.subheader("Methodology and Limitations")
    st.markdown(
        """
        **Datasets used**

        The application uses official open data for València: neighbourhood
        boundaries, district boundaries, green-space polygons, the night-noise
        map and citizen complaints/suggestions. The deployed app reads the
        processed indicator files generated from those sources.

        **Spatial aggregation**

        The official barrios layer is the canonical geography. Green-space
        polygons are intersected with barrio polygons to calculate total green
        area per neighbourhood. Night-noise polygons are also intersected with
        barrios; `gridcode` is averaged with intersection-area weighting to
        produce the area-weighted night-noise indicator.

        **Complaint-code validation**

        Complaint records provide `barrio_localización_código`. Validation
        showed that this code matches `coddistbar`, not `codbarrio`. One
        `coddistbar` value is duplicated in the barrio layer, so the pipeline
        keeps a unique barrio row identifier and disambiguates the duplicated
        complaint code using the complaint barrio name.

        **Normalization**

        Green area, night noise and complaints use different units, so the app
        scales each indicator to a 0-100 score. For noise and complaints, the
        direction is reversed: high raw noise or high raw complaints become a
        lower score.

        **Urban Quality Index**

        `Urban Quality Index = 0.40 * green score + 0.30 * low-noise score + 0.30 * low-complaints score`

        **KMeans clustering**

        KMeans with 4 clusters groups neighbourhoods using the three normalized
        score dimensions. Cluster labels are assigned from cluster-average
        profiles, so the names describe the observed strengths or weaknesses of
        each group.

        **Limitations**

        - Green area and complaints are absolute values, not per-capita values,
          because population data is not included yet.
        - Complaints without a valid neighbourhood code are excluded from
          neighbourhood-level complaint indicators.
        - Complaint volume can reflect reporting behaviour and municipal service
          intensity, not only objective urban problems.
        - The index weights are methodological choices and should be tested with
          sensitivity analysis.
        - The index is a comparative tool, not a definitive quality-of-life
          measurement.
        """
    )


def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=":cityscape:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    data, geojson = load_indicator_data()
    if data.empty:
        st.error("The processed indicators dataset is empty.")
        st.stop()

    section = render_sidebar()
    render_header()

    if section == "Overview":
        render_overview(data)
    elif section == "Urban Quality Map":
        render_map(data, geojson)
    elif section == "Rankings":
        render_rankings(data)
    elif section == "Neighbourhood Profile":
        render_profile(data)
    elif section == "Data Science":
        render_data_science(data)
    elif section == "Methodology":
        render_methodology()


if __name__ == "__main__":
    main()
