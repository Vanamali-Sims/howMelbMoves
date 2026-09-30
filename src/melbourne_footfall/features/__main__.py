"""CLI: python -m melbourne_footfall.features"""

from __future__ import annotations

import json
import logging

from melbourne_footfall.features.build import build_feature_matrix


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    frame = build_feature_matrix()
    payload = {
        "rows": int(len(frame)),
        "precincts": int(frame["precinct"].nunique()),
        "min_date": frame["sensing_date"].min().isoformat(),
        "max_date": frame["sensing_date"].max().isoformat(),
    }
    print(json.dumps({"features": payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
