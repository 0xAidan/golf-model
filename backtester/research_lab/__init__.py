"""Research lab: canonical evaluation and future autoresearch v2 primitives."""

from backtester.research_lab.canonical import (
    CHECKPOINT_SCRIPT_EVALUATOR_VERSION,
    EVAL_CONTRACT_VERSION_WALK_FORWARD,
    EvaluationResult,
    WalkForwardBenchmarkSpec,
    compute_objective_vector_higher_is_better,
    evaluate_checkpoint_pilot,
    evaluate_walk_forward_benchmark,
    evaluation_from_walk_forward_dict,
)
from backtester.research_lab.mo_study import (
    create_or_load_study,
    default_storage_path,
    make_objective,
    run_mo_study,
    study_summary,
)
from backtester.research_lab.param_space import strategy_from_optuna_trial
from backtester.research_lab.cycle_config import CYCLE_CONFIG_PATH, load_cycle_config

__all__ = [
    "CHECKPOINT_SCRIPT_EVALUATOR_VERSION",
    "EVAL_CONTRACT_VERSION_WALK_FORWARD",
    "EvaluationResult",
    "WalkForwardBenchmarkSpec",
    "compute_objective_vector_higher_is_better",
    "evaluate_checkpoint_pilot",
    "evaluate_walk_forward_benchmark",
    "evaluation_from_walk_forward_dict",
    "create_or_load_study",
    "default_storage_path",
    "make_objective",
    "run_mo_study",
    "study_summary",
    "strategy_from_optuna_trial",
    "CYCLE_CONFIG_PATH",
    "load_cycle_config",
]
