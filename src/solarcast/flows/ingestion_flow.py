"""[Member 1] ingestion -> validation -> preprocessing. Runs daily on a Prefect schedule.

Run locally:  python -m solarcast.flows.ingestion_flow
"""

from prefect import flow, task


@task(retries=2, retry_delay_seconds=60)
def ingest():
    raise NotImplementedError


@task
def validate(df):
    raise NotImplementedError


@task
def preprocess(df):
    raise NotImplementedError


@flow(name="solarcast-ingestion", log_prints=True)
def ingestion_flow():
    df = ingest()
    df = validate(df)
    return preprocess(df)


if __name__ == "__main__":
    ingestion_flow()
