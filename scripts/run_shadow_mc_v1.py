#!/usr/bin/env python3
"""
Dry-run shadow Monte Carlo v1 on a synthetic field (stdout JSON).

Does not touch the database or live pipelines unless you import from your own code.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.models.prob_engine_v1.shadow_dispatch import run_shadow_field_simulation  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Shadow MC v1/v2 dry run (stdout JSON)")
    p.add_argument("--engine", choices=("auto", "v1", "v2"), default="auto")
    p.add_argument("--field-size", type=int, default=80)
    p.add_argument("--n-sims", type=int, default=500)
    p.add_argument("--noise", type=float, default=2.5)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    field = [(f"player_{i}", 70.0 + (args.field_size - i) * 0.05) for i in range(args.field_size)]
    if args.engine == "v1":
        from src.models.prob_engine_v1.shadow_mc import run_field_simulation_v1

        out = run_field_simulation_v1(
            field,
            n_sims=args.n_sims,
            score_noise=args.noise,
            seed=args.seed,
        )
    elif args.engine == "v2":
        from src.models.prob_engine_v1.shadow_mc_v2 import run_field_simulation_v2

        out = run_field_simulation_v2(
            field,
            n_sims=args.n_sims,
            base_score_noise=args.noise,
            seed=args.seed,
        )
    else:
        out = run_shadow_field_simulation(field, [], seed=args.seed)
    print(json.dumps(out, indent=2)[:8000])


if __name__ == "__main__":
    main()
