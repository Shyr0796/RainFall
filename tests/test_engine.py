import os

os.environ["RAINFALL_FORCE_CPU"] = "1"

import numpy as np

from rainfall_ca.engine import (
    DrainageSink,
    FixedStageBoundary,
    MountainFloodCA,
    SimulationConfig,
    SpecifiedFluxBoundary,
    generate_mountain_dem,
)


def small_config(**overrides):
    values = {
        "grid_size": 48,
        "cell_size_m": 10.0,
        "relief_m": 80.0,
        "north_south_drop_m": 40.0,
        "rainfall_mm_h": 120.0,
        "infiltration_mm_h": 0.0,
        "max_dt_s": 0.5,
        "open_outlet": False,
    }
    values.update(overrides)
    return SimulationConfig(**values)


def test_dem_is_reproducible_and_mountainous():
    cfg = small_config(seed=77)
    first = generate_mountain_dem(cfg)
    second = generate_mountain_dem(cfg)
    other = generate_mountain_dem(small_config(seed=78))
    assert first.shape == (48, 48)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, other)
    assert float(np.ptp(first)) > 80.0
    assert np.isfinite(first).all()
    # Hydrologic conditioning removes strictly closed interior pits.
    interior = first[1:-1, 1:-1]
    lower_neighbour = np.minimum.reduce(
        [first[:-2, 1:-1], first[2:, 1:-1], first[1:-1, :-2], first[1:-1, 2:]]
    )
    assert np.all(lower_neighbour < interior)


def test_rainfall_step_is_nonnegative_and_mass_conservative():
    sim = MountainFloodCA(small_config())
    sim.step(80)
    stats = sim.stats()
    assert np.min(sim.h) >= 0.0
    assert stats["rainfall_m3"] > 0.0
    assert stats["relative_mass_error"] < 2e-5


def test_uniform_water_on_flat_surface_stays_still():
    sim = MountainFloodCA(small_config(rainfall_mm_h=0.0))
    sim.dem.fill(10.0)
    sim.h.fill(0.08)
    initial = sim.h.copy()
    sim.step(12)
    assert np.allclose(sim.h, initial, atol=1e-7)
    assert np.max(np.abs(sim.qx)) == 0.0
    assert np.max(np.abs(sim.qy)) == 0.0


def test_level_water_surface_over_irregular_bed_is_well_balanced():
    sim = MountainFloodCA(small_config(rainfall_mm_h=0.0))
    level = float(np.max(sim.dem)) + 0.25
    sim.h[:] = level - sim.dem
    initial = sim.h.copy()
    sim.step(10)
    assert np.allclose(sim.h, initial, atol=2e-6)
    assert np.max(np.abs(sim.qx)) < 2e-6
    assert np.max(np.abs(sim.qy)) < 2e-6


def test_two_dimensional_flux_follows_known_diagonal_slope():
    sim = MountainFloodCA(
        small_config(rainfall_mm_h=0.0, max_dt_s=0.05, manning_n=0.03)
    )
    n = sim.config.grid_size
    y, x = np.mgrid[0:n, 0:n]
    expected_angle = np.deg2rad(30.0)
    slope = 0.01
    sim.dem[:] = 50.0 - sim.config.cell_size_m * slope * (
        np.cos(expected_angle) * x + np.sin(expected_angle) * y
    )
    sim.h.fill(0.10)
    sim.step(1)
    measured_angle = np.arctan2(float(np.mean(sim.qy)), float(np.mean(sim.qx)))
    assert abs(measured_angle - expected_angle) < np.deg2rad(0.5)


def test_open_outlet_removes_exactly_accounted_volume():
    sim = MountainFloodCA(small_config(rainfall_mm_h=0.0, open_outlet=True))
    sim.dem.fill(0.0)
    sim.h[-1, :] = 0.10
    initial_volume = float(np.sum(sim.h)) * sim.config.cell_size_m**2
    sim.step(1)
    final_volume = float(np.sum(sim.h)) * sim.config.cell_size_m**2
    assert sim.cumulative_outflow_m3 > 0.0
    assert abs(initial_volume - final_volume - sim.cumulative_outflow_m3) < 1e-3


def test_rainfall_stops_at_configured_duration():
    sim = MountainFloodCA(small_config(rain_duration_min=1.0, max_dt_s=1.5))
    while sim.time_s < 75.0:
        sim.step(8)
    rain_after_cutoff = sim.stats()["rainfall_m3"]
    assert sim.stats()["rain_active"] is False
    sim.step(40)
    assert abs(sim.stats()["rainfall_m3"] - rain_after_cutoff) < 1e-8


def test_water_centroid_moves_down_a_slope():
    sim = MountainFloodCA(small_config(rainfall_mm_h=0.0, manning_n=0.04))
    n = sim.config.grid_size
    sim.dem[:] = np.linspace(20.0, 0.0, n, dtype=np.float32)[:, None]
    sim.h[3:8, 15:33] = 0.12
    initial_volume = float(np.sum(sim.h))
    y = np.arange(n, dtype=np.float64)[:, None]
    initial_centroid = float(np.sum(sim.h * y) / np.sum(sim.h))
    sim.step(100)
    final_centroid = float(np.sum(sim.h * y) / np.sum(sim.h))
    assert final_centroid > initial_centroid + 0.2
    assert abs(float(np.sum(sim.h)) - initial_volume) / initial_volume < 2e-5


def test_buildings_exclude_storage_sources_and_face_fluxes():
    sim = MountainFloodCA(small_config(rainfall_mm_h=90.0, max_dt_s=0.2))
    terrain = np.zeros((12, 16), dtype=np.float32)
    buildings = np.zeros_like(terrain, dtype=bool)
    buildings[:, 8] = True
    sim.configure_domain(
        terrain,
        surface_dem_m=terrain + buildings * 10.0,
        cell_size_m=2.0,
        building_mask=buildings,
    )
    sim.update_controls(rain_center_x=0.25, rain_center_y=0.5, rain_width=0.45, rain_height=0.9)
    sim.step(100)
    assert np.all(sim.h[:, 8] == 0.0)
    assert np.all(sim.qx[:, 7] == 0.0)
    assert np.all(sim.qx[:, 8] == 0.0)
    assert sim.stats()["building_cells"] == 12
    assert sim.stats()["relative_mass_error"] < 2e-5


def test_named_flux_and_stage_boundaries_close_water_balance():
    sim = MountainFloodCA(
        small_config(rainfall_mm_h=0.0, max_dt_s=0.1, manning_n=0.03)
    )
    rows, cols = 16, 30
    terrain = np.tile(np.linspace(0.30, 0.0, cols, dtype=np.float32), (rows, 1))
    sim.configure_domain(terrain, cell_size_m=2.0)
    inlet_cells = np.column_stack((np.arange(5, 11), np.zeros(6, dtype=int)))
    outlet_cells = np.column_stack((np.arange(5, 11), np.full(6, cols - 1)))
    sim.configure_boundaries(
        inflows=[SpecifiedFluxBoundary("west_inlet", inlet_cells, 0.12)],
        stages=[FixedStageBoundary("east_stage", outlet_cells, 0.01, "depth")],
    )
    sim.step(400)
    stats = sim.stats()
    assert stats["boundary_inflow_by_name_m3"]["west_inlet"] > 0.0
    assert stats["boundary_outflow_by_name_m3"]["east_stage"] >= 0.0
    assert np.allclose(sim.h[outlet_cells[:, 0], outlet_cells[:, 1]], 0.01)
    assert stats["relative_mass_error"] < 3e-5


def test_spatial_rainfall_and_capacity_limited_drainage_are_accounted():
    sim = MountainFloodCA(small_config(rainfall_mm_h=0.0, max_dt_s=0.1))
    terrain = np.zeros((10, 12), dtype=np.float32)
    sim.configure_domain(terrain, cell_size_m=2.0)
    rainfall = np.zeros_like(terrain)
    rainfall[4:6, 4:8] = 36.0
    infiltration = np.zeros_like(terrain)
    roughness = np.full_like(terrain, 0.04)
    sim.set_spatial_fields(
        rainfall_mm_h=rainfall,
        infiltration_mm_h=infiltration,
        manning_n=roughness,
    )
    drain_cells = np.array([[4, 5], [5, 5]])
    sim.configure_boundaries(
        drainage=[DrainageSink("street_inlets", drain_cells, 1e-5)]
    )
    sim.step(100)
    stats = sim.stats()
    assert stats["rainfall_m3"] > 0.0
    assert stats["drainage_by_name_m3"]["street_inlets"] > 0.0
    assert stats["relative_mass_error"] < 3e-5
