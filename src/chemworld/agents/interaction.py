"""Typed public interaction contract for operation-level benchmark agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from chemworld.data.logging import to_builtin

INTERACTION_CONTRACT_VERSION = "chemworld-agent-interaction-0.2"

DecisionScope = Literal["experiment_recipe", "operation"]
AdaptationSource = Literal[
    "none",
    "measurement",
    "spectrum",
    "experiment_memory",
    "validator",
]


@dataclass(frozen=True)
class InteractionCapabilities:
    """Machine-readable declaration of evidence an agent actually consumes."""

    decision_scope: DecisionScope = "operation"
    consumes_intermediate_observations: bool = False
    consumes_spectra: bool = False
    adapts_within_experiment: bool = False
    adapts_across_experiments: bool = False
    emits_structured_decision_audit: bool = False

    def __post_init__(self) -> None:
        if self.decision_scope not in {"experiment_recipe", "operation"}:
            raise ValueError("unsupported decision scope")
        if self.consumes_spectra and not self.consumes_intermediate_observations:
            raise ValueError("spectra consumption requires intermediate observations")
        if self.adapts_within_experiment and self.decision_scope != "operation":
            raise ValueError("within-experiment adaptation requires operation decisions")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": INTERACTION_CONTRACT_VERSION,
            **asdict(self),
        }


@dataclass(frozen=True)
class DecisionAuditRecord:
    """Concise public decision evidence; never a private chain-of-thought field."""

    action: dict[str, Any]
    expected_effect: str
    diagnostic_target: str
    expected_information_gain: float
    belief_update_rule: dict[str, str]
    uncertainty: float | None
    adaptation_source: AdaptationSource
    requested_historical_spectrum_id: str | None = None
    status: Literal["provided", "not_provided"] = "provided"

    def __post_init__(self) -> None:
        if self.adaptation_source not in {
            "none",
            "measurement",
            "spectrum",
            "experiment_memory",
            "validator",
        }:
            raise ValueError("unsupported decision adaptation source")
        if self.status not in {"provided", "not_provided"}:
            raise ValueError("unsupported decision audit status")
        if self.uncertainty is not None and not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("decision uncertainty must be in [0, 1]")
        if not 0.0 <= self.expected_information_gain <= 1.0:
            raise ValueError("expected information gain must be in [0, 1]")
        if set(self.belief_update_rule) != {"if_supported", "if_not_supported"} or not all(
            str(value).strip() for value in self.belief_update_rule.values()
        ):
            raise ValueError("belief update rule requires two non-empty branches")
        if self.requested_historical_spectrum_id is not None and (
            not isinstance(self.requested_historical_spectrum_id, str)
            or not self.requested_historical_spectrum_id.strip()
        ):
            raise ValueError("requested historical spectrum ID must be non-empty or null")
        if self.status == "provided" and (
            not self.action.get("operation")
            or not self.expected_effect
            or not self.diagnostic_target
        ):
            raise ValueError(
                "provided decision audits require action, expected effect, and diagnostic target"
            )

    @classmethod
    def unavailable(cls, action: dict[str, Any]) -> DecisionAuditRecord:
        return cls(
            action=dict(action),
            expected_effect="",
            diagnostic_target="",
            expected_information_gain=0.0,
            belief_update_rule={
                "if_supported": "not provided",
                "if_not_supported": "not provided",
            },
            uncertainty=None,
            adaptation_source="none",
            status="not_provided",
        )

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
        *,
        action: dict[str, Any],
    ) -> DecisionAuditRecord:
        if not payload:
            return cls.unavailable(action)
        payload_action = payload.get("action", action)
        if not isinstance(payload_action, dict) or payload_action != action:
            raise ValueError("decision audit action must match the selected action")
        raw_spectrum_request = payload.get("request_historical_spectrum_id")
        if raw_spectrum_request is not None and not isinstance(raw_spectrum_request, str):
            raise ValueError("requested historical spectrum ID must be a string or null")
        expected_effect = str(
            payload.get("expected_effect") or payload.get("hypothesis") or ""
        )
        diagnostic_target = str(
            payload.get("diagnostic_target") or payload.get("rationale") or ""
        )
        raw_information_gain = payload.get("expected_information_gain", 0.0)
        if isinstance(raw_information_gain, bool) or not isinstance(
            raw_information_gain,
            int | float,
        ):
            raise ValueError("expected_information_gain must be numeric")
        raw_rule = payload.get("belief_update_rule")
        if raw_rule is None:
            belief_update_rule = {
                "if_supported": "increase support for the stated expectation",
                "if_not_supported": "decrease support and select a follow-up",
            }
        elif isinstance(raw_rule, dict):
            belief_update_rule = {
                "if_supported": str(raw_rule.get("if_supported") or ""),
                "if_not_supported": str(raw_rule.get("if_not_supported") or ""),
            }
        else:
            raise ValueError("belief_update_rule must be an object")
        return cls(
            action=dict(action),
            expected_effect=expected_effect,
            diagnostic_target=diagnostic_target,
            expected_information_gain=float(raw_information_gain),
            belief_update_rule=belief_update_rule,
            uncertainty=(
                None if payload.get("uncertainty") is None else float(payload["uncertainty"])
            ),
            adaptation_source=str(payload.get("adaptation_source", "none")),  # type: ignore[arg-type]
            requested_historical_spectrum_id=raw_spectrum_request,
            status=str(payload.get("status", "provided")),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        return to_builtin(asdict(self))


@dataclass(frozen=True)
class AgentDecisionContext:
    """Public, compact context supplied before one operation decision."""

    step: int
    task_id: str | None
    decision_stage: str
    campaign_state: dict[str, Any]
    visible_metrics: dict[str, Any]
    latest_spectra: dict[str, Any]
    uncertainty: dict[str, Any]
    constraint_flags: dict[str, Any]
    available_operations: tuple[str, ...]
    previous_event_type: str | None
    historical_spectrum_catalog: tuple[dict[str, Any], ...] = ()
    requested_historical_spectrum: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_operations(self) -> int:
        return max(int(self.campaign_state.get("remaining_budget", 0)), 0)

    def to_dict(self) -> dict[str, Any]:
        cataloged = [
            item
            for item in self.historical_spectrum_catalog
            if isinstance(item.get("measurement_step"), int)
            and not isinstance(item.get("measurement_step"), bool)
        ]
        latest_cataloged = (
            max(cataloged, key=lambda item: int(item["measurement_step"]))
            if cataloged
            else None
        )
        latest_measurement_step = (
            int(latest_cataloged["measurement_step"])
            if latest_cataloged is not None
            else None
        )
        return {
            "contract_version": INTERACTION_CONTRACT_VERSION,
            "step": self.step,
            "task_id": self.task_id,
            "decision_stage": self.decision_stage,
            "campaign_state": to_builtin(self.campaign_state),
            "visible_metrics": to_builtin(self.visible_metrics),
            "latest_spectra": to_builtin(self.latest_spectra),
            "uncertainty": to_builtin(self.uncertainty),
            "constraint_flags": to_builtin(self.constraint_flags),
            "available_operations": list(self.available_operations),
            "previous_event_type": self.previous_event_type,
            "remaining_operations": self.remaining_operations,
            "historical_spectrum_catalog": to_builtin(self.historical_spectrum_catalog),
            "requested_historical_spectrum": to_builtin(self.requested_historical_spectrum),
            "observation_provenance": {
                "current_event_type": self.previous_event_type,
                "current_spectral_packet": bool(
                    self.latest_spectra.get("has_spectral_packet")
                ),
                "latest_cataloged_spectrum_id": (
                    latest_cataloged.get("spectrum_id")
                    if latest_cataloged is not None
                    else None
                ),
                "latest_spectrum_measurement_step": latest_measurement_step,
                "operations_since_latest_spectrum": (
                    max(self.step - latest_measurement_step - 1, 0)
                    if latest_measurement_step is not None
                    else None
                ),
            },
        }


def build_decision_context(
    *,
    step: int,
    task_info: dict[str, Any],
    campaign_state: dict[str, Any],
    public_view: dict[str, Any],
    previous_event_type: str | None,
) -> AgentDecisionContext:
    """Reduce the standard public view to stable decision-relevant evidence."""

    tool_view = public_view.get("tool_json", {})
    lab_report = tool_view.get("lab_report", {}) if isinstance(tool_view, dict) else {}
    spectra = lab_report.get("spectra_summary", {}) if isinstance(lab_report, dict) else {}
    spectra_context = {
        **(spectra if isinstance(spectra, dict) else {}),
        "raw_signal": to_builtin(tool_view.get("raw_signal", {})),
        "processed_estimate": to_builtin(tool_view.get("processed_estimate", {})),
    }
    if not spectra_context.get("has_spectral_packet"):
        # Instrument-derived estimates may remain in the public state observation
        # after a control operation. They are still available as visible metrics
        # and agent memory, but must not masquerade as a newly measured spectrum.
        spectra_context["raw_signal"] = {}
        spectra_context["processed_estimate"] = {}
        spectra_context["uncertainty"] = {}
    catalog = tool_view.get("historical_spectrum_catalog", [])
    requested = tool_view.get("requested_historical_spectrum", {})
    available = tool_view.get("available_actions", []) if isinstance(tool_view, dict) else []
    operations = tuple(
        str(item["operation"])
        for item in available
        if isinstance(item, dict) and item.get("operation")
    )
    measure_choices: set[str] = set()
    for item in available:
        if not isinstance(item, dict) or item.get("operation") != "measure":
            continue
        schema = item.get("schema")
        fields = schema.get("fields") if isinstance(schema, dict) else None
        for field_spec in fields if isinstance(fields, list) else ():
            if (
                not isinstance(field_spec, dict)
                or field_spec.get("field") != "instrument"
            ):
                continue
            choices = field_spec.get("choices")
            if isinstance(choices, list):
                measure_choices.update(str(choice) for choice in choices)
    if previous_event_type == "experiment_end" or step == 1:
        stage = "experiment_setup"
    elif set(operations) == {"measure"} and measure_choices == {"final_assay"}:
        # A committed termination exposes only final-assay measurement.  Some
        # live workflow states also expose only ``measure`` but restrict it to
        # a non-final process assay, so operation shape alone is insufficient.
        stage = "experiment_closeout"
    elif previous_event_type == "measurement_result":
        stage = "evidence_update"
    else:
        stage = "experiment_control"
    return AgentDecisionContext(
        step=step,
        task_id=(None if task_info.get("task_id") is None else str(task_info["task_id"])),
        decision_stage=stage,
        campaign_state=to_builtin(campaign_state),
        visible_metrics=to_builtin(lab_report.get("visible_metrics", {})),
        latest_spectra=to_builtin(spectra_context),
        uncertainty=to_builtin(tool_view.get("uncertainty", {})),
        constraint_flags=to_builtin(tool_view.get("constraints", {})),
        available_operations=operations,
        previous_event_type=previous_event_type,
        historical_spectrum_catalog=tuple(
            to_builtin(item) for item in catalog if isinstance(item, dict)
        )
        if isinstance(catalog, list)
        else (),
        requested_historical_spectrum=(
            to_builtin(requested) if isinstance(requested, dict) else {}
        ),
    )


__all__ = [
    "INTERACTION_CONTRACT_VERSION",
    "AgentDecisionContext",
    "DecisionAuditRecord",
    "InteractionCapabilities",
    "build_decision_context",
]
