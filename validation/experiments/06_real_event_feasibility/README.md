# 06 Real-event feasibility: Fourmile Creek 2018

## Purpose

This lane tests whether an openly documented real event can be represented by the *current* RainFall model. It is an input-and-physics audit first, not a claim of completed real-event validation.

## Available observations

- NOAA station precipitation totals reported for 30 June--1 July 2018.
- Continuous discharge at USGS streamgages 05485605 and 05485640.
- Eleven surveyed high-water-mark elevations along 21 river miles.
- USGS 3DEP elevation products are discoverable for the study area.

Primary event page: https://www.usgs.gov/publications/flood-june-30-july-1-2018-fourmile-creek-basin-near-ankeny-iowa

## Compatibility decision

Status: **partial / not yet simulation-ready**.

The event is dominated by routed channel flooding over a 120-square-mile basin. The current RainFall prototype applies direct rainfall to a small raster, has a synthetic outlet, and does not represent a surveyed river channel, tributary inflows, bridges, culverts, or stage/discharge boundary conditions. Running it unchanged would create a numerical picture but not a defensible event reconstruction.

## Completed data audit

The official USGS NWIS query returned 480 approved 15-minute observations for each gauge from 29 June through 3 July 2018. The observed peaks are:

- site `05485605`: 10,000 ft³/s and 16.17 ft gage height at 01:00 CDT on 1 July;
- site `05485640`: 12,000 ft³/s and 17.51 ft gage height at 05:15 CDT on 1 July.

Table 3 of the official report was transcribed to `data/processed/high_water_marks_table3.csv`: eleven surveyed bridge locations plus the recorded-stage location at gauge `05485605`. Elevations use NAVD 88. The report states HWM uncertainty ranges from 0.05 to 0.4 ft; this uncertainty must be included in any later score.

Actual artifacts are under `results/`. `event_data_audit.json` is explicitly marked `data_audit_completed_simulation_blocked` because no simulated series exists yet.

## Evidence-preserving next experiment

1. Download and clip 3DEP lidar-derived DEM to a small reach.
2. Acquire gauge rainfall/QPE and both USGS hydrographs in a common time zone.
3. Add a channel/bathymetry representation and prescribed discharge/stage boundaries.
4. Calibrate on one reach or earlier event only; freeze parameters.
5. Validate peak stage against the 11 high-water marks, hydrograph timing against the two gauges, and inundation extent where independent observations exist.

Until steps 1--3 exist, this lane must not be reported as a failed or successful RainFall physics validation.
