# Agent Tracks

ChemWorld supports three interaction levels over the same world and task contracts. They ask different questions and should not share a leaderboard without an explicit conversion protocol.

## Track A — Campaign Design

The Agent proposes a complete experiment or recipe. This is the shortest route for black-box optimization, design of experiments and cross-experiment adaptation.

**Agent owns:** recipe choice, measurement plan and allocation across experiments.  
**Runtime owns:** legal execution, state transitions, resource accounting and final evaluation.

## Track B — Procedure Execution

The Agent selects one operation at a time: charge material, set conditions, measure, work up, recover, terminate and request final assay.

This track exposes procedural autonomy. A good recipe does not rescue an Agent that cannot execute its preconditions or close the lifecycle.

## Track C — Process Control

The Agent selects bounded equipment setpoints or process actions while the world evolves. This is intended for flow, electrochemical and other tasks where the control trajectory matters.

Public v0.4 implements a bounded setpoint/process abstraction. It is not a universal high-frequency controller and does not model every real actuator.

## What remains shared

All tracks bind the same public task identifiers, world/scenario split, resource ledger, transaction semantics, replay rules and evidence boundary. Hidden truth remains evaluator-owned.

## Browser and Python access

The [Student Lab](student-lab.md) exposes legal operation composition. The [Agent Observatory](agent-observatory.md) runs eight provider-free built-in policies through the official runner. Custom policies, external models and advanced adapters connect in Python through [Build an Agent](agents.md); arbitrary code and provider credentials are deliberately not accepted by the public browser service.

When comparing tracks, report operation counts, measurements, failures, lifecycle completion and method resources alongside task outcomes.
