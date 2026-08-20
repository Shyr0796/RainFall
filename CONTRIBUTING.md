# Contributing and Research Collaboration

RainFall is actively seeking **non-commercial research collaboration**.

## Priority collaboration areas

- dynamic-wave cellular automata and full shallow-water-equation baselines;
- GPU kernels, numerical stability, convergence, and reproducible benchmarks;
- urban DEM/DSM, buildings, roads, drainage networks, and vertical-datum QA;
- laboratory, benchmark, and blind real-event validation of depth, velocity,
  direction, arrival time, and mass balance;
- uncertainty quantification, data assimilation, impact assessment, and safe
  decision support.

## Propose a collaboration

Open a GitHub Issue whose title begins with `[Collaboration]` and include:

1. your team and institution;
2. the research question and intended non-commercial outcome;
3. data, benchmarks, models, observations, or compute resources you can provide;
4. expected responsibilities, publication plan, and approximate timeline;
5. data-governance, ethics, licensing, or confidentiality constraints.

Please do not upload restricted, personal, sensitive, or unlicensed third-party
data to an Issue or pull request.

## Contributions

Before opening a pull request:

- keep claims evidence-bounded: distinguish source checks, synthetic tests,
  benchmark verification, calibration, and independent real-event validation;
- preserve non-negative water depth and auditable source/sink/boundary accounting;
- add focused tests and document the validation layer actually completed;
- avoid committing downloaded papers, third-party raw datasets, generated caches,
  local service logs, or secrets;
- confirm that your contribution can be distributed under the repository license.

## Non-commercial license

By contributing, you agree that your contribution may be distributed under the
[PolyForm Noncommercial License 1.0.0](LICENSE). This repository does not grant
commercial-use rights. For industry collaboration or commercial licensing, open
an Issue beginning with `[Commercial Licensing]` before using the software.

## Scientific-use boundary

RainFall is a research prototype. Unless a specific configuration has completed
appropriate calibration and independent validation, outputs must not be presented
as operational forecasts, engineering certification, or public warning advice.
