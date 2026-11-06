"""[Member 1 + 2] Wraps the train/evaluate entry points (Member 2) so Prefect can call them."""

from prefect import flow


@flow(name="solarcast-training", log_prints=True)
def training_flow(dataset_version: str | None = None):
    # from solarcast.models.train import train
    # from solarcast.models.evaluate import evaluate
    raise NotImplementedError


if __name__ == "__main__":
    training_flow()
