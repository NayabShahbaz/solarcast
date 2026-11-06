"""[Member 2 + 3] Promotion gate: candidate TFT vs current Production (params.promotion).

Promote only if the candidate meets the threshold; previous version stays available for rollback.
"""


def compare_with_production(candidate_run_id: str) -> bool:
    raise NotImplementedError


def promote(candidate_run_id: str) -> None:
    raise NotImplementedError
