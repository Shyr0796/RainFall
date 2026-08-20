from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .engine import MountainFloodCA, SimulationConfig
from .geospatial import load_urban_domain

WEB_DIR = Path(__file__).with_name("web")
PROJECT_DIR = WEB_DIR.parents[2]
REPORT_PATH = PROJECT_DIR / "docs" / "RainCell_GPU_技术与使用报告.html"
app = FastAPI(title="RainCell GPU", version="0.1.0")
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

simulation = MountainFloodCA()
simulation_lock = asyncio.Lock()
PREPARED_DOMAIN_DIR = PROJECT_DIR / "data" / "processed"


class ConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grid_size: int = Field(192, ge=48, le=384)
    cell_size_m: float = Field(10.0, ge=1.0, le=100.0)
    seed: int = Field(42, ge=0, le=2_147_483_647)
    relief_m: float = Field(180.0, ge=20.0, le=800.0)
    north_south_drop_m: float = Field(110.0, ge=0.0, le=1200.0)
    rainfall_mm_h: float = Field(95.0, ge=0.0, le=500.0)
    rain_duration_min: float = Field(60.0, ge=1.0, le=360.0)
    rain_center_x: float = Field(0.50, ge=0.0, le=1.0)
    rain_center_y: float = Field(0.22, ge=0.0, le=1.0)
    rain_width: float = Field(0.48, ge=0.05, le=1.0)
    rain_height: float = Field(0.30, ge=0.05, le=1.0)
    infiltration_mm_h: float = Field(8.0, ge=0.0, le=200.0)
    manning_n: float = Field(0.055, ge=0.01, le=0.2)
    max_dt_s: float = Field(1.5, ge=0.02, le=10.0)
    cfl: float = Field(0.35, ge=0.05, le=0.8)
    open_outlet: bool = True


class ControlPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rainfall_mm_h: float | None = Field(None, ge=0.0, le=500.0)
    rain_duration_min: float | None = Field(None, ge=1.0, le=360.0)
    rain_center_x: float | None = Field(None, ge=0.0, le=1.0)
    rain_center_y: float | None = Field(None, ge=0.0, le=1.0)
    rain_width: float | None = Field(None, ge=0.05, le=1.0)
    rain_height: float | None = Field(None, ge=0.05, le=1.0)
    infiltration_mm_h: float | None = Field(None, ge=0.0, le=200.0)
    manning_n: float | None = Field(None, ge=0.01, le=0.2)
    max_dt_s: float | None = Field(None, ge=0.02, le=10.0)
    cfl: float | None = Field(None, ge=0.05, le=0.8)
    open_outlet: bool | None = None


class StepPayload(BaseModel):
    iterations: int = Field(4, ge=1, le=64)


class PreparedDomainPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain_file: str = Field(min_length=1, max_length=240)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/report")
async def report() -> FileResponse:
    return FileResponse(REPORT_PATH)


@app.get("/api/info")
async def info() -> dict[str, Any]:
    return {
        "name": "RainCell GPU",
        "model": "mass-conservative local-inertial CA prototype",
        "backend": simulation.backend,
        "device_name": simulation.device_name,
        "gpu_active": simulation.backend == "cuda",
        "config": asdict(simulation.config),
    }


@app.get("/api/frame")
async def frame() -> dict[str, Any]:
    async with simulation_lock:
        return simulation.frame(include_dem=True)


@app.post("/api/reset")
async def reset(payload: ConfigPayload) -> dict[str, Any]:
    global simulation
    try:
        config = SimulationConfig(**payload.model_dump()).validated()
        async with simulation_lock:
            simulation = MountainFloodCA(config)
            return simulation.frame(include_dem=True)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Unable to reset simulation: {exc}"
        ) from exc


@app.patch("/api/controls")
async def controls(payload: ControlPayload) -> dict[str, Any]:
    values = payload.model_dump(exclude_none=True)
    async with simulation_lock:
        simulation.update_controls(**values)
        return {"config": asdict(simulation.config), "stats": simulation.stats()}


@app.post("/api/step")
async def step(payload: StepPayload) -> dict[str, Any]:
    async with simulation_lock:
        simulation.step(payload.iterations)
        return simulation.frame(include_dem=False)


@app.post("/api/domain/load-prepared")
async def load_prepared_domain(payload: PreparedDomainPayload) -> dict[str, Any]:
    """Load a pre-audited domain from data/processed without arbitrary path access."""

    global simulation
    root = PREPARED_DOMAIN_DIR.resolve()
    source = (root / payload.domain_file).resolve()
    if not source.is_relative_to(root) or source.suffix.lower() != ".npz":
        raise HTTPException(status_code=400, detail="Domain must be an .npz under data/processed")
    if not source.is_file():
        raise HTTPException(status_code=404, detail=f"Prepared domain not found: {payload.domain_file}")
    try:
        domain = load_urban_domain(source)
        config = SimulationConfig(**asdict(simulation.config)).validated()
        replacement = MountainFloodCA(config)
        replacement.configure_domain(
            domain.terrain_dem_m,
            surface_dem_m=domain.surface_dem_m,
            cell_size_m=domain.cell_size_m,
            active_mask=domain.active_mask,
            building_mask=domain.building_mask,
            grid_metadata=asdict(domain.grid),
        )
        async with simulation_lock:
            simulation = replacement
            return simulation.frame(include_dem=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Unable to load domain: {exc}") from exc
