# València Urban Equity Compass

**Interactive Streamlit app for analysing neighbourhood-level urban quality,
environmental stress and civic complaints in València.**

## Submission Links

- Online app: **TODO: add Streamlit Cloud link**
- Video demo: **TODO: add demo video link**
- Source code: **TODO: add GitHub repository link**

## Author and Course

- Author: **TODO: add student name**
- Course: **EDM**
- Assignment: Final project, interactive urban data application

## Objective

The objective of this project is to create an interactive decision-support app
that compares València neighbourhoods using open urban data. The app helps users
identify neighbourhoods with stronger or weaker urban-quality profiles based on
green-space availability, night-noise pressure and citizen complaint intensity.

The project is designed to satisfy the subject requirements through:

- An interactive Streamlit application.
- Official open data sources.
- Reproducible data inspection and preprocessing scripts.
- Geospatial aggregation.
- Normalized indicators.
- A custom Urban Quality Index.
- Rankings, maps, comparisons, correlations and clustering.

## Data Sources

The current version uses official València open datasets:

- **Barris / Barrios:** neighbourhood boundaries.
- **Districtes / Distritos:** district reference layer.
- **Espais Verds / Espacios Verdes:** green-space polygons and area attributes.
- **Mapa soroll nit / Mapa ruido noche:** night-noise polygons using `gridcode`.
- **Quejas y Sugerencias:** citizen complaint records.

No additional datasets are required to run the deployed app. The app reads the
processed files stored in `data/processed/`.

## Methodology

1. Download raw data from official open data exports.
2. Inspect rows, columns, data types, missing values, identifiers and geometry.
3. Use the official barrios layer as the canonical neighbourhood geometry.
4. Aggregate green-space polygons to barrios through spatial intersection.
5. Aggregate night-noise polygons to barrios through area-weighted spatial
   overlay.
6. Validate complaint neighbourhood codes and aggregate complaints to barrio
   level.
7. Normalize indicators to a 0-100 scale.
8. Reverse negative indicators so that higher scores always mean better urban
   quality.
9. Calculate the Urban Quality Index:

```text
Urban Quality Index =
0.40 * green_score
+ 0.30 * low_noise_score
+ 0.30 * low_complaints_score
```

10. Rank neighbourhoods by the index and component indicators.
11. Apply KMeans clustering with 4 clusters using the normalized scores.
12. Present the results interactively in Streamlit.

## Complaint-Code Validation

The complaint dataset contains `barrio_localización_código`. Validation showed
that this code matches `coddistbar`, not `codbarrio`.

One `coddistbar` value is duplicated in the barrios layer, so the pipeline keeps
a unique `barrio_unique_id` and disambiguates the duplicated complaint code by
using the complaint barrio name. This avoids copying the same complaint records
onto two different neighbourhood geometries.

## App Features

- **Overview:** project explanation, KPI cards, index formula and cluster count.
- **Urban Quality Map:** interactive choropleth map with metric and district
  filters.
- **Rankings:** sortable ranking table, top/bottom 10 views and CSV download.
- **Neighbourhood Profile:** comparison of one or two neighbourhoods.
- **Data Science:** correlation heatmap, scatterplot, cluster summary and index
  distribution.
- **Methodology:** data sources, spatial aggregation, code validation, index
  formula, clustering and limitations.

## Folder Structure

```text
.
├── app.py
├── requirements.txt
├── README.md
├── data/
│   ├── raw/
│   └── processed/
│       ├── neighbourhood_master_table.csv
│       ├── neighbourhood_master.geojson
│       ├── neighbourhood_indicators.csv
│       └── neighbourhood_indicators.geojson
├── docs/
│   ├── data_inspection_report.md
│   ├── master_table_validation_report.md
│   ├── indicators_and_clustering_report.md
│   └── final_submission_checklist.md
├── notebooks/
│   └── 01_download_and_inspect_data.py
├── scripts/
│   ├── build_master_table.py
│   └── build_indicators.py
└── src/
    ├── clustering.py
    ├── data_loader.py
    ├── features.py
    ├── index.py
    ├── plots.py
    └── preprocessing.py
```

## How to Run Locally

Install the app dependencies:

```bash
pip install -r requirements.txt
```

Run the Streamlit app:

```bash
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## Deployment Instructions

The intended deployment target is **Streamlit Cloud**.

1. Push the repository to GitHub.
2. Confirm `requirements.txt` is present at the repository root.
3. Confirm the processed files exist in `data/processed/`.
4. In Streamlit Cloud, create a new app from the GitHub repository.
5. Set the entry point to `app.py`.
6. Deploy and add the public app URL to this README.

## Processed Outputs

The deployed app uses:

- `data/processed/neighbourhood_indicators.csv`
- `data/processed/neighbourhood_indicators.geojson`

Supporting reports:

- `docs/data_inspection_report.md`
- `docs/master_table_validation_report.md`
- `docs/indicators_and_clustering_report.md`

## Limitations

- Green area and complaints are absolute indicators, not per-capita indicators,
  because population data has not been included yet.
- Complaints without a valid neighbourhood code are excluded from
  neighbourhood-level complaint indicators.
- Complaint volume can reflect reporting behaviour and municipal service
  intensity, not only objective urban problems.
- The Urban Quality Index weights are methodological choices and should be
  tested with sensitivity analysis.
- The index is a comparative tool, not a definitive quality-of-life measure.
