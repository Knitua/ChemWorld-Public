"""Transactional runtime engine used by ChemWorldEnv."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chemworld.foundation import OperationRecord, PhysicalConstitution, WorldState
from chemworld.operation_validator import OperationValidation
from chemworld.runtime.domain_service_registry import DomainServiceRegistry
from chemworld.runtime.domain_services import ChemWorldDomainServices
from chemworld.runtime.kernel_contracts import KernelResult, RuntimeContext
from chemworld.runtime.kernel_registry import OperationKernelRegistry
from chemworld.runtime.mechanisms import CompiledMechanism
from chemworld.runtime.profiles import TaskRuntimeProfile
from chemworld.runtime.transactions import StatePatch, TransactionManager, WorldEvent
from chemworld.tasks import TaskSpec
from chemworld.world.parameters import ChemWorldParameters


@dataclass(frozen=True)
class RuntimeStepResult:
    state: WorldState
    operation_record: OperationRecord
    kernel_result: KernelResult

    def info_payload(self) -> dict[str, Any]:
        return {
            "kernel_id": self.kernel_result.kernel_id,
            "kernel_version": self.kernel_result.kernel_version,
            "affected_ledgers": list(self.kernel_result.affected_ledgers),
            "world_events": [
                event.to_dict() for event in self.kernel_result.events
            ],
            "state_patches_summary": [
                patch.to_dict() for patch in self.kernel_result.patches
            ],
            "cost_delta": self.kernel_result.cost_delta,
            "risk_delta": self.kernel_result.risk_delta,
            "sample_delta": self.kernel_result.sample_delta,
            "transaction_status": self.kernel_result.transaction_status,
            "rollback_reason": self.kernel_result.rollback_reason,
        }


class ChemWorldRuntime:
    """Transactional operation runtime for a ChemWorld task/scenario."""

    def __init__(
        self,
        *,
        world: ChemWorldParameters,
        constitution: PhysicalConstitution,
        task_spec: TaskSpec | None,
        compiled_mechanism: CompiledMechanism,
        debug_truth: bool = False,
        registry: OperationKernelRegistry | None = None,
        domain_service_registry: DomainServiceRegistry | None = None,
        partition_nominal_pair_contract: str | None = None,
    ) -> None:
        self.world = world
        self.constitution = constitution
        self.task_spec = task_spec
        self.compiled_mechanism = compiled_mechanism
        self.profile = TaskRuntimeProfile.from_task(task_spec)
        self.registry = registry or OperationKernelRegistry.default()
        self.registry.validate_profile(self.profile)
        self.domain_services = ChemWorldDomainServices(
            world,
            constitution,
            compiled_mechanism=compiled_mechanism,
            service_registry=domain_service_registry,
            partition_nominal_pair_contract=partition_nominal_pair_contract,
        )
        self.domain_services.validate_profile(self.profile)
        self.transaction_manager = TransactionManager(constitution)
        self.context = RuntimeContext(
            task_spec=task_spec,
            profile=self.profile,
            compiled_mechanism=compiled_mechanism,
            domain_services=self.domain_services,
            transaction_manager=self.transaction_manager,
            debug_truth=debug_truth,
        )

    def apply_transaction(
        self,
        state: WorldState,
        action: dict[str, Any],
    ) -> RuntimeStepResult:
        kernel = self.registry.get(str(action["operation"]))
        result = kernel.apply(state, action, self.context)
        return RuntimeStepResult(
            state=result.state,
            operation_record=result.operation_record,
            kernel_result=result,
        )

    def apply_invalid_transaction(
        self,
        state: WorldState,
        action: dict[str, Any],
        validation: OperationValidation,
    ) -> RuntimeStepResult:
        raw_operation = action.get("operation")
        operation_type = (
            raw_operation
            if isinstance(raw_operation, str) and raw_operation.strip()
            else "invalid"
        )
        penalized = self.domain_services.penalize_invalid(state)
        cost_delta = penalized.ledger.cost - state.ledger.cost
        risk_delta = penalized.ledger.risk - state.ledger.risk
        sample_delta = penalized.ledger.sample_consumed_L - state.ledger.sample_consumed_L
        operation_record = self.domain_services.record_operation(
            operation_type,
            state,
            penalized,
            validation.preconditions,
            action,
        )
        result = KernelResult(
            state=penalized,
            operation_record=operation_record,
            events=(
                WorldEvent(
                    event_type="validation_failed",
                    operation_type=operation_type,
                    payload={
                        "invalid_reasons": list(validation.invalid_reasons),
                        "cost_delta": cost_delta,
                        "risk_delta": risk_delta,
                        "sample_delta": sample_delta,
                    },
                ),
            ),
            patches=(
                StatePatch(
                    patch_type="validation_penalty",
                    affected_ledgers=("process",),
                    summary={
                        "delta_cost": cost_delta,
                        "delta_risk": risk_delta,
                        "delta_sample_consumed_L": sample_delta,
                        "invalid_reasons": list(validation.invalid_reasons),
                    },
                ),
            ),
            state_delta_summary=operation_record.state_delta_summary,
            cost_delta=cost_delta,
            risk_delta=risk_delta,
            sample_delta=sample_delta,
            affected_ledgers=("process",),
            kernel_id="validation:invalid_action",
            kernel_version="runtime-v2.0",
            transaction_status="validation_failed",
            rollback_reason="validation_failed",
        )
        return RuntimeStepResult(
            state=penalized,
            operation_record=operation_record,
            kernel_result=result,
        )

    def apply_campaign_control_transaction(
        self,
        state: WorldState,
        action: dict[str, Any],
        validation: OperationValidation,
    ) -> RuntimeStepResult:
        """Record an environment-owned campaign control without mutating physics."""

        operation_type = str(action["operation"])
        operation_record = self.domain_services.record_operation(
            operation_type,
            state,
            state,
            validation.preconditions,
            action,
        )
        result = KernelResult(
            state=state,
            operation_record=operation_record,
            events=(
                WorldEvent(
                    event_type="campaign_batch_discarded",
                    operation_type=operation_type,
                    payload={"reason": str(action.get("reason", ""))},
                ),
            ),
            patches=(),
            state_delta_summary=operation_record.state_delta_summary,
            cost_delta=0.0,
            risk_delta=0.0,
            sample_delta=0.0,
            affected_ledgers=(),
            kernel_id="campaign_control:discard_batch",
            kernel_version="runtime-v2.0",
            transaction_status="committed",
            rollback_reason=None,
        )
        return RuntimeStepResult(
            state=state,
            operation_record=operation_record,
            kernel_result=result,
        )

    def to_dict(self, *, include_debug_truth: bool = False) -> dict[str, Any]:
        payload = {
            "profile": self.profile.to_dict(),
            "operation_kernels": self.registry.to_dict(),
            "domain_services": self.domain_services.to_dict(),
            "mechanism_summary": {
                "mechanism_id": self.compiled_mechanism.mechanism_id,
                "mechanism_version": self.compiled_mechanism.mechanism_version,
                "mechanism_hash": self.compiled_mechanism.mechanism_hash,
                "species_count": self.compiled_mechanism.manifest.species_count,
                "reaction_count": self.compiled_mechanism.manifest.reaction_count,
                "validation_passed": self.compiled_mechanism.manifest.validation_report.passed,
                "public_boundary": (
                    "hash/count summary only; species identities, rate laws, and "
                    "stoichiometry are hidden from public agent-facing views"
                ),
            },
        }
        if include_debug_truth:
            payload["debug_compiled_mechanism"] = self.compiled_mechanism.to_dict()
        return payload


__all__ = ["ChemWorldRuntime", "RuntimeStepResult"]
