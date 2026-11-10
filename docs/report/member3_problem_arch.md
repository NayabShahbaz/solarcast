# Problem and architecture

## Problem

Lahore households with net-metered rooftop solar need to know **how much they will generate
tomorrow, hour by hour**, to plan heavy loads around it. SolarCast forecasts the next 24 hours of
generation in kWh, with an uncertainty band (p10 / p50 / p90), from weather inputs. The model is
trained per kW of installed capacity, so one model serves any system size.

## D1 pipeline

The core pipeline is a set of named DVC stages, rebuilt end to end by `dvc repro` (Figure 1):

```
Open-Meteo + PVGIS (+ NASA POWER cross-check)
   ▼
ingest ─► preprocess ─► validate (Pandera: schema, nulls, ranges)   data versioned with DVC on DagsHub
   ▼
train_baseline ─┐
train_tft ──────┴─► evaluate        every run logged to MLflow on DagsHub
   ▼
MLflow Model Registry: solarcast-tft (Staging)
```

*Figure 1: SolarCast D1 pipeline.*

The REST API, Docker deployment and monitoring come in later deliverables.
