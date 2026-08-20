"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const canvas = $("#simulationCanvas");
const ctx = canvas.getContext("2d", { alpha: false });

const state = {
  running: false,
  busy: false,
  view: "terrain",
  n: 0,
  dem: null,
  terrainRgb: null,
  depth: null,
  speed: null,
  dirX: null,
  dirY: null,
  depthScale: 1,
  speedScale: 1,
  config: null,
  liveTimer: null,
};

function decodeBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function decodeU16(base64) {
  const bytes = decodeBytes(base64);
  return new Uint16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
}

function decodeI8(base64) {
  const bytes = decodeBytes(base64);
  return new Int8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(node._timer);
  node._timer = setTimeout(() => node.classList.remove("visible"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `请求失败 (${response.status})`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* no-op */ }
    throw new Error(detail);
  }
  return response.json();
}

function interpolate(a, b, t) { return a + (b - a) * t; }

function terrainColor(t) {
  const stops = [
    [0.00, [35, 70, 54]],
    [0.25, [77, 103, 65]],
    [0.52, [135, 126, 83]],
    [0.75, [153, 142, 110]],
    [1.00, [226, 222, 203]],
  ];
  for (let i = 1; i < stops.length; i += 1) {
    if (t <= stops[i][0]) {
      const [p0, c0] = stops[i - 1];
      const [p1, c1] = stops[i];
      const f = (t - p0) / (p1 - p0);
      return c0.map((v, j) => interpolate(v, c1[j], f));
    }
  }
  return stops.at(-1)[1];
}

function buildTerrainTexture() {
  if (!state.dem) return;
  const n = state.n;
  const rgb = new Uint8ClampedArray(n * n * 3);
  for (let y = 0; y < n; y += 1) {
    for (let x = 0; x < n; x += 1) {
      const i = y * n + x;
      const t = state.dem[i] / 65535;
      const left = state.dem[y * n + Math.max(0, x - 1)];
      const right = state.dem[y * n + Math.min(n - 1, x + 1)];
      const up = state.dem[Math.max(0, y - 1) * n + x];
      const down = state.dem[Math.min(n - 1, y + 1) * n + x];
      const shade = Math.max(0.52, Math.min(1.24, 0.90 + (left - right + up - down) / 4200));
      const color = terrainColor(t);
      rgb[i * 3] = color[0] * shade;
      rgb[i * 3 + 1] = color[1] * shade;
      rgb[i * 3 + 2] = color[2] * shade;
    }
  }
  state.terrainRgb = rgb;
}

function waterColor(value, mode) {
  const t = Math.max(0, Math.min(1, Math.sqrt(value)));
  if (mode === "speed") {
    return [interpolate(20, 221, t), interpolate(63, 255, t), interpolate(115, 184, t)];
  }
  return [interpolate(31, 179, t), interpolate(185, 239, t), interpolate(226, 255, t)];
}

function render() {
  if (!state.terrainRgb || !state.depth) return;
  const n = state.n;
  if (canvas.width !== n) { canvas.width = n; canvas.height = n; }
  const image = ctx.createImageData(n, n);
  for (let i = 0; i < n * n; i += 1) {
    const baseIdx = i * 3;
    const outIdx = i * 4;
    const depthNorm = state.depth[i] / 65535;
    const speedNorm = state.speed[i] / 65535;
    let r = state.terrainRgb[baseIdx];
    let g = state.terrainRgb[baseIdx + 1];
    let b = state.terrainRgb[baseIdx + 2];

    if (state.view === "depth") {
      r = 10; g = 26; b = 38;
      if (depthNorm > 0) {
        const c = waterColor(depthNorm, "depth");
        const a = Math.min(1, 0.24 + Math.sqrt(depthNorm) * 0.95);
        r = interpolate(r, c[0], a); g = interpolate(g, c[1], a); b = interpolate(b, c[2], a);
      }
    } else if (state.view === "speed") {
      r *= 0.35; g *= 0.35; b *= 0.42;
      if (speedNorm > 0 && depthNorm > 0) {
        const c = waterColor(speedNorm, "speed");
        const a = Math.min(1, 0.30 + Math.sqrt(speedNorm) * 0.95);
        r = interpolate(r, c[0], a); g = interpolate(g, c[1], a); b = interpolate(b, c[2], a);
      }
    } else if (depthNorm > 0) {
      const c = waterColor(depthNorm, "depth");
      const a = Math.min(0.93, 0.16 + Math.sqrt(depthNorm) * 0.86);
      r = interpolate(r, c[0], a); g = interpolate(g, c[1], a); b = interpolate(b, c[2], a);
    }

    image.data[outIdx] = r;
    image.data[outIdx + 1] = g;
    image.data[outIdx + 2] = b;
    image.data[outIdx + 3] = 255;
  }
  ctx.putImageData(image, 0, 0);
  drawVectorsAndRainBox();
}

function drawVectorsAndRainBox() {
  const n = state.n;
  const stride = Math.max(10, Math.round(n / 14));
  ctx.save();
  ctx.lineWidth = Math.max(0.45, n / 420);
  ctx.strokeStyle = "rgba(240,255,233,.82)";
  ctx.fillStyle = "rgba(240,255,233,.82)";
  if (state.view !== "depth") {
    for (let y = Math.floor(stride / 2); y < n; y += stride) {
      for (let x = Math.floor(stride / 2); x < n; x += stride) {
        const i = y * n + x;
        const d = state.depth[i] / 65535 * state.depthScale;
        const s = state.speed[i] / 65535 * state.speedScale;
        if (d < 0.001 || s < 0.02) continue;
        const ux = state.dirX[i] / 127;
        const uy = state.dirY[i] / 127;
        const len = stride * 0.34;
        const x2 = x + ux * len;
        const y2 = y + uy * len;
        ctx.beginPath(); ctx.moveTo(x - ux * len * 0.35, y - uy * len * 0.35); ctx.lineTo(x2, y2); ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x2, y2);
        ctx.lineTo(x2 - ux * 2.0 + uy * 1.3, y2 - uy * 2.0 - ux * 1.3);
        ctx.lineTo(x2 - ux * 2.0 - uy * 1.3, y2 - uy * 2.0 + ux * 1.3);
        ctx.closePath(); ctx.fill();
      }
    }
  }

  const c = state.config;
  const left = (c.rain_center_x - c.rain_width / 2) * n;
  const top = (c.rain_center_y - c.rain_height / 2) * n;
  ctx.strokeStyle = "rgba(255,138,56,.95)";
  ctx.lineWidth = Math.max(1, n / 220);
  ctx.setLineDash([n / 70, n / 90]);
  ctx.strokeRect(left, top, c.rain_width * n, c.rain_height * n);
  ctx.restore();
}

function absorbFrame(data, includesDem = false) {
  state.n = data.shape[0];
  state.depth = decodeU16(data.depth_u16);
  state.speed = decodeU16(data.speed_u16);
  state.dirX = decodeI8(data.dir_x_i8);
  state.dirY = decodeI8(data.dir_y_i8);
  state.depthScale = data.depth_scale_m;
  state.speedScale = data.speed_scale_m_s;
  state.config = data.config;
  const scaleMetres = state.config.grid_size * state.config.cell_size_m / 4;
  $("#scaleLabel").textContent = scaleMetres >= 1000 ? `${(scaleMetres / 1000).toFixed(1)} km` : `${Math.round(scaleMetres)} m`;
  if (includesDem && data.dem_u16) {
    state.dem = decodeU16(data.dem_u16);
    buildTerrainTexture();
  }
  updateStats(data.stats);
  render();
}

function formatClock(seconds) {
  const s = Math.floor(seconds % 60).toString().padStart(2, "0");
  const m = Math.floor((seconds / 60) % 60).toString().padStart(2, "0");
  const h = Math.floor(seconds / 3600).toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function formatVolume(value) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M m³`;
  if (value >= 10_000) return `${(value / 1000).toFixed(1)}k m³`;
  return `${value.toFixed(1)} m³`;
}

function updateStats(stats) {
  $("#simClock").textContent = formatClock(stats.simulation_time_s);
  $("#maxDepth").textContent = stats.max_depth_m.toFixed(3);
  $("#maxSpeed").textContent = stats.max_speed_m_s.toFixed(3);
  $("#storage").textContent = stats.storage_m3 < 1000 ? stats.storage_m3.toFixed(1) : (stats.storage_m3 / 1000).toFixed(1) + "k";
  $("#massError").textContent = (stats.relative_mass_error * 100).toFixed(4);
  $("#stepRate").textContent = stats.steps_per_second ? Math.round(stats.steps_per_second).toLocaleString() : "—";
  $("#rainVolume").textContent = formatVolume(stats.rainfall_m3);
  $("#infiltrationVolume").textContent = formatVolume(stats.infiltration_m3);
  $("#outflowVolume").textContent = formatVolume(stats.outflow_m3);
  $("#rainStatus").textContent = stats.rain_active ? "可控降雨区 · 降雨中" : "可控降雨区 · 降雨已结束";
  $("#timelineProgress").style.width = `${Math.min(100, (stats.simulation_time_s % 3600) / 36)}%`;
  const label = state.view === "speed" ? `${state.speedScale.toFixed(2)} m/s` : `${state.depthScale.toFixed(2)} m`;
  $("#legendMax").textContent = label;
}

function collectConfig() {
  return {
    grid_size: Number($("#grid_size").value),
    cell_size_m: Number($("#cell_size_m").value),
    seed: Number($("#seed").value),
    relief_m: Number($("#relief_m").value),
    north_south_drop_m: Number($("#north_south_drop_m").value),
    rainfall_mm_h: Number($("#rainfall_mm_h").value),
    rain_duration_min: Number($("#rain_duration_min").value),
    rain_center_x: Number($("#rain_center_x").value),
    rain_center_y: Number($("#rain_center_y").value),
    rain_width: Number($("#rain_width").value),
    rain_height: Number($("#rain_height").value),
    infiltration_mm_h: Number($("#infiltration_mm_h").value),
    manning_n: Number($("#manning_n").value),
    max_dt_s: 1.5,
    cfl: 0.35,
    open_outlet: $("#open_outlet").checked,
  };
}

function collectLiveControls() {
  const all = collectConfig();
  const result = {};
  $$('[data-live]').forEach((node) => { result[node.id] = all[node.id]; });
  return result;
}

function updateOutputs() {
  const units = {
    rainfall_mm_h: " mm/h", rain_duration_min: " min", infiltration_mm_h: " mm/h", relief_m: " m", north_south_drop_m: " m",
  };
  const percent = new Set(["rain_center_x", "rain_center_y", "rain_width", "rain_height"]);
  $$('output[data-for]').forEach((out) => {
    const input = document.getElementById(out.dataset.for);
    let value = Number(input.value);
    if (percent.has(input.id)) value = `${Math.round(value * 100)}%`;
    else if (input.id === "manning_n") value = value.toFixed(3);
    else value = `${value}${units[input.id] || ""}`;
    out.textContent = value;
  });
}

async function applyLiveControls() {
  try {
    const data = await api("/api/controls", { method: "PATCH", body: JSON.stringify(collectLiveControls()) });
    state.config = data.config;
    render();
  } catch (error) { toast(error.message); }
}

async function resetSimulation(message = "地形已重建，积水已清零") {
  state.running = false;
  updateRunButton();
  if (state.busy) return;
  state.busy = true;
  $("#regenerateBtn").disabled = true;
  try {
    const data = await api("/api/reset", { method: "POST", body: JSON.stringify(collectConfig()) });
    absorbFrame(data, true);
    toast(message);
  } catch (error) { toast(error.message); }
  finally { state.busy = false; $("#regenerateBtn").disabled = false; }
}

async function advance() {
  if (state.busy) return;
  state.busy = true;
  try {
    const iterations = Number($("#iterationsPerFrame").value);
    const data = await api("/api/step", { method: "POST", body: JSON.stringify({ iterations }) });
    absorbFrame(data, false);
  } catch (error) {
    state.running = false; updateRunButton(); toast(error.message);
  } finally { state.busy = false; }
}

async function runLoop() {
  if (!state.running) return;
  await advance();
  if (state.running) requestAnimationFrame(runLoop);
}

function updateRunButton() {
  const button = $("#runBtn");
  button.classList.toggle("running", state.running);
  button.innerHTML = state.running ? "<span>Ⅱ</span> 暂停" : "<span>▶</span> 开始";
}

function bindEvents() {
  $$('.section-toggle').forEach((button) => button.addEventListener("click", () => {
    const section = button.closest(".control-section");
    const collapsed = section.classList.toggle("collapsed");
    button.setAttribute("aria-expanded", String(!collapsed));
    button.lastElementChild.textContent = collapsed ? "+" : "−";
  }));

  $$('input[type="range"]').forEach((input) => input.addEventListener("input", () => {
    updateOutputs();
    if (input.dataset.live !== undefined) {
      clearTimeout(state.liveTimer);
      state.liveTimer = setTimeout(applyLiveControls, 120);
      if (state.config) {
        state.config[input.id] = Number(input.value);
        render();
      }
    }
  }));
  $$('[data-live]').filter((node) => node.type === "checkbox").forEach((input) => input.addEventListener("change", applyLiveControls));
  $("#regenerateBtn").addEventListener("click", () => resetSimulation());
  $("#clearBtn").addEventListener("click", () => resetSimulation("积水与时间已清零"));
  $("#stepBtn").addEventListener("click", advance);
  $("#exportBtn").addEventListener("click", () => {
    canvas.toBlob((blob) => {
      if (!blob) { toast("当前画面导出失败"); return; }
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      const seconds = Math.round($("#simClock").textContent.split(":").reduce((total, value) => total * 60 + Number(value), 0));
      link.download = `raincell_${seconds}s.png`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast("当前画面已导出为 PNG");
    }, "image/png");
  });
  $("#runBtn").addEventListener("click", () => {
    state.running = !state.running; updateRunButton();
    if (state.running) runLoop();
  });
  $$('[data-view]').forEach((button) => button.addEventListener("click", () => {
    $$('[data-view]').forEach((b) => b.classList.toggle("active", b === button));
    state.view = button.dataset.view; render();
  }));
  canvas.addEventListener("mousemove", (event) => {
    if (!state.depth) return;
    const rect = canvas.getBoundingClientRect();
    const x = Math.min(state.n - 1, Math.max(0, Math.floor((event.clientX - rect.left) / rect.width * state.n)));
    const y = Math.min(state.n - 1, Math.max(0, Math.floor((event.clientY - rect.top) / rect.height * state.n)));
    const i = y * state.n + x;
    const d = state.depth[i] / 65535 * state.depthScale;
    const s = state.speed[i] / 65535 * state.speedScale;
    $("#cellReadout").textContent = `单元 [${x}, ${y}] · 水深 ${d.toFixed(3)} m · 流速 ${s.toFixed(3)} m/s`;
  });
  canvas.addEventListener("mouseleave", () => { $("#cellReadout").textContent = "移动鼠标查看单元"; });
}

async function boot() {
  bindEvents(); updateOutputs();
  try {
    const [info, frame] = await Promise.all([api("/api/info"), api("/api/frame")]);
    $("#hardwareText").textContent = info.gpu_active ? `GPU · ${info.device_name}` : "CPU 回退模式";
    $("#hardwarePill").classList.add("ready");
    absorbFrame(frame, true);
  } catch (error) { toast(`启动失败：${error.message}`); }
}

boot();
