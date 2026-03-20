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

__all__ = [
    "CHECKPOINT_SCRIPT_EVALUATOR_VERSION",
    "EVAL_CONTRACT_VERSION_WALK_FORWARD",
    "EvaluationResult",
    "WalkForwardBenchmarkSpec",
    "compute_objective_vector_higher_is_better",
    "evaluate_checkpoint_pilot",
    "evaluate_walk_forward_benchmark",
    "evaluation_from_walk_forward_dict",
]
