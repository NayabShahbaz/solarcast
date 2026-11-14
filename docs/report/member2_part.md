# Models and experiment tracking

SolarCast uses Linear Regression as the baseline and a small Temporal
Fusion Transformer implemented with PyTorch Forecasting as the main model.
Both predict the next 24 hourly generation values using 168 hours of history.
Forecasts start at midnight Lahore time. The baseline uses cyclic calendar
features and generation from yesterday and last week. TFT uses historical
generation and weather, with calendar features as known future inputs.
Future observed weather is not supplied as a forecast.

The dataset contains 35,064 hourly records for a simulated 10 kW PVGIS
system in Lahore from 2020 to 2023. Training uses 2020–2022, validation uses
the first half of 2023, and testing uses the second half. Windows crossing
missing hours or split boundaries are excluded. Preprocessing is fitted
on training data only. Models learn generation per kW, with predictions
converted back to kWh for evaluation.

TFT uses hidden size 16, two attention heads, dropout 0.1, learning rate
0.003, batch size 64 and up to five CPU training epochs, with seed 42.
It predicts the 0.1, 0.5 and 0.9 quantiles. Both models are evaluated on
the same 4,392 test hours, including 2,193 daylight hours.

| Model | Test daylight MAE in kWh | Test daylight RMSE in kWh |
|---|---:|---:|
| Linear Regression | 0.4566 | 0.7490 |
| TFT | 0.4665 | 0.8068 |

Linear Regression achieved slightly lower daylight test errors. TFT remains
the main model to satisfy the Transformer-based project approach. These
results describe simulated generation, not measured household performance.

Parameters, dataset fingerprints, metrics and model artifacts are logged
to remote DagsHub MLflow. The main model is registered as solarcast-tft,
with version 2 in Staging at the time of this report.

The train_baseline, train_tft and evaluate stages completed through DVC.
A second execution skipped all three unchanged stages, and their artifacts
were pushed to the DVC remote. Full reproduction from source ingestion
remains a team integration check.

GitHub: https://github.com/NayabShahbaz/solarcast
MLflow: https://dagshub.com/NayabShahbaz/solarcast.mlflow

Screenshots:
- mlflow_runs.png
- mlflow_registry_staging.png
- dvc_dag.png