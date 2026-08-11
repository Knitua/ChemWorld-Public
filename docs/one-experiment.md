# One complete experiment

An experimental agent does more than choose an endpoint. It reads a contract, makes a sequence of physically constrained requests, observes instruments, manages resources and decides when the lifecycle is complete.

## Explore the frozen 15-step trajectory

The controls below are generated from the sanitized `agent-instrument-use` report. Select a step with a mouse, touch or the arrow keys.

<div class="cw-explorer" data-cw-explorer data-source="../assets/data/representative-behavior-and-forks.json">
  <div class="cw-explorer-header">
    <h3>One persistent agent, one complete lifecycle</h3>
    <div data-cw-summary>Loading frozen public evidence…</div>
  </div>
  <div class="cw-step-strip" data-cw-step-strip role="list" aria-label="Committed experimental actions"></div>
  <div class="cw-step-detail" data-cw-step-detail aria-live="polite"></div>
</div>

<noscript><p class="cw-noscript">JavaScript is disabled. The full static action and observation table remains available below.</p></noscript>

## What changes after each action?

Three records stay separate:

1. **Transaction:** whether the requested action committed or rolled back.
2. **Public observation:** what the instrument-facing agent is allowed to see.
3. **Resource outcome:** process time, sample use and registered consequences.

This separation prevents an endpoint score from erasing how the result was obtained.

## Failure remains part of the record

The deterministic recovery example intentionally requests phase separation before the physical preconditions exist. The operation rolls back physical, RNG and ghost state, retains its declared attempt consequence, and is followed by a valid recovery path. The submitted failure is retained during exact replay.

## Same experiment, changed world

An experiment author can construct controlled parent–child worlds that share the public task, action schema, resources and typed action sequence while changing one registered private component. The agent is judged from public feedback—not from direct access to the component identity.

[Open the complete static trajectory, rollback and fork tables](representative-behavior.md){ .md-button }

!!! note "Interpretation boundary"
    The trajectory demonstrates interface use and auditable execution, not model superiority. The world-fork matrix qualifies registered software-model interventions; it does not establish physical-laboratory transfer.
