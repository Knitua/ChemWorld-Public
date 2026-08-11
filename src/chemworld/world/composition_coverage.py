"""Coverage-guided finite generation for declarative ChemWorld compositions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from typing import Any

import numpy as np

from chemworld.schemas import validate_action_schema
from chemworld.world.composition import (
    CompiledWorldComposition,
    compile_world_composition,
)

WORLD_COMPOSITION_COVERAGE_SCHEMA_VERSION = "chemworld-composition-coverage-0.1"

_ACTION_FIELD_UNITS = {
    "amount_mol": "mol",
    "catalyst_amount_mol": "mol",
    "current_mA": "mA",
    "duration_s": "s",
    "flow_rate_mL_min": "mL/min",
    "potential_V": "V",
    "reflux_ratio": "dimensionless",
    "residence_time_s": "s",
    "sample_volume_L": "L",
    "seed_mass_g": "g",
    "stirring_speed_rpm": "rpm",
    "target_temperature_K": "K",
    "transfer_fraction": "dimensionless",
    "volume_L": "L",
    "wash_volume_L": "L",
}


def _json_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("coverage values must be JSON-serializable") from exc


@dataclass(frozen=True)
class DiscreteCoverageAxis:
    """One categorical authoring choice applied to one or more request paths."""

    axis_id: str
    bindings: tuple[str, ...]
    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        if not self.axis_id.strip():
            raise ValueError("discrete axis_id must be non-empty")
        if not self.bindings or any(not path.strip() for path in self.bindings):
            raise ValueError("discrete axis bindings must be non-empty paths")
        if not self.values:
            raise ValueError("discrete axis values must be non-empty")
        keys = tuple(_json_key(value) for value in self.values)
        if len(set(keys)) != len(keys):
            raise ValueError(f"discrete axis {self.axis_id!r} contains duplicate values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis_id": self.axis_id,
            "bindings": list(self.bindings),
            "values": deepcopy(list(self.values)),
        }


@dataclass(frozen=True)
class ContinuousCoverageAxis:
    """One bounded numeric coordinate used by workflow placeholders."""

    axis_id: str
    lower: float
    upper: float
    unit: str

    def __post_init__(self) -> None:
        if not self.axis_id.strip():
            raise ValueError("continuous axis_id must be non-empty")
        if not isfinite(self.lower) or not isfinite(self.upper) or self.lower >= self.upper:
            raise ValueError("continuous axis bounds must be finite and increasing")
        if not self.unit.strip():
            raise ValueError("continuous axis unit must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis_id": self.axis_id,
            "lower": self.lower,
            "upper": self.upper,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class OrderedWorkflowTemplate:
    """One typed operation path with optional continuous-axis placeholders."""

    workflow_id: str
    actions: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        if not self.workflow_id.strip():
            raise ValueError("workflow_id must be non-empty")
        if not self.actions:
            raise ValueError("workflow actions must be non-empty")
        for action in self.actions:
            if not isinstance(action, dict) or not str(action.get("operation", "")).strip():
                raise ValueError("every workflow action must declare an operation")

    @property
    def operation_sequence(self) -> tuple[str, ...]:
        return tuple(str(action["operation"]) for action in self.actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "actions": deepcopy(list(self.actions)),
        }


@dataclass(frozen=True)
class CompositionCoverageTarget:
    """Finite coverage target; no exhaustive-world claim is implied."""

    discrete_strength: int = 2
    continuous_samples: int = 8
    ordered_interaction_depth: int = 2
    seed: int = 0

    def __post_init__(self) -> None:
        if self.discrete_strength != 2:
            raise ValueError("v1 coverage generation supports pairwise discrete strength only")
        if self.continuous_samples <= 0:
            raise ValueError("continuous_samples must be positive")
        if self.ordered_interaction_depth <= 0:
            raise ValueError("ordered_interaction_depth must be positive")
        if self.seed < 0:
            raise ValueError("coverage seed must be non-negative")

    def to_dict(self) -> dict[str, int]:
        return {
            "discrete_strength": self.discrete_strength,
            "continuous_samples": self.continuous_samples,
            "ordered_interaction_depth": self.ordered_interaction_depth,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class GeneratedCompositionCase:
    """One compiled composition plus a materialized qualification workflow."""

    case_id: str
    request: dict[str, Any]
    discrete_levels: dict[str, Any]
    continuous_coordinates: dict[str, dict[str, float | str]]
    workflow_id: str
    actions: tuple[dict[str, Any], ...]
    compiled: CompiledWorldComposition

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "request": deepcopy(self.request),
            "discrete_levels": deepcopy(self.discrete_levels),
            "continuous_coordinates": deepcopy(self.continuous_coordinates),
            "workflow_id": self.workflow_id,
            "actions": deepcopy(list(self.actions)),
            "composition": self.compiled.to_public_dict(),
        }


@dataclass(frozen=True)
class CompositionCoverageSuite:
    """Finite generated cases and exact coverage denominators."""

    suite_id: str
    target: CompositionCoverageTarget
    cases: tuple[GeneratedCompositionCase, ...]
    report: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": WORLD_COMPOSITION_COVERAGE_SCHEMA_VERSION,
            "suite_id": self.suite_id,
            "target": self.target.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
            "report": deepcopy(self.report),
        }


class WorldCompositionCoverageError(ValueError):
    """Raised when a generated coverage case cannot pass compilation or schema checks."""

    def __init__(self, message: str, *, report: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.report = deepcopy(dict(report))


def _pair_key(
    left_axis: str,
    left_value: Any,
    right_axis: str,
    right_value: Any,
) -> tuple[str, str, str, str]:
    return (left_axis, _json_key(left_value), right_axis, _json_key(right_value))


def _required_discrete_pairs(
    axes: Sequence[DiscreteCoverageAxis],
) -> set[tuple[str, str, str, str]]:
    required: set[tuple[str, str, str, str]] = set()
    for left, right in combinations(axes, 2):
        required.update(
            _pair_key(left.axis_id, left_value, right.axis_id, right_value)
            for left_value in left.values
            for right_value in right.values
        )
    return required


def _covered_discrete_pairs(row: Mapping[str, Any]) -> set[tuple[str, str, str, str]]:
    ordered = tuple(row)
    return {
        _pair_key(left, row[left], right, row[right])
        for left, right in combinations(ordered, 2)
    }


def pairwise_covering_rows(
    axes: Sequence[DiscreteCoverageAxis],
    *,
    seed: int = 0,
) -> tuple[dict[str, Any], ...]:
    """Construct deterministic pairwise rows without emitting the Cartesian product."""

    axis_tuple = tuple(axes)
    axis_ids = tuple(axis.axis_id for axis in axis_tuple)
    if len(set(axis_ids)) != len(axis_ids):
        raise ValueError("discrete axis IDs must be unique")
    if not axis_tuple:
        return ({},)
    if len(axis_tuple) == 1:
        axis = axis_tuple[0]
        return tuple({axis.axis_id: deepcopy(value)} for value in axis.values)

    rng = np.random.default_rng(seed)
    value_orders: dict[str, tuple[Any, ...]] = {}
    for axis in axis_tuple:
        order = rng.permutation(len(axis.values))
        value_orders[axis.axis_id] = tuple(axis.values[int(index)] for index in order)

    uncovered = _required_discrete_pairs(axis_tuple)
    rows: list[dict[str, Any]] = []
    axis_by_id = {axis.axis_id: axis for axis in axis_tuple}
    while uncovered:
        left_id, left_key, right_id, right_key = min(uncovered)
        row: dict[str, Any] = {}
        for axis_id, value_key in ((left_id, left_key), (right_id, right_key)):
            axis = axis_by_id[axis_id]
            row[axis_id] = deepcopy(
                next(value for value in axis.values if _json_key(value) == value_key)
            )
        for axis in axis_tuple:
            if axis.axis_id in row:
                continue
            best_value = None
            best_gain = -1
            for value in value_orders[axis.axis_id]:
                candidate = {**row, axis.axis_id: value}
                gain = len(_covered_discrete_pairs(candidate).intersection(uncovered))
                if gain > best_gain:
                    best_value = value
                    best_gain = gain
            row[axis.axis_id] = deepcopy(best_value)
        canonical_row = {axis.axis_id: row[axis.axis_id] for axis in axis_tuple}
        uncovered -= _covered_discrete_pairs(canonical_row)
        rows.append(canonical_row)
    return tuple(rows)


def latin_hypercube_coordinates(
    axes: Sequence[ContinuousCoverageAxis],
    *,
    sample_count: int,
    seed: int = 0,
) -> tuple[dict[str, float], ...]:
    """Generate one randomized point in every stratum of every continuous axis."""

    axis_tuple = tuple(axes)
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    axis_ids = tuple(axis.axis_id for axis in axis_tuple)
    if len(set(axis_ids)) != len(axis_ids):
        raise ValueError("continuous axis IDs must be unique")
    if not axis_tuple:
        return ({},)
    rng = np.random.default_rng(seed)
    unit_design = np.zeros((sample_count, len(axis_tuple)), dtype=float)
    for dimension in range(len(axis_tuple)):
        bins = (np.arange(sample_count, dtype=float) + rng.random(sample_count)) / sample_count
        rng.shuffle(bins)
        unit_design[:, dimension] = bins
    rows: list[dict[str, float]] = []
    for row in unit_design:
        rows.append(
            {
                axis.axis_id: axis.lower + float(row[index]) * (axis.upper - axis.lower)
                for index, axis in enumerate(axis_tuple)
            }
        )
    return tuple(rows)


def _set_request_binding(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if path == "world_split":
        payload["world_split"] = deepcopy(value)
        return
    if len(parts) >= 4 and parts[0] == "components" and parts[2] == "parameters":
        component_kind = parts[1]
        parameter_name = ".".join(parts[3:])
        components = payload.get("components")
        if not isinstance(components, list):
            raise ValueError("coverage base request must contain a components list")
        matches = [item for item in components if item.get("kind") == component_kind]
        if len(matches) != 1:
            raise ValueError(
                f"coverage binding {path!r} requires exactly one {component_kind!r} component"
            )
        parameters = matches[0].setdefault("parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError(f"coverage binding {path!r} requires parameter object")
        parameters[parameter_name] = deepcopy(value)
        return
    if parts[0] == "task" and len(parts) >= 2:
        task = payload.setdefault("task", {})
        if not isinstance(task, dict):
            raise ValueError("coverage base request task must be an object")
        cursor = task
        for part in parts[1:-1]:
            child = cursor.setdefault(part, {})
            if not isinstance(child, dict):
                raise ValueError(f"coverage binding {path!r} crosses a non-object field")
            cursor = child
        cursor[parts[-1]] = deepcopy(value)
        return
    raise ValueError(f"unsupported coverage binding path: {path!r}")


def _axis_placeholders(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        if set(value) == {"coverage_axis"}:
            return {str(value["coverage_axis"])}
        return set().union(*(_axis_placeholders(item) for item in value.values()), set())
    if isinstance(value, (list, tuple)):
        return set().union(*(_axis_placeholders(item) for item in value), set())
    return set()


def _validate_workflow_axis_units(
    workflows: Sequence[OrderedWorkflowTemplate],
    continuous_axes: Sequence[ContinuousCoverageAxis],
) -> None:
    unit_by_axis = {axis.axis_id: axis.unit for axis in continuous_axes}
    for workflow in workflows:
        for action_index, action in enumerate(workflow.actions):
            for field, value in action.items():
                placeholders = _axis_placeholders(value)
                if not placeholders:
                    continue
                if not isinstance(value, Mapping) or set(value) != {"coverage_axis"}:
                    raise ValueError(
                        "continuous coverage placeholders must occupy a complete action field"
                    )
                expected_unit = _ACTION_FIELD_UNITS.get(field)
                if expected_unit is None:
                    raise ValueError(
                        f"workflow {workflow.workflow_id!r} action {action_index} field "
                        f"{field!r} has no declared continuous unit"
                    )
                axis_id = next(iter(placeholders))
                actual_unit = unit_by_axis.get(axis_id)
                if actual_unit is not None and actual_unit != expected_unit:
                    raise ValueError(
                        f"continuous axis {axis_id!r} uses {actual_unit!r} but action field "
                        f"{field!r} requires {expected_unit!r}"
                    )


def _materialize_value(value: Any, coordinates: Mapping[str, float]) -> Any:
    if isinstance(value, Mapping):
        if set(value) == {"coverage_axis"}:
            axis_id = str(value["coverage_axis"])
            try:
                return float(coordinates[axis_id])
            except KeyError as exc:
                raise ValueError(f"workflow references unknown coverage axis {axis_id!r}") from exc
        return {key: _materialize_value(item, coordinates) for key, item in value.items()}
    if isinstance(value, list):
        return [_materialize_value(item, coordinates) for item in value]
    if isinstance(value, tuple):
        return tuple(_materialize_value(item, coordinates) for item in value)
    return deepcopy(value)


def _ordered_interactions(
    operation_sequence: Sequence[str],
    depth: int,
) -> set[tuple[str, ...]]:
    if len(operation_sequence) < depth:
        return set()
    return {
        tuple(operation_sequence[index : index + depth])
        for index in range(len(operation_sequence) - depth + 1)
    }


def _coverage_report(
    *,
    target: CompositionCoverageTarget,
    discrete_axes: tuple[DiscreteCoverageAxis, ...],
    discrete_rows: tuple[dict[str, Any], ...],
    continuous_axes: tuple[ContinuousCoverageAxis, ...],
    continuous_rows: tuple[dict[str, float], ...],
    workflows: tuple[OrderedWorkflowTemplate, ...],
    cases: Sequence[GeneratedCompositionCase],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    required_pairs = _required_discrete_pairs(discrete_axes)
    required_levels = {
        (axis.axis_id, _json_key(value))
        for axis in discrete_axes
        for value in axis.values
    }
    covered_pairs = set().union(
        *(_covered_discrete_pairs(case.discrete_levels) for case in cases),
        set(),
    )
    covered_levels = {
        (axis_id, _json_key(value))
        for case in cases
        for axis_id, value in case.discrete_levels.items()
    }
    required_strata = len(continuous_axes) * (
        target.continuous_samples if continuous_axes else 0
    )
    covered_strata: set[tuple[str, int]] = set()
    for case in cases:
        for axis in continuous_axes:
            coordinate = case.continuous_coordinates[axis.axis_id]
            normalized = (float(coordinate["value"]) - axis.lower) / (
                axis.upper - axis.lower
            )
            stratum = min(
                int(normalized * target.continuous_samples),
                target.continuous_samples - 1,
            )
            covered_strata.add((axis.axis_id, stratum))
    required_ordered = set().union(
        *(
            _ordered_interactions(
                workflow.operation_sequence,
                target.ordered_interaction_depth,
            )
            for workflow in workflows
        ),
        set(),
    )
    covered_ordered = set().union(
        *(
            _ordered_interactions(
                tuple(str(action["operation"]) for action in case.actions),
                target.ordered_interaction_depth,
            )
            for case in cases
        ),
        set(),
    )
    return {
        "schema_version": WORLD_COMPOSITION_COVERAGE_SCHEMA_VERSION,
        "coverage_target": target.to_dict(),
        "generated_case_count": len(cases),
        "exhaustive_enumeration_claim": False,
        "denominators": {
            "discrete_levels": len(required_levels),
            "discrete_pair_interactions": len(required_pairs),
            "continuous_strata": required_strata,
            "ordered_operation_interactions": len(required_ordered),
        },
        "covered": {
            "discrete_levels": len(covered_levels.intersection(required_levels)),
            "discrete_pair_interactions": len(covered_pairs.intersection(required_pairs)),
            "continuous_strata": len(covered_strata),
            "ordered_operation_interactions": len(
                covered_ordered.intersection(required_ordered)
            ),
        },
        "discrete_row_count": len(discrete_rows),
        "continuous_sample_count": len(continuous_rows) if continuous_axes else 0,
        "workflow_template_count": len(workflows),
        "attempted_case_count": len(cases) + len(failures),
        "successful_case_count": len(cases),
        "failure_count": len(failures),
        "failures": deepcopy(failures),
    }


def generate_world_composition_coverage(
    base_request: Mapping[str, Any],
    *,
    suite_id: str,
    discrete_axes: Sequence[DiscreteCoverageAxis] = (),
    continuous_axes: Sequence[ContinuousCoverageAxis] = (),
    workflows: Sequence[OrderedWorkflowTemplate],
    target: CompositionCoverageTarget | None = None,
) -> CompositionCoverageSuite:
    """Generate and compile a finite suite satisfying the declared coverage target."""

    if not suite_id.strip():
        raise ValueError("suite_id must be non-empty")
    coverage_target = target or CompositionCoverageTarget()
    discrete_axis_tuple = tuple(discrete_axes)
    continuous_axis_tuple = tuple(continuous_axes)
    workflow_tuple = tuple(workflows)
    if not workflow_tuple:
        raise ValueError("at least one workflow template is required")
    discrete_ids = {axis.axis_id for axis in discrete_axis_tuple}
    continuous_ids = {axis.axis_id for axis in continuous_axis_tuple}
    if discrete_ids.intersection(continuous_ids):
        raise ValueError("discrete and continuous axis IDs must be disjoint")
    referenced_axes = set().union(
        *(
            _axis_placeholders(action)
            for workflow in workflow_tuple
            for action in workflow.actions
        ),
        set(),
    )
    unknown_axes = sorted(referenced_axes - continuous_ids)
    unused_axes = sorted(continuous_ids - referenced_axes)
    if unknown_axes:
        raise ValueError(f"workflows reference unknown continuous axes: {unknown_axes}")
    if unused_axes:
        raise ValueError(f"continuous axes are not bound into workflows: {unused_axes}")
    _validate_workflow_axis_units(workflow_tuple, continuous_axis_tuple)

    discrete_rows = pairwise_covering_rows(
        discrete_axis_tuple,
        seed=coverage_target.seed,
    )
    continuous_rows = latin_hypercube_coordinates(
        continuous_axis_tuple,
        sample_count=coverage_target.continuous_samples,
        seed=coverage_target.seed + 1,
    )
    case_count = max(len(discrete_rows), len(continuous_rows), len(workflow_tuple))
    cases: list[GeneratedCompositionCase] = []
    failures: list[dict[str, Any]] = []
    base = deepcopy(dict(base_request))
    base_composition_id = str(base.get("composition_id", suite_id)).strip() or suite_id
    for index in range(case_count):
        case_id = f"{suite_id}-case-{index + 1:04d}"
        request = deepcopy(base)
        request["composition_id"] = f"{base_composition_id}-coverage-{index + 1:04d}"
        discrete_row = discrete_rows[index % len(discrete_rows)]
        for axis in discrete_axis_tuple:
            value = discrete_row[axis.axis_id]
            for path in axis.bindings:
                _set_request_binding(request, path, value)
        coordinates = continuous_rows[index % len(continuous_rows)]
        workflow = workflow_tuple[index % len(workflow_tuple)]
        actions = tuple(
            _materialize_value(action, coordinates) for action in workflow.actions
        )
        try:
            compiled = compile_world_composition(request)
            for action_index, action in enumerate(actions):
                operation = str(action.get("operation", ""))
                if operation not in compiled.task_spec.allowed_operations:
                    raise ValueError(
                        f"workflow operation {operation!r} is outside the compiled task surface"
                    )
                schema_result = validate_action_schema(action)
                if not schema_result.valid:
                    raise ValueError(
                        f"workflow action {action_index} is invalid: "
                        + "; ".join(schema_result.errors)
                    )
        except (TypeError, ValueError) as exc:
            failures.append(
                {
                    "case_id": case_id,
                    "workflow_id": workflow.workflow_id,
                    "error": str(exc),
                }
            )
            continue
        coordinate_payload: dict[str, dict[str, float | str]] = {
            axis.axis_id: {
                "value": coordinates[axis.axis_id],
                "unit": axis.unit,
            }
            for axis in continuous_axis_tuple
        }
        cases.append(
            GeneratedCompositionCase(
                case_id=case_id,
                request=request,
                discrete_levels=deepcopy(discrete_row),
                continuous_coordinates=coordinate_payload,
                workflow_id=workflow.workflow_id,
                actions=actions,
                compiled=compiled,
            )
        )

    report = _coverage_report(
        target=coverage_target,
        discrete_axes=discrete_axis_tuple,
        discrete_rows=discrete_rows,
        continuous_axes=continuous_axis_tuple,
        continuous_rows=continuous_rows,
        workflows=workflow_tuple,
        cases=cases,
        failures=failures,
    )
    if failures:
        raise WorldCompositionCoverageError(
            f"coverage generation rejected {len(failures)} of {case_count} case(s)",
            report=report,
        )
    expected_coverage = report["denominators"]
    actual_coverage = report["covered"]
    if expected_coverage != actual_coverage:
        raise WorldCompositionCoverageError(
            "coverage generation did not satisfy the frozen target",
            report=report,
        )
    return CompositionCoverageSuite(
        suite_id=suite_id,
        target=coverage_target,
        cases=tuple(cases),
        report=report,
    )


__all__ = [
    "WORLD_COMPOSITION_COVERAGE_SCHEMA_VERSION",
    "CompositionCoverageSuite",
    "CompositionCoverageTarget",
    "ContinuousCoverageAxis",
    "DiscreteCoverageAxis",
    "GeneratedCompositionCase",
    "OrderedWorkflowTemplate",
    "WorldCompositionCoverageError",
    "generate_world_composition_coverage",
    "latin_hypercube_coordinates",
    "pairwise_covering_rows",
]
