# Real-world Bridge

> **ChemWorld’s relationship to reality should not be reduced to whether one simulator looks “realistic enough.”**

The bridge question is whether virtual interaction reduces the experiments, risk or cost needed to adapt to an independent model, real dataset or narrow physical system.

!!! info "Current status"
    This is a validation roadmap. Public v0.4 is not an operational physical-laboratory product and contains no physical-transfer result.

## Validity ladder

| Level | Question |
| --- | --- |
| Contract validity | Are state, actions, conservation and replay internally correct? |
| Decision validity | Does the world create meaningful experimental trade-offs? |
| Causal validity | Do controlled interventions change responses and useful strategies? |
| Behavioral validity | Do conclusions persist across independent backends? |
| Transfer validity | Does virtual training reduce target-system experiments? |
| Numerical validity | Are predictions accurate for one specified real system? |

The public release primarily addresses the first three through bounded software qualification. Later levels require new independent evidence.

## What may transfer

Measurement strategy, exploration order, uncertainty handling, failure recovery, safety habits, change detection and few-shot adaptation may transfer even when a virtual optimum does not.

## What cannot be copied directly

Virtual reagent quantities, risk scores, yields, equipment settings or policy rankings cannot be treated as real recommendations without identity mapping, calibration, equipment constraints, safety review and independent validation.

## Bridge path

```text
Causal core → independent backend → real dataset
→ shadow-mode physical lab → approved narrow closed loop
```

A Bridge Pack should bind material identity, action and observation mappings, units, equipment limits, calibration data, uncertainty, safety approval, independent test data and replay provenance.

The primary metric is not zero-shot replication of a virtual recipe. It is transfer advantage at the same target-system budget—for example, how many target experiments are saved relative to learning from scratch.

Partition-like characterization is a lower-risk first candidate. Flow and electrochemical control offer stronger operational relevance but require shadow-mode safety and equipment validation. Crystallization and distillation should follow only after narrower bridges are established.

See [Limitations](limitations.md) and the [development repository](https://github.com/sunyrain/ChemWorld) for future research directions; candidate bridge work is not copied into the stable Public release.
