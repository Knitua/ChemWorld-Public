# Coverage-guided composition generation

ChemWorld generates a finite qualification suite from a declared coverage target. The
generator is not an enumerator of all possible worlds and its report explicitly records that
no exhaustive-coverage claim is made.

## Three coverage layers

| Layer | Qualification method | Reported denominator |
| --- | --- | ---: |
| Discrete authoring axes | deterministic pairwise covering rows | all declared value pairs across every pair of axes |
| Continuous workflow axes | seeded Latin hypercube samples | one stratum per sample and continuous axis |
| Ordered workflow interactions | contiguous operation subsequences at the declared depth | union of declared workflow interactions |

The emitted case count is the largest of the three finite requirements: pairwise rows,
continuous samples and workflow templates. Shorter designs are cycled so every required row,
sample and workflow appears at least once. The generator does not form their Cartesian
product.

## Public Python entry point

```python
import chemworld

suite = chemworld.generate_world_composition_coverage(
    base_request,
    suite_id="reaction-assay-coverage",
    discrete_axes=(
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
    ),
    continuous_axes=(
        chemworld.ContinuousCoverageAxis(
            axis_id="temperature_K",
            lower=310.0,
            upper=390.0,
            unit="K",
        ),
    ),
    workflows=(
        chemworld.OrderedWorkflowTemplate(
            workflow_id="heat-then-assay",
            actions=(
                {"operation": "add_solvent", "volume_L": 0.03, "solvent": 2},
                {"operation": "add_reagent", "amount_mol": 0.01},
                {
                    "operation": "heat",
                    "target_temperature_K": {
                        "coverage_axis": "temperature_K"
                    },
                    "duration_s": 600.0,
                    "stirring_speed_rpm": 600.0,
                },
                {"operation": "terminate"},
                {"operation": "measure", "instrument": "final_assay"},
            ),
        ),
    ),
    target=chemworld.CompositionCoverageTarget(
        discrete_strength=2,
        continuous_samples=8,
        ordered_interaction_depth=2,
        seed=0,
    ),
)
```

Discrete bindings may target `world_split`, task fields, nested task resource or evaluation
fields, and component parameters. One discrete value may bind multiple paths so an
instrument profile can update both the observation component and task surface atomically.

Continuous values enter workflows through an exact
`{"coverage_axis": "axis_id"}` placeholder. Every declared continuous axis must appear in at
least one workflow; unused coordinates are rejected rather than reported as covered.

## Fail-closed behavior

Every generated request is compiled through the same compatibility checker as an authored
world. Every materialized action must belong to the compiled operation surface and pass the
public action schema. If any case fails, generation raises `WorldCompositionCoverageError`
with a readable report containing the exact attempted denominator and every failed case; a
partial suite is not returned as successful output.

For a successful suite, `suite.report` contains:

- the frozen target and generated case count;
- exact required and covered counts for all three coverage layers;
- the number of pairwise rows, continuous samples and workflows;
- attempted, successful and failed case counts;
- an explicit `exhaustive_enumeration_claim: false` boundary; and
- a zero failure count with an empty failure list.

Coverage construction is therefore distinct from physical or transactional qualification.
The suite says which cases and ordered interactions were selected; later qualification must
execute them and report its own denominators and failures.
