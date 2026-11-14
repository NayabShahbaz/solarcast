# Model workflow

Run commands from the repository root using Python 3.10.
The tested environment uses CPU PyTorch 2.5.1, Lightning 2.5.0,
PyTorch Forecasting 1.3.0 and MLflow 2.22.5.

## Setup in Windows PowerShell

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt --extra-index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e .
$env:Path = "$(Resolve-Path .venv\Scripts);$env:Path"
```

Copy .env.example to .env and enter your own DagsHub username/token.
Keep the shared repository owner and repository name unchanged.
Configure DVC credentials locally; never commit credentials.

## Retrieve and run

```powershell
dvc pull data/processed
dvc repro --single-item train_baseline train_tft evaluate
```

If the stages are cached, force model-stage execution with:

```powershell
dvc repro --single-item --force train_baseline train_tft evaluate
```

Training creates remote MLflow runs and registers a new solarcast-tft
version in Staging. Evaluation logs validation/test metrics to those runs.

## Outputs

- models/baselines: fitted baseline and run metadata
- models/tft: TFT checkpoints, fitted dataset parameters and run metadata
- reports/evaluation: hourly validation/test predictions
- reports/eval.json: test metrics for both models

Models and prediction files are DVC outputs, not Git files.
Use dvc push train_baseline train_tft evaluate to upload them.

The main comparison uses daylight MAE/RMSE in kWh.
All-hour and per-kW metrics are also recorded.
All reported results currently use PVGIS-simulated generation.

The model-stage workflow has been executed successfully.
Full dvc repro from ingestion remains a team integration check.