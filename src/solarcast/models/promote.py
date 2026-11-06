"""[Member 2 + 3] Promotion gate for `solarcast-tft` in the MLflow Model Registry (DagsHub).

D1 requires a registered model in the **Staging** (or Production) stage, so use registry
STAGES. MLflow marks them deprecated, but MLflow 3.x and DagsHub still support them:
    MlflowClient().transition_model_version_stage("solarcast-tft", version, "Staging")
Also set aliases (@staging / @production / @previous), which newer MLflow tooling and the API
(MODEL_ALIAS in .env) use.

Flow: a new candidate goes to Staging. Promote Staging -> Production only if it meets
params.promotion against the current Production version. The old version gets @previous, so
rollback is just re-pointing the alias.
"""


def compare_with_production(candidate_run_id: str) -> bool:
    raise NotImplementedError


def promote(candidate_run_id: str) -> None:
    raise NotImplementedError
