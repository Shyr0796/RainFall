import os

os.environ["RAINFALL_FORCE_CPU"] = "1"

import numpy as np

from rainfall_ca.geospatial import (
    load_urban_domain,
    prepare_urban_domain,
    save_urban_domain,
)


def test_shapefile_buildings_align_and_burn_into_dem(tmp_path):
    import fiona
    import rasterio
    from rasterio.transform import from_origin

    dem_path = tmp_path / "terrain.tif"
    shape_path = tmp_path / "buildings.shp"
    transform = from_origin(500_000.0, 100.0, 2.0, 2.0)
    terrain = np.full((10, 10), 100.0, dtype=np.float32)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs="EPSG:32633",
        transform=transform,
    ) as dst:
        dst.write(terrain, 1)

    schema = {
        "geometry": "Polygon",
        "properties": {"height": "float", "ground": "float"},
    }
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            (500_004.0, 92.0),
            (500_008.0, 92.0),
            (500_008.0, 96.0),
            (500_004.0, 96.0),
            (500_004.0, 92.0),
        ]],
    }
    with fiona.open(
        shape_path,
        "w",
        driver="ESRI Shapefile",
        crs="EPSG:32633",
        schema=schema,
    ) as vector:
        vector.write(
            {"geometry": polygon, "properties": {"height": 12.0, "ground": 100.0}}
        )

    domain = prepare_urban_domain(
        dem_path, shape_path, height_field="height", default_height_m=8.0
    )
    assert domain.grid.crs == "EPSG:32633"
    assert domain.grid.cell_size_x_m == 2.0
    assert int(domain.building_mask.sum()) == 4
    assert np.all(domain.surface_dem_m[domain.building_mask] == 112.0)
    assert domain.audit["building_plan_area_m2"] == 16.0
    assert domain.audit["solid_volume_proxy_m3"] == 192.0

    stored = save_urban_domain(domain, tmp_path / "domain.npz")
    loaded = load_urban_domain(stored)
    assert np.array_equal(loaded.building_mask, domain.building_mask)
    assert np.array_equal(loaded.surface_dem_m, domain.surface_dem_m)
    assert loaded.grid.crs == domain.grid.crs


def test_vertical_units_and_datum_contract_prevent_feet_meter_confusion(tmp_path):
    import fiona
    import rasterio
    from rasterio.transform import from_origin

    dem_path = tmp_path / "terrain_feet.tif"
    shape_path = tmp_path / "buildings_feet.shp"
    transform = from_origin(900_000.0, 120_000.0, 3.28084, 3.28084)
    terrain_ft = np.full((8, 8), 100.0, dtype=np.float32)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="float32",
        crs="EPSG:2263",
        transform=transform,
    ) as dst:
        dst.write(terrain_ft, 1)
    schema = {
        "geometry": "Polygon",
        "properties": {"HEIGHTROOF": "float", "GROUNDELEV": "float"},
    }
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            (900_006.56168, 119_986.87664),
            (900_013.12336, 119_986.87664),
            (900_013.12336, 119_993.43832),
            (900_006.56168, 119_993.43832),
            (900_006.56168, 119_986.87664),
        ]],
    }
    with fiona.open(
        shape_path, "w", driver="ESRI Shapefile", crs="EPSG:2263", schema=schema
    ) as vector:
        vector.write(
            {
                "geometry": polygon,
                "properties": {"HEIGHTROOF": 30.0, "GROUNDELEV": 100.0},
            }
        )

    foot_to_m = 0.3048
    domain = prepare_urban_domain(
        dem_path,
        shape_path,
        height_field="HEIGHTROOF",
        vertical_scale_to_m=foot_to_m,
        building_height_scale_to_m=foot_to_m,
        ground_elevation_field="GROUNDELEV",
        building_ground_scale_to_m=foot_to_m,
        dem_vertical_datum="NAVD88",
        building_vertical_datum="NAVD88",
        roof_base_source="building_ground",
        missing_height_policy="error",
        max_ground_mismatch_m=0.01,
        strict_vertical=True,
    )
    assert np.allclose(domain.terrain_dem_m[domain.building_mask], 30.48)
    assert np.allclose(domain.building_height_m[domain.building_mask], 9.144)
    assert np.allclose(domain.surface_dem_m[domain.building_mask], 39.624)
    assert domain.audit["ground_coupling_check"]["absolute_error_p95_m"] < 1e-5


def test_strict_vertical_rejects_unresolved_datum_mismatch(tmp_path):
    import fiona
    import rasterio
    import pytest
    from rasterio.transform import from_origin

    dem_path = tmp_path / "terrain.tif"
    shape_path = tmp_path / "buildings.shp"
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="float32",
        crs="EPSG:32633",
        transform=from_origin(0, 4, 1, 1),
    ) as dst:
        dst.write(np.zeros((4, 4), dtype=np.float32), 1)
    schema = {"geometry": "Polygon", "properties": {"height": "float", "base": "float"}}
    with fiona.open(
        shape_path, "w", driver="ESRI Shapefile", crs="EPSG:32633", schema=schema
    ) as vector:
        vector.write(
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]],
                },
                "properties": {"height": 5.0, "base": 0.0},
            }
        )
    with pytest.raises(ValueError, match="vertical datums differ"):
        prepare_urban_domain(
            dem_path,
            shape_path,
            height_field="height",
            ground_elevation_field="base",
            dem_vertical_datum="NAVD88",
            building_vertical_datum="NGVD29",
            strict_vertical=True,
        )
