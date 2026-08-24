"""Debug runner for support-preference diversification live scenario."""

from __future__ import annotations

from recommender.calc_service import CalcService
from tests.recommender.test_support_preference_live import (
    REPO,
    rain_core_draft,
    run_support_preference_pipeline,
    support_discovery_state,
)


def main() -> None:
    state = support_discovery_state(rain_core_draft())
    with CalcService(repo_root=REPO):
        result = run_support_preference_pipeline(state)
    options = [row.species for row in result["presentation"].candidates]
    print("options:", options)


if __name__ == "__main__":
    main()
