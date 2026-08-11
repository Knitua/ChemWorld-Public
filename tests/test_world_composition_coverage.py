from __future__ import annotations

import json
from itertools import combinations, product

import pytest

import chemworld


def _base_request() -> dict[str, object]:
    return {
        "schema_version": "chemworld-world-composition-0.1",
        "composition_id": "coverage-reaction-assay",
        "world_split": "public-dev",
        "components": [
            {"kind": "reaction", "role": "transformation", "parameters": {}},
            {"kind": "thermal", "role": "thermal", "parameters": {}},
            {"kind": "observation", "role": "measurement", "parameters": {}},
        ],
        "task": {
            "budget": 8,
            "resources": {"operation_budget": 8},
        },
    }


def _discrete_axes() -> tuple[chemworld.DiscreteCoverageAxis, ...]:
    return (
        chemworld.DiscreteCoverageAxis(
            axis_id="world_split",
            bindings=("world_split",),
            values=("public-dev", "public-test"),
        ),
        chemworld.DiscreteCoverageAxis(
            axis_id="instrument_profile",
            bindings=(
                "components.observation.parameters.instruments",
                "task.instruments",
            ),
            values=(
                ["hplc", "final_assay"],
                ["gc", "final_assay"],
                ["uvvis", "final_assay"],
            ),
        ),
        chemworld.DiscreteCoverageAxis(
            axis_id="reaction_family",
            bindings=("components.reaction.parameters.family",),
            values=("declared-family-a", "declared-family-b"),
        ),
    )


def _continuous_axes() -> tuple[chemworld.ContinuousCoverageAxis, ...]:
    return (
        chemworld.ContinuousCoverageAxis(
            axis_id="temperature_K",
            lower=310.0,
            upper=390.0,
            unit="K",
        ),
        chemworld.ContinuousCoverageAxis(
            axis_id="duration_s",
            lower=30.0,
            upper=600.0,
            unit="s",
        ),
    )


def _workflows() -> tuple[chemworld.OrderedWorkflowTemplate, ...]:
    return (
        chemworld.OrderedWorkflowTemplate(
            workflow_id="heat-then-assay",
            actions=(
                {"operation": "add_solvent", "volume_L": 0.03, "solvent": 2},
                {"operation": "add_reagent", "amount_mol": 0.01},
                {
                    "operation": "heat",
                    "target_temperature_K": {"coverage_axis": "temperature_K"},
                    "duration_s": {"coverage_axis": "duration_s"},
                    "stirring_speed_rpm": 600.0,
                },
                {"operation": "terminate"},
                {"operation": "measure", "instrument": "final_assay"},
            ),
        ),
        chemworld.OrderedWorkflowTemplate(
            workflow_id="wait-heat-then-assay",
            actions=(
                {"operation": "add_solvent", "volume_L": 0.03, "solvent": 2},
                {"operation": "add_reagent", "amount_mol": 0.01},
                {
                    "operation": "wait",
                    "duration_s": {"coverage_axis": "duration_s"},
                    "stirring_speed_rpm": 600.0,
                },
                {
                    "operation": "heat",
                    "target_temperature_K": {"coverage_axis": "temperature_K"},
                    "duration_s": {"coverage_axis": "duration_s"},
                    "stirring_speed_rpm": 600.0,
                },
                {"operation": "terminate"},
                {"operation": "measure", "instrument": "final_assay"},
            ),
        ),
    )


def test_pairwise_covering_rows_cover_every_discrete_pair_without_product_output() -> None:
    axes = _discrete_axes()
    rows = chemworld.world.pairwise_covering_rows(axes, seed=7)

    for left, right in combinations(axes, 2):
        covered = {
            (repr(row[left.axis_id]), repr(row[right.axis_id])) for row in rows
        }
        required = {
            (repr(left_value), repr(right_value))
            for left_value, right_value in product(left.values, right.values)
        }
        assert covered == required
    exhaustive_count = 1
    for axis in axes:
        exhaustive_count *= len(axis.values)
    assert len(rows) < exhaustive_count


def test_latin_hypercube_coordinates_cover_each_axis_stratum_once() -> None:
    axes = _continuous_axes()
    rows = chemworld.world.latin_hypercube_coordinates(axes, sample_count=7, seed=3)

    assert len(rows) == 7
    for axis in axes:
        strata = {
            min(
                int(
                    (row[axis.axis_id] - axis.lower)
                    / (axis.upper - axis.lower)
                    * len(rows)
                ),
                len(rows) - 1,
            )
            for row in rows
        }
        assert strata == set(range(len(rows)))


def test_generate_world_composition_coverage_reports_exact_denominators() -> None:
    suite = chemworld.generate_world_composition_coverage(
        _base_request(),
        suite_id="reaction-assay-coverage",
        discrete_axes=_discrete_axes(),
        continuous_axes=_continuous_axes(),
        workflows=_workflows(),
        target=chemworld.CompositionCoverageTarget(
            discrete_strength=2,
            continuous_samples=5,
            ordered_interaction_depth=2,
            seed=11,
        ),
    )

    assert suite.report["denominators"] == suite.report["covered"]
    assert suite.report["failure_count"] == 0
    assert suite.report["exhaustive_enumeration_claim"] is False
    assert suite.report["generated_case_count"] == len(suite.cases)
    assert suite.report["attempted_case_count"] == len(suite.cases)
    assert suite.report["successful_case_count"] == len(suite.cases)
    assert suite.report["continuous_sample_count"] == 5
    json.dumps(suite.to_dict(), allow_nan=False)
    assert len({case.case_id for case in suite.cases}) == len(suite.cases)
    assert len({case.request["composition_id"] for case in suite.cases}) == len(suite.cases)
    assert {case.workflow_id for case in suite.cases} == {
        "heat-then-assay",
        "wait-heat-then-assay",
    }
    for case in suite.cases:
        assert case.compiled.compatibility.compatible
        heat_action = next(action for action in case.actions if action["operation"] == "heat")
        assert isinstance(heat_action["target_temperature_K"], float)
        assert isinstance(heat_action["duration_s"], float)
        assert case.continuous_coordinates["temperature_K"]["unit"] == "K"


def test_generation_fails_closed_with_all_case_failures_reported() -> None:
    invalid_axis = chemworld.DiscreteCoverageAxis(
        axis_id="operation_surface",
        bindings=("task.operations",),
        values=(["measure", "terminate"],),
    )

    with pytest.raises(chemworld.WorldCompositionCoverageError) as exc:
        chemworld.generate_world_composition_coverage(
            _base_request(),
            suite_id="invalid-coverage",
            discrete_axes=(invalid_axis,),
            continuous_axes=_continuous_axes(),
            workflows=(_workflows()[0],),
            target=chemworld.CompositionCoverageTarget(continuous_samples=3, seed=1),
        )

    assert exc.value.report["failure_count"] == 3
    assert exc.value.report["attempted_case_count"] == 3
    assert exc.value.report["successful_case_count"] == 0
    assert len(exc.value.report["failures"]) == 3
    assert all("lifecycle_hole" in item["error"] for item in exc.value.report["failures"])


def test_continuous_axis_unit_must_match_bound_action_field() -> None:
    wrong_unit_axis = chemworld.ContinuousCoverageAxis(
        axis_id="temperature_K",
        lower=0.001,
        upper=0.010,
        unit="L",
    )
    temperature_workflow = chemworld.OrderedWorkflowTemplate(
        workflow_id="temperature-unit-check",
        actions=(
            {"operation": "add_solvent", "volume_L": 0.03, "solvent": 2},
            {"operation": "add_reagent", "amount_mol": 0.01},
            {
                "operation": "heat",
                "target_temperature_K": {"coverage_axis": "temperature_K"},
                "duration_s": 60.0,
                "stirring_speed_rpm": 600.0,
            },
            {"operation": "terminate"},
            {"operation": "measure", "instrument": "final_assay"},
        ),
    )

    with pytest.raises(ValueError, match="requires 'K'"):
        chemworld.generate_world_composition_coverage(
            _base_request(),
            suite_id="unit-mismatch-coverage",
            continuous_axes=(wrong_unit_axis,),
            workflows=(temperature_workflow,),
            target=chemworld.CompositionCoverageTarget(continuous_samples=3),
        )
