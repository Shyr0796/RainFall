# 03 UK Environment Agency 2D hydraulic benchmarks

The Environment Agency SC120002 package is a **standard numerical model
benchmark**, not field observations.  Its terrain, boundary conditions and
published reference/model outputs are useful for solver capability testing and
model intercomparison; they must not be labelled as real-event validation.

Official sources:

- Project page: https://www.gov.uk/flood-and-coastal-erosion-risk-management-research-reports/2d-benchmarking-evaluating-the-latest-generation-of-the-hydraulic-models-for-fcrm
- Model-data ZIP (linked by the project page): https://assets.publishing.service.gov.uk/media/6033a9bbd3bf7f72182e99ca/Benchmarking_Model_Data.zip
- Technical report: https://assets.publishing.service.gov.uk/media/6033a943d3bf7f721f4b0d49/_SC120002_Benchmarking_2D_hydraulic_models_Report.pdf

The download is retained byte-for-byte under `data/raw/`, with SHA-256 and an
extracted-file inventory. `code/audit_and_adapt.py` recursively extracts the
per-test archives, identifies usable rasters, and prepares a parsing smoke test.

`code/run_test1_stage_boundary.py` adapts official Test 1 at the specified 10 m
model resolution. It crops the 2 m source DEM to the official 700 x 100 m domain,
block-averages it to 10 m, embeds the rectangle inside closed high walls, applies
the official time-varying left water-level boundary, and runs to 20 hours. The
boundary is an **experiment-only wrapper** around `MountainFloodCA`; the core API
still lacks a generic prescribed-stage boundary. Boundary exchange is therefore
tracked explicitly in the experiment water balance.

Run after downloading:

```bash
UV_CACHE_DIR=/tmp/rainfall_uv_cache uv run python \
  validation/experiments/03_uk_ea_benchmarks/code/audit_and_adapt.py

RAINFALL_FORCE_CPU=1 UV_CACHE_DIR=/tmp/rainfall_uv_cache uv run python \
  validation/experiments/03_uk_ea_benchmarks/code/run_test1_stage_boundary.py
```

## Completed result

- Official archive: 52,456,734 bytes; SHA-256
  `388c2789570e5975fe909033e34bedbe5d7bde5e6d7f9b7d7c1eaf04e58bc732`;
  ZIP integrity test passed.
- Audit: 8 nested test archives, 64 files after recursive extraction, and 8
  readable DEM grids.
- Test 1: full 20 h run completed in 50,083 adaptive steps. Point 1 peak/final
  levels were 10.35160/10.25531 m; Point 2 levels were
  10.35179/10.25533 m. Against the report's approximate 10.35 m peak and
  10.25 m final expectations, absolute deviations were 0.0016--0.0018 m and
  0.0053 m, respectively.
- Water balance including the imposed-stage exchange closed to
  `3.17e-7` relative error.

These close scalar outcomes demonstrate a successful implementation-level
reproduction of this standard wetting/drying benchmark under the documented
10 m resampling and experiment boundary wrapper. They do not establish accuracy
against nature, do not validate a general stage-boundary API, and do not show
that the other seven EA tests are supported.
