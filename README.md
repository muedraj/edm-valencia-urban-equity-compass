# València Urban Equity Compass

**Interactive Streamlit app for analysing neighbourhood-level urban quality,
environmental stress and civic complaints in València.**

## Submission Links

- Online app: https://edm-valencia-urban-equity-compass.streamlit.app
- Video demo: https://drive.google.com/file/d/1ofTEhWXED2sOJDahgJQgwPSpiB3Nm94z/view?usp=sharing
- Source code: https://github.com/muedraj/edm-valencia-urban-equity-compass

## Author and Course

- Author: **Jorge Muedra Vela**
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

## Raw Data and Reproducibility

The repository includes the processed datasets required by the deployed
application, but the original raw files are intentionally not stored in GitHub.

All raw datasets can be downloaded again from the official València Open Data
Portal by running:

```bash
python notebooks/01_download_and_inspect_data.py
```

This script retrieves the original resources, preserves their real column names
and saves them locally in `data/raw/`.

| Dataset | Raw file | Format | Rows | Purpose |
| --- | --- | ---: | ---: | --- |
| Barris / Barrios | `barris_barrios.geojson` | GeoJSON | 88 | Neighbourhood boundaries |
| Districtes / Distritos | `districtes_distritos.geojson` | GeoJSON | 22 | District reference |
| Espais Verds | `espais_verds.geojson` | GeoJSON | 807 | Green-space polygons |
| Mapa de ruido nocturno | `mapa_soroll_nit.geojson` | GeoJSON | 54 | Night-noise polygons |
| Quejas y Sugerencias | `quejas_sugerencias.csv` | CSV | 90,005 | Citizen complaints |

The complete inspection of the original schemas, missing values, identifiers
and geometries is available in `docs/data_inspection_report.md`.

The complete transformation process is therefore traceable:

```text
Official open-data sources
        |
        v
notebooks/01_download_and_inspect_data.py
        |
        v
data/raw/
Original downloaded files
        |
        v
scripts/build_master_table.py
        |
        v
neighbourhood_master_table.csv
neighbourhood_master.geojson
        |
        v
scripts/build_indicators.py
        |
        v
neighbourhood_indicators.csv
neighbourhood_indicators.geojson
        |
        v
app.py
Deployed Streamlit application
```

To reproduce the processed outputs from the downloaded raw data, run the
following commands from the project root:

```bash
python notebooks/01_download_and_inspect_data.py
python scripts/build_master_table.py
python scripts/build_indicators.py
```

Raw files are excluded from Git because they can be regenerated from their
official sources and would unnecessarily duplicate external data. The download
script, source identifiers, inspection report and processing scripts are
included so that the complete pipeline can be reviewed and reproduced.

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
│   ├── raw/          # generated locally and ignored in GitHub
│   └── processed/    # processed files used by the deployed app
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

The deployed Streamlit app only needs the lightweight dependencies listed in
`requirements.txt`.

Install the app dependencies:

```bash
pip install -r requirements.txt

Run the Streamlit app:

streamlit run app.py

If the streamlit command is not recognized on Windows, run:

python -m streamlit run app.py

To reproduce the full preprocessing and geospatial pipeline, install the
additional pipeline dependencies:

pip install -r requirements-pipeline.txt
```

## Deployment

The app is deployed on Streamlit Cloud:

https://edm-valencia-urban-equity-compass.streamlit.app

Deployment configuration:

- Repository: `muedraj/edm-valencia-urban-equity-compass`
- Branch: `main`
- Main file: `app.py`
- Dependencies file: `requirements.txt`

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
