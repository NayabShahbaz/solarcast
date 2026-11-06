"""[Member 2 + 3] Promotion gate: candidate TFT vs the version with alias @production.

Promote only if the candidate meets params.promotion. On promotion, move @production to the
candidate and @previous to the old version, so rollback is just re-pointing the alias.
"""


def compare_with_production(candidate_run_id: str) -> bool:
    raise NotImplementedError


def promote(candidate_run_id: str) -> None:
    raise NotImplementedError
