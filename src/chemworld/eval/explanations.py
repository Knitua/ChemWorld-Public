"""Structured mechanism-explanation scoring utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MechanismScore:
    score: float
    max_score: float
    passed_items: list[str]
    missing_items: list[str]

    @property
    def normalized(self) -> float:
        return 0.0 if self.max_score <= 0 else self.score / self.max_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "max_score": self.max_score,
            "normalized": self.normalized,
            "passed_items": self.passed_items,
            "missing_items": self.missing_items,
        }


RUBRIC: dict[str, tuple[str, ...]] = {
    "temperature_tradeoff": ("temperature", "heat", "hot", "thermal", "温度", "高温"),
    "degradation": ("degradation", "degrade", "降解", "分解"),
    "byproduct_or_selectivity": ("byproduct", "selectivity", "副产物", "选择性"),
    "catalyst_solvent_interaction": ("catalyst", "solvent", "催化剂", "溶剂"),
    "concentration_or_safety": ("concentration", "risk", "safety", "浓度", "风险", "安全"),
    "uncertainty_or_limitations": ("uncertainty", "limited", "seed", "noise", "不确定", "局限"),
    "next_experiment": ("next", "experiment", "validate", "下一", "验证"),
}


def score_mechanism_explanation(explanation: dict[str, Any] | str) -> MechanismScore:
    """Score whether an explanation covers the expected mechanism themes.

    This is a transparent keyword rubric, not a substitute for expert grading.
    It is intended for benchmark artifacts and classroom feedback where a stable
    first-pass mechanism checklist is useful.
    """

    if isinstance(explanation, str):
        text = explanation
    else:
        text = " ".join(str(value) for value in explanation.values())
    normalized_text = text.casefold()
    passed: list[str] = []
    missing: list[str] = []
    for item, keywords in RUBRIC.items():
        if any(keyword.casefold() in normalized_text for keyword in keywords):
            passed.append(item)
        else:
            missing.append(item)
    return MechanismScore(
        score=float(len(passed)),
        max_score=float(len(RUBRIC)),
        passed_items=passed,
        missing_items=missing,
    )


def combined_artifact_score(
    *,
    performance: float,
    mechanism_score: float,
    reproducibility: float,
) -> float:
    """Combine performance, explanation, and reproducibility for capstone grading."""

    clipped_performance = min(max(float(performance), 0.0), 1.0)
    clipped_mechanism = min(max(float(mechanism_score), 0.0), 1.0)
    clipped_reproducibility = min(max(float(reproducibility), 0.0), 1.0)
    return (
        0.50 * clipped_performance
        + 0.30 * clipped_mechanism
        + 0.20 * clipped_reproducibility
    )
