import os

os.environ["RAINFALL_FORCE_CPU"] = "1"

from fastapi.testclient import TestClient
import numpy as np

import rainfall_ca.api as api_module
from rainfall_ca.api import app
from rainfall_ca.geospatial import GridMetadata, UrbanDomain, save_urban_domain

client = TestClient(app)


def test_home_and_info_are_available():
    home = client.get("/")
    assert home.status_code == 200
    assert "RainCell" in home.text
    info = client.get("/api/info")
    assert info.status_code == 200
    assert info.json()["model"].startswith("mass-conservative")
    report = client.get("/report")
    assert report.status_code == 200
    assert "技术与使用报告" in report.text


def test_reset_control_and_step_round_trip():
    config = {
        "grid_size": 48,
        "cell_size_m": 10,
        "seed": 4,
        "relief_m": 60,
        "north_south_drop_m": 30,
        "rainfall_mm_h": 100,
        "rain_duration_min": 60,
        "rain_center_x": 0.5,
        "rain_center_y": 0.2,
        "rain_width": 0.4,
        "rain_height": 0.3,
        "infiltration_mm_h": 4,
        "manning_n": 0.05,
        "max_dt_s": 0.5,
        "cfl": 0.35,
        "open_outlet": True,
    }
    reset = client.post("/api/reset", json=config)
    assert reset.status_code == 200
    assert reset.json()["shape"] == [48, 48]
    assert "dem_u16" in reset.json()

    control = client.patch(
        "/api/controls", json={"rainfall_mm_h": 140, "rain_duration_min": 45}
    )
    assert control.status_code == 200
    assert control.json()["config"]["rainfall_mm_h"] == 140
    assert control.json()["config"]["rain_duration_min"] == 45

    stepped = client.post("/api/step", json={"iterations": 5})
    assert stepped.status_code == 200
    payload = stepped.json()
    assert payload["stats"]["simulation_time_s"] > 0
    assert payload["stats"]["relative_mass_error"] < 2e-5
    assert len(payload["depth_u16"]) > 100


def test_prepared_domain_endpoint_rejects_path_traversal():
    response = client.post(
        "/api/domain/load-prepared", json={"domain_file": "../../outside.npz"}
    )
    assert response.status_code == 400


def test_prepared_urban_domain_loads_into_web_simulator(tmp_path, monkeypatch):
    terrain = np.zeros((8, 12), dtype=np.float32)
    buildings = np.zeros_like(terrain, dtype=bool)
    buildings[2:5, 5:7] = True
    surface = terrain + buildings * 9.0
    grid = GridMetadata(
        crs="EPSG:32650",
        transform=(2.0, 0.0, 400000.0, 0.0, -2.0, 1000.0),
        width=12,
        height=8,
        cell_size_x_m=2.0,
        cell_size_y_m=2.0,
        bounds=(400000.0, 984.0, 400024.0, 1000.0),
    )
    domain = UrbanDomain(
        terrain,
        surface,
        np.ones_like(buildings),
        buildings,
        buildings.astype(np.float32) * 9.0,
        grid,
        {"test": True},
    )
    save_urban_domain(domain, tmp_path / "city.npz")
    monkeypatch.setattr(api_module, "PREPARED_DOMAIN_DIR", tmp_path)
    response = client.post(
        "/api/domain/load-prepared", json={"domain_file": "city.npz"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["shape"] == [8, 12]
    assert payload["grid"]["crs"] == "EPSG:32650"
    assert payload["stats"]["building_cells"] == 6
