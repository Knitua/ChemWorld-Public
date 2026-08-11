"""Evaluation protocol and leaderboard utilities."""

from chemworld.eval.baseline_report import (
    CORE_BASELINE_AGENTS,
    SERIOUS_BASELINE_AGENTS,
    BaselineReport,
    generate_baseline_report,
    generate_core_baseline_report,
    generate_serious_baseline_report,
)
from chemworld.eval.explanations import (
    MechanismScore,
    combined_artifact_score,
    score_mechanism_explanation,
)
from chemworld.eval.metrics import EvaluationResult, evaluate_records
from chemworld.eval.private_artifact import (
    SignedPrivateEvalArtifact,
    sign_private_eval_results,
    verify_private_eval_artifact,
)
from chemworld.eval.runner import make_agent, run_agent
from chemworld.eval.scoring_audit import (
    ScoringAuditFailure,
    ScoringAuditResult,
    audit_scoring_contract,
)
from chemworld.eval.suite import run_suite
from chemworld.eval.task_metric_endpoints import (
    MetricEndpoint,
    build_task_metric_contract,
    evaluate_task_metrics,
    metric_endpoint,
)
from chemworld.eval.verify import VerificationResult, verify_records

__all__ = [
    "CORE_BASELINE_AGENTS",
    "SERIOUS_BASELINE_AGENTS",
    "BaselineReport",
    "EvaluationResult",
    "MechanismScore",
    "MetricEndpoint",
    "ScoringAuditFailure",
    "ScoringAuditResult",
    "SignedPrivateEvalArtifact",
    "VerificationResult",
    "audit_scoring_contract",
    "build_task_metric_contract",
    "combined_artifact_score",
    "evaluate_records",
    "evaluate_task_metrics",
    "generate_baseline_report",
    "generate_core_baseline_report",
    "generate_serious_baseline_report",
    "make_agent",
    "metric_endpoint",
    "run_agent",
    "run_suite",
    "score_mechanism_explanation",
    "sign_private_eval_results",
    "verify_private_eval_artifact",
    "verify_records",
]
