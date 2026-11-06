# Data workflow (Member 1)

> Week 4 deliverable — fill this in as the pipeline is built.

## Get the exact dataset version someone else used
```bash
git checkout <commit-or-tag>
dvc pull
```

## Run the pipeline
```bash
python -m solarcast.flows.ingestion_flow      # ingest -> validate -> preprocess
python -m solarcast.flows.training_flow       # calls Member 2's train/evaluate
python -m solarcast.flows.retraining_flow     # drift check -> retrain if triggered
```

## Diagnosing a failed run
TODO: where Prefect logs live, what each validation error means.
