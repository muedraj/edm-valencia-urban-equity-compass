"""Plotting helpers for the Streamlit application."""

from __future__ import annotations

from typing import Iterable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


SCORE_COLUMNS = ["green_score", "low_noise_score", "low_complaints_score"]

DISPLAY_LABELS = {
    "nombre": "Neighbourhood",
    "coddistbar": "Neighbourhood code",
    "coddistrit": "District code",
    "urban_quality_index": "Urban Quality Index",
    "urban_quality_rank": "Overall rank",
    "green_score": "Green score",
    "low_noise_score": "Low-noise score",
    "low_complaints_score": "Low-complaints score",
    "green_area_total_m2": "Green area (m2)",
    "green_spaces_count": "Green spaces",
    "complaints_total": "Total complaints",
    "complaints_most_frequent_tema": "Most frequent complaint topic",
    "complaints_most_frequent_tema_count": "Topic records",
    "noise_area_weighted_mean": "Area-weighted night noise",
    "noise_mean": "Mean night-noise class",
    "cluster_label": "Urban profile",
    "cluster": "Cluster",
}


def label_for(column: str) -> str:
    """Return a human-readable label for a dataset column."""
    return DISPLAY_LABELS.get(column, column.replace("_", " ").title())


def build_kpi_summary(data: pd.DataFrame) -> dict[str, str]:
    """Build formatted KPI values for the app overview."""
    best = data.sort_values("urban_quality_index", ascending=False).iloc[0]
    lowest = data.sort_values("urban_quality_index", ascending=True).iloc[0]
    return {
        "neighbourhoods": f"{len(data):,}",
        "avg_index": f"{data['urban_quality_index'].mean():.1f}",
        "best_name": str(best["nombre"]),
        "best_score": f"{best['urban_quality_index']:.1f}",
        "lowest_name": str(lowest["nombre"]),
        "lowest_score": f"{lowest['urban_quality_index']:.1f}",
        "clusters": f"{data['cluster'].nunique()}",
    }


def create_choropleth_map(
    data: pd.DataFrame,
    geojson: dict,
    metric: str,
    title: str,
) -> go.Figure:
    """Create a Mapbox choropleth from the neighbourhood GeoJSON."""
    map_data = data.copy()
    map_data["barrio_unique_id"] = map_data["barrio_unique_id"].astype(str)
    figure = px.choropleth_mapbox(
        map_data,
        geojson=geojson,
        locations="barrio_unique_id",
        featureidkey="properties.barrio_unique_id",
        color=metric,
        hover_name="nombre",
        hover_data={
            "barrio_unique_id": False,
            "coddistbar": True,
            "urban_quality_index": ":.1f",
            "green_score": ":.1f",
            "low_noise_score": ":.1f",
            "low_complaints_score": ":.1f",
            "complaints_total": ":,",
            "cluster_label": True,
            metric: ":.2f",
        },
        labels={column: label_for(column) for column in map_data.columns},
        color_continuous_scale="Viridis",
        mapbox_style="carto-positron",
        center={"lat": 39.47, "lon": -0.38},
        zoom=10.4,
        opacity=0.74,
        title=f"Map of {title}",
    )
    figure.update_layout(
        margin={"r": 0, "t": 48, "l": 0, "b": 0},
        height=620,
        coloraxis_colorbar={"title": title},
    )
    return figure


def create_score_bar_chart(data: pd.DataFrame) -> go.Figure:
    """Create a grouped bar chart comparing normalized indicator scores."""
    long_data = data.melt(
        id_vars=["nombre"],
        value_vars=SCORE_COLUMNS,
        var_name="indicator",
        value_name="score",
    )
    long_data["indicator"] = long_data["indicator"].map(label_for)
    figure = px.bar(
        long_data,
        x="indicator",
        y="score",
        color="nombre",
        barmode="group",
        range_y=[0, 100],
        title="Normalized Indicator Comparison",
        labels={"indicator": "", "score": "Score (0-100)", "nombre": "Neighbourhood"},
    )
    figure.update_layout(height=420, legend_title_text="Neighbourhood")
    return figure


def create_correlation_heatmap(data: pd.DataFrame, columns: Iterable[str]) -> go.Figure:
    """Create a correlation heatmap for selected numeric indicators."""
    selected = list(columns)
    corr = data[selected].corr(numeric_only=True)
    labels = [label_for(column) for column in corr.columns]
    figure = go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=labels,
            y=labels,
            zmin=-1,
            zmax=1,
            colorscale="RdBu",
            reversescale=True,
            colorbar={"title": "Correlation"},
            text=corr.round(2).values,
            texttemplate="%{text}",
        )
    )
    figure.update_layout(
        title="Correlation Between Urban Indicators",
        height=540,
        margin={"l": 0, "r": 0, "t": 48, "b": 0},
    )
    return figure


def create_ranking_chart(data: pd.DataFrame, metric: str, n: int = 10) -> go.Figure:
    """Create a horizontal top-neighbourhood ranking chart."""
    top = data.sort_values(metric, ascending=False).head(n).sort_values(metric)
    figure = px.bar(
        top,
        x=metric,
        y="nombre",
        orientation="h",
        color=metric,
        color_continuous_scale="Viridis",
        title=f"Top {n} Neighbourhoods by {label_for(metric)}",
        labels={metric: label_for(metric), "nombre": ""},
    )
    figure.update_layout(height=430, showlegend=False, margin={"l": 0, "r": 0})
    return figure


def create_scatterplot(data: pd.DataFrame, x: str, y: str) -> go.Figure:
    """Create a scatterplot with cluster labels."""
    figure = px.scatter(
        data,
        x=x,
        y=y,
        color="cluster_label",
        hover_name="nombre",
        size="urban_quality_index",
        size_max=24,
        title=f"{label_for(y)} vs {label_for(x)}",
        labels={
            x: label_for(x),
            y: label_for(y),
            "cluster_label": "Urban profile",
            "urban_quality_index": "Urban Quality Index",
        },
    )
    figure.update_layout(height=520, legend_title_text="Urban profile")
    return figure


def create_index_distribution(data: pd.DataFrame) -> go.Figure:
    """Create a histogram of the Urban Quality Index."""
    figure = px.histogram(
        data,
        x="urban_quality_index",
        nbins=18,
        color="cluster_label",
        title="Distribution of the Urban Quality Index",
        labels={
            "urban_quality_index": "Urban Quality Index",
            "cluster_label": "Urban profile",
        },
    )
    figure.update_layout(height=430, bargap=0.08, legend_title_text="Urban profile")
    return figure
