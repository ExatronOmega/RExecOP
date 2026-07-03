#!/usr/bin/env python3
from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rexecop.profile.conformance import (  # noqa: E402
    CONFORMANCE_TRACKS,
    validate_profile_conformance,
)


def main() -> int:
    parser = ArgumentParser(description="Validate active profile conformance.")
    parser.add_argument(
        "--track",
        choices=CONFORMANCE_TRACKS,
        default="readonly",
        help="conformance track to validate (default: readonly)",
    )
    args = parser.parse_args()
    result = validate_profile_conformance(
        "tecrax",
        require_reaction_observation=args.track != "mutation",
        track=args.track,
    )
    if result.status != "passed":
        for error in result.errors:
            print(error, file=sys.stderr)
        return 1
    print(
        "profile_conformance_ok:"
        f"track={result.track}:"
        f"profile={result.profile}:"
        f"checked={','.join(result.checked_intents)}:"
        f"skipped={','.join(result.skipped_intents)}:"
        f"mutation_candidates={','.join(result.mutation_candidate_intents)}:"
        f"reaction_observation={','.join(result.reaction_observation_intents)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
