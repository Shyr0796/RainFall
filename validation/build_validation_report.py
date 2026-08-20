#!/usr/bin/env python3
"""Build the offline, evidence-bounded RainFall validation proposal."""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXPERIMENTS = ROOT / "experiments"
ADVANCED = ROOT / "advanced"

EXPERIMENT_SPECS = [
    (EXPERIMENTS / "01_numerical_verification", "A", "代码与数值可信性", "守恒、非负、CPU/GPU一致性、网格和时间步敏感性"),
    (EXPERIMENTS / "02_swashes", "B", "解析基准", "定常流、摩阻、降雨、干湿界面或波传播的解析预期"),
    (EXPERIMENTS / "03_uk_ea_benchmarks", "C", "复杂二维标准基准", "复杂地形、城市障碍、传播时间与空间水深"),
    (EXPERIMENTS / "04_infiltration_runoff", "D", "入渗—产流", "常量损失与状态型入渗模型的跨事件盲测"),
    (EXPERIMENTS / "05_urban_lspiv", "E", "城市水动力初始诊断", "水深、出口分流、二维表面速度和方向"),
    (EXPERIMENTS / "06_real_event_feasibility", "F", "Fourmile 可行性", "降雨、流量、水位、水痕、DEM与模型适用性"),
    (ADVANCED / "07_urban_flume_blind", "G", "城市水槽锁参盲测", "三构型率定、五构型盲测与网格敏感性"),
    (ADVANCED / "08_nyc_floodnet", "H", "NYC 街道积水", "真实城市传感器水深时序、局部低点与潮汐分层"),
    (ADVANCED / "09_usgs_muddy_creek", "I", "Muddy Creek 真实洪水", "完整降雨—径流—二维水动力档案与独立事件"),
    (ADVANCED / "10_urban_gis_core", "J", "城市 GIS 核心回归", "统一 CRS、建筑 DEM/固体体积、空间参数和守恒边界"),
    (ADVANCED / "11_building_dem_datum", "K", "建筑高度—DEM 基准", "官方高度 Shapefile、NAVD88/单位契约与纯地形道路策略"),
]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def file_count_and_bytes(folder: Path) -> tuple[int, int]:
    files = [path for path in folder.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def fmt_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


def infer_status(folder: Path) -> tuple[str, str]:
    json_paths = sorted((folder / "results").glob("*.json")) if (folder / "results").exists() else []
    if (folder / "status.json").exists():
        json_paths.insert(0, folder / "status.json")
    statuses: list[str] = []
    for path in json_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            for key in ("status", "validation_status", "run_status"):
                if key in payload:
                    statuses.append(str(payload[key]).lower())
    joined = " ".join(statuses)
    if "completed" in joined and "blocked" not in joined:
        return "completed", "已有实际运行结果"
    if "blocked" in joined or "partial" in joined:
        return "partial", "已完成数据/能力审计，仍有明确边界"
    result_files = list((folder / "results").glob("*")) if (folder / "results").exists() else []
    data_files = list((folder / "data" / "raw").glob("*")) if (folder / "data" / "raw").exists() else []
    if result_files:
        return "partial", "已有结果文件，待总审计"
    if data_files:
        return "partial", "数据已到位，尚无完整结果"
    if folder.exists():
        return "running", "目录已建立，正在执行"
    return "planned", "尚未建立"


def artifact_links(folder: Path, limit: int = 12) -> str:
    candidates = []
    for sub in ("README.md", "status.json", "SOURCE_AND_LICENSE.md", "results", "logs", "data/raw"):
        path = folder / sub
        if path.is_file():
            candidates.append(path)
        elif path.is_dir():
            candidates.extend(sorted(p for p in path.iterdir() if p.is_file()))
    items = []
    for path in candidates[:limit]:
        items.append(
            f'<a class="artifact" href="{html.escape(rel(path))}">{html.escape(path.name)}</a>'
        )
    return "".join(items) or '<span class="muted">暂无制品</span>'


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def key_results() -> str:
    numerical = load_json(EXPERIMENTS / "01_numerical_verification/results/metrics.json")
    swashes = load_json(EXPERIMENTS / "02_swashes/results/metrics.json")
    uk_ea = load_json(EXPERIMENTS / "03_uk_ea_benchmarks/results/test1_metrics.json")
    infiltration = load_json(EXPERIMENTS / "04_infiltration_runoff/results/summary.json")
    lspiv = load_json(EXPERIMENTS / "05_urban_lspiv/results/ref_baseline_metrics.json")
    event = load_json(EXPERIMENTS / "06_real_event_feasibility/results/event_data_audit.json")
    flume = load_json(ADVANCED / "07_urban_flume_blind/results/summary.json")
    floodnet = load_json(ADVANCED / "08_nyc_floodnet/results/qc_summary.json")
    muddy = load_json(ADVANCED / "09_usgs_muddy_creek/results/audit.json")
    urban_gis = load_json(ADVANCED / "10_urban_gis_core/results/metrics.json")
    building_datum = load_json(ADVANCED / "11_building_dem_datum/results/metrics.json")

    numerical_summary = numerical.get("summary", {})
    swashes_metrics = swashes.get("metrics", {})
    uk_points = uk_ea.get("point_metrics", {})
    uk_balance = uk_ea.get("water_balance", {})
    infiltration_rows = infiltration.get("metrics", [])
    infiltration_blind = {
        row.get("model"): row
        for row in infiltration_rows
        if row.get("split") == "blind_test"
    }
    constant_loss = infiltration_blind.get("constant_loss", {})
    soil_state = infiltration_blind.get("soil_state_decay", {})
    event_sites = event.get("sites", {})
    flume_blind = flume.get("blind_aggregate", {})
    floodnet_snapshot = floodnet.get("dataset_snapshot", {})
    floodnet_profile = floodnet.get("profile_qc", {})
    muddy_obs = muddy.get("observations", {})
    muddy_archive = muddy.get("full_model_archive", {})

    cards = [
        (
            "A · 数值验证",
            f"{numerical_summary.get('pass', '—')} PASS / {numerical_summary.get('fail', '—')} FAIL",
            f"另有 {numerical_summary.get('skip', '—')} 项跳过或仅报告；CUDA 一致性本轮未执行。",
            "ok",
        ),
        (
            "B · SWASHES 范围诊断",
            f"深度 RMSE {swashes_metrics.get('depth_rmse_active_window_m', float('nan')):.3f} m",
            f"湿润前缘误差 {swashes_metrics.get('front_position_error_m', float('nan')):.2f} m；局部惯性方程未通过完整 SWE Ritter 剖面对比。",
            "warn",
        ),
        (
            "C · UK EA Test 1",
            f"峰值误差 {1000 * max((p.get('peak_error_vs_expected_10_35_m', 0) for p in uk_points.values()), default=0):.2f} mm",
            f"最终水位最大误差 {1000 * max((p.get('final_error_vs_expected_10_25_m', 0) for p in uk_points.values()), default=0):.2f} mm；相对水量闭合 {uk_balance.get('relative_closure_error', float('nan')):.2e}。",
            "ok",
        ),
        (
            "D · 入渗—产流",
            f"盲测 NSE {soil_state.get('volume_nse_across_events', float('nan')):.3f}",
            f"28 个留站事件：状态模型体积 RMSE {soil_state.get('volume_rmse_mm', float('nan')):.2f} mm，常量损失率为 {constant_loss.get('volume_rmse_mm', float('nan')):.2f} mm；只验证产流子机理。",
            "warn",
        ),
        (
            "E · 城市 LSPIV 诊断",
            f"速度 RMSE {lspiv.get('speed_rmse_m_s_surface_vs_depth_average', float('nan')):.3f} m/s",
            f"方向 MAE {lspiv.get('direction_mae_deg_where_both_speed_gt_0p02', float('nan')):.2f}°；表面速度与深度平均速度非等价，只计诊断。",
            "warn",
        ),
        (
            "F · Fourmile 真实事件",
            f"{len(event_sites)} 个站点 × 480 条记录",
            "观测与水痕已整理；缺少河道几何和指定水位/流量边界，模拟对齐被明确阻塞。",
            "blocked",
        ),
        (
            "G · 城市水槽锁参盲测",
            f"4/5 构型执行；TV {flume_blind.get('outlet_partition_total_variation_mean', float('nan')):.3f}",
            f"水深 MAE {1000 * flume_blind.get('inlet_depth_mae_m_mean', float('nan')):.2f} mm，方向 MAE {flume_blind.get('direction_mae_deg_mean', float('nan')):.2f}°；多项阈值失败，不构成正式验证。",
            "blocked",
        ),
        (
            "H · NYC FloodNet 观测审计",
            f"{floodnet_snapshot.get('event_rows', '—')} 事件 / {floodnet_snapshot.get('unique_event_sensors', '—')} 传感器",
            f"共 {floodnet_profile.get('total_profile_points', '—')} 个水深点；候选事件已筛选，但降雨、潮位、DEM 与排水边界尚未组装运行。",
            "warn",
        ),
        (
            "I · USGS Muddy Creek",
            f"{muddy_obs.get('pressure_transducer_rows', '—')} 水位记录",
            f"完整模型档案 {muddy_archive.get('files', '—')} 个文件，DEM/糙率/降雨存储/二维几何齐全；格式与边界适配尚未完成。",
            "warn",
        ),
        (
            "J · 城市 GIS 核心回归",
            f"建筑面积误差 {urban_gis.get('building_area_error_m2', float('nan')):.2f} m²",
            f"建筑内最大水深 {urban_gis.get('max_building_depth_m', float('nan')):.1e} m；水量闭合 {urban_gis.get('with_buildings', {}).get('relative_mass_error', float('nan')):.2e}。这是合成 GIS 代码验证，不是现实事件验证。",
            "ok",
        ),
        (
            "K · 建筑高度—DEM 基准",
            f"{building_datum.get('official_building_features', '—')} 个官方建筑",
            f"单位、相对高度公式与 solid-mask 门控通过；建筑 GROUNDELEV 对 NOAA DEM 的绝对误差 p95 为 {building_datum.get('ground_cross_check', {}).get('p95_absolute_error_m', float('nan')):.2f} m，二者不可互换。",
            "warn",
        ),
    ]
    return "".join(
        f'<article class="result-card {tone}"><small>{html.escape(label)}</small>'
        f'<strong>{html.escape(value)}</strong><p>{html.escape(note)}</p></article>'
        for label, value, note, tone in cards
    )


def image_gallery() -> str:
    images = []
    for result_dir in sorted(list(EXPERIMENTS.glob("*/results")) + list(ADVANCED.glob("*/results"))):
        images.extend(path for path in result_dir.rglob("*") if path.is_file())
    images = sorted(path for path in images if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"})
    if not images:
        return '<div class="empty">结果图将在实验完成后自动出现在这里。</div>'
    cards = []
    for path in images[:24]:
        experiment = path.parent.parent.name
        cards.append(
            f'<figure><a href="{html.escape(rel(path))}"><img src="{html.escape(rel(path))}" '
            f'alt="{html.escape(path.stem)}"></a><figcaption>{html.escape(experiment)} · '
            f'{html.escape(path.stem)}</figcaption></figure>'
        )
    return "".join(cards)


def build_rows() -> tuple[str, dict[str, int]]:
    rows = []
    counts = {key: 0 for key in ("completed", "partial", "running", "planned")}
    for folder, code, title, purpose in EXPERIMENT_SPECS:
        status, status_text = infer_status(folder)
        counts[status] += 1
        count, size = file_count_and_bytes(folder) if folder.exists() else (0, 0)
        rows.append(
            f"""
            <tr>
              <td><span class="exp-code">{code}</span></td>
              <td><strong>{html.escape(title)}</strong><small>{html.escape(purpose)}</small></td>
              <td><span class="status {status}">{status}</span><small>{html.escape(status_text)}</small></td>
              <td>{count} files<small>{fmt_bytes(size)}</small></td>
              <td><div class="artifacts">{artifact_links(folder)}</div></td>
            </tr>"""
        )
    return "".join(rows), counts


def main() -> None:
    rows, counts = build_rows()
    result_cards = key_results()
    updated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    report = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RainFall Physics Validation Proposal</title>
  <style>
    :root{{--ink:#10212a;--muted:#60717a;--paper:#f5f7f4;--card:#fff;--line:#dce4df;--teal:#0b7c78;--blue:#135ba1;--amber:#b87503;--red:#a63832;--green:#17714c}}
    *{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,"Noto Sans SC","Microsoft YaHei",system-ui,sans-serif;line-height:1.65}}
    a{{color:var(--blue)}} .hero{{background:linear-gradient(125deg,#0b2731 0%,#0d5657 62%,#0b7770 100%);color:white;padding:74px max(24px,calc((100vw - 1180px)/2)) 56px}}
    .kicker{{font:700 12px/1.2 ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase;color:#8ee1d7}} h1{{font-size:clamp(34px,6vw,70px);line-height:1.02;max-width:900px;margin:14px 0 22px;letter-spacing:-.035em}}
    .lead{{max-width:860px;font-size:18px;color:#d8eeeb}} .meta{{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}} .pill{{padding:6px 10px;border:1px solid #ffffff45;border-radius:99px;font-size:13px;background:#ffffff12}}
    main{{max-width:1180px;margin:auto;padding:42px 24px 90px}} nav{{display:flex;gap:10px;flex-wrap:wrap;margin:-63px 0 40px;padding:14px;background:#fff;border-radius:14px;box-shadow:0 12px 35px #10212a22;position:relative}} nav a{{text-decoration:none;color:var(--ink);font-size:13px;padding:7px 10px;border-radius:8px}} nav a:hover{{background:#eef4f1}}
    section{{margin:50px 0}} h2{{font-size:30px;line-height:1.2;letter-spacing:-.02em;margin:0 0 16px}} h3{{margin:0 0 9px;font-size:18px}} p{{max-width:900px}} .callout{{border-left:5px solid var(--teal);padding:17px 20px;background:#e7f3ef;border-radius:0 12px 12px 0}}
    .grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}} .card p{{font-size:14px;color:var(--muted);margin-bottom:0}} .number{{font:700 34px/1 ui-monospace,monospace;color:var(--teal)}}
    .result-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}} .result-card{{background:#fff;border:1px solid var(--line);border-left:5px solid #8a9992;border-radius:12px;padding:16px}} .result-card small{{display:block;color:var(--muted);font-weight:700}} .result-card strong{{display:block;font:750 21px/1.25 ui-monospace,monospace;margin:8px 0}} .result-card p{{font-size:13px;color:var(--muted);margin:0}} .result-card.ok{{border-left-color:var(--green)}} .result-card.warn{{border-left-color:var(--amber)}} .result-card.blocked{{border-left-color:var(--red)}}
    table{{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:14px}} th{{background:#eaf0ed;text-align:left;padding:11px 13px}} td{{padding:13px;border-top:1px solid var(--line);vertical-align:top}} td small{{display:block;color:var(--muted);margin-top:3px}} .exp-code{{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:50%;background:#dcefea;color:#075f5b;font-weight:800}}
    .status{{display:inline-block;padding:3px 8px;border-radius:99px;font:700 11px/1.4 ui-monospace,monospace;text-transform:uppercase}} .status.completed{{background:#dcefe4;color:var(--green)}} .status.partial{{background:#fff0ce;color:#815000}} .status.running{{background:#dcebf7;color:var(--blue)}} .status.planned{{background:#e9eceb;color:#66716c}}
    .artifacts{{display:flex;gap:5px;flex-wrap:wrap;max-width:340px}} .artifact{{font-size:11px;text-decoration:none;border:1px solid var(--line);border-radius:6px;padding:3px 6px;background:#fafcfb}} .artifact:hover{{border-color:var(--teal)}} .muted{{color:var(--muted)}}
    .chain{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}} .chain div{{background:#fff;border:1px solid var(--line);border-top:4px solid var(--teal);padding:14px;border-radius:10px;font-size:13px}} .chain b{{display:block;margin-bottom:5px}}
    .metric-table td:nth-child(1){{font-weight:700}} code{{background:#e8efec;border-radius:5px;padding:2px 5px}} ul{{padding-left:20px}} li{{margin:5px 0}} .gallery{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}} figure{{margin:0;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}} figure img{{width:100%;height:220px;object-fit:contain;background:#f8faf8;display:block}} figcaption{{padding:9px 12px;color:var(--muted);font-size:12px}} .empty{{padding:30px;background:#fff;border:1px dashed #aab9b2;border-radius:12px;color:var(--muted)}}
    .sources a{{display:block;margin:7px 0}} footer{{margin-top:70px;padding-top:24px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}}
    @media(max-width:800px){{.grid,.gallery,.result-grid{{grid-template-columns:1fr}} .chain{{grid-template-columns:1fr 1fr}} table{{display:block;overflow-x:auto}} .hero{{padding-top:48px}} nav{{margin-top:-54px}}}}
  </style>
</head>
<body>
<header class="hero">
  <div class="kicker">RainFall · Evidence-bounded validation</div>
  <h1>降雨—产流—水动力<br>分层实验验证提案</h1>
  <p class="lead">真实 DEM 是必要输入，但可信性来自完整证据链。本提案把代码验证、解析基准、入渗实验、城市水动力实验和真实事件盲测分开，避免用一张“看起来相似”的淹没图替代物理验证。</p>
  <div class="meta"><span class="pill">更新 {updated}</span><span class="pill">自动汇总本地实际制品</span><span class="pill">未运行内容明确标记</span></div>
</header>
<main>
<nav><a href="#decision">核心判断</a><a href="#design">验证设计</a><a href="#advanced">高级实验</a><a href="#status">执行状态</a><a href="#key-results">关键结果</a><a href="#metrics">指标</a><a href="#calibration">校准与盲测</a><a href="#data-needs">数据需求</a><a href="#results">结果图</a><a href="#sources">来源</a></nav>

<section id="decision">
  <div class="kicker">01 · Scientific decision</div><h2>验证对象不是“模型整体”，而是可被证伪的机理链</h2>
  <div class="callout"><strong>论文主线：</strong>解析基准证明方程实现正确；人工降雨实验验证入渗—产流；城市水槽验证水深、速度与方向；独立真实事件验证淹没范围、流量和时序。任一层失败，都不能由后续文本或视觉效果替代。</div>
  <div class="grid" style="margin-top:16px">
    <article class="card"><h3>当前可验证</h3><p>质量闭合、非负水深、局部惯性通量、空间 Manning/降雨/入渗、建筑固体掩膜、命名流量/水位边界和排水汇记账。</p></article>
    <article class="card"><h3>当前只是有效参数</h3><p>常量入渗 <code>f</code> 表示等效损失率，尚未表达随含水状态变化的真实土壤入渗容量。</p></article>
    <article class="card"><h3>当前不能声称</h3><p>真实城市 30 m 速度精度、河道洪水适用性、管网回涌、工程设计或生命安全阈值有效性。</p></article>
  </div>
</section>

<section id="design">
  <div class="kicker">02 · Validation ladder</div><h2>五级证据链</h2>
  <div class="chain"><div><b>1 代码验证</b>实现是否等于公式</div><div><b>2 解验证</b>网格与时间误差</div><div><b>3 校准</b>参数能否识别</div><div><b>4 独立验证</b>未见事件能否预测</div><div><b>5 业务有效性</b>误差是否改变判断</div></div>
  <p>高保真有限体积模型只能用于模型互比，不能代替实验或现场观测。卫星洪水范围也不能单独验证速度、方向或入渗。</p>
</section>

<section id="advanced">
  <div class="kicker">03 · Journal-grade extension</div><h2>三条相互独立的高级证据链</h2>
  <div class="grid">
    <article class="card"><h3>方法一：受控水槽锁参盲测</h3><p>用 CO/CE/Ref 选择一套全局参数，再对 Px5/Py5/BU/BS/BD 锁参预测。水深、出口分流、表面速度与方向必须同时过门；本轮 4/5 构型已执行，但精度与稳态门槛未通过。</p></article>
    <article class="card"><h3>方法二：真实传感器观测算子</h3><p>NYC FloodNet 同时保留传感器正下方水深和局部低点修正水深；潮汐与非潮汐站点分层。官方事件序列已完整审计，下一步组装同步降雨、潮位和城市地形。</p></article>
    <article class="card"><h3>方法三：独立降雨驱动洪水</h3><p>USGS Muddy Creek 提供真实事件、DEM、糙率、HEC-HMS/HEC-RAS 工程、7 站水位与高水痕。数据已齐全，当前工作转为 DSS、空间基准和河道边界适配。</p></article>
  </div>
  <p><strong>期刊级最低条件：</strong>参数和事件划分预注册；至少一个严格未见事件；网格/时间步/输入不确定性；失败案例完整保留；代码、原始数据散列、处理脚本、逐站结果与置信区间可复现。</p>
</section>

<section id="status">
  <div class="kicker">04 · Execution status</div><h2>实验与本地制品</h2>
  <div class="grid" style="margin-bottom:16px"><div class="card"><span class="number">{counts['completed']}</span><p>completed</p></div><div class="card"><span class="number">{counts['partial']}</span><p>partial / bounded</p></div><div class="card"><span class="number">{counts['running'] + counts['planned']}</span><p>running or planned</p></div></div>
  <table><thead><tr><th>ID</th><th>实验</th><th>状态</th><th>规模</th><th>证据文件</th></tr></thead><tbody>{rows}</tbody></table>
</section>

<section id="key-results">
  <div class="kicker">05 · Evidence snapshot</div><h2>实际结果与边界</h2>
  <div class="result-grid">{result_cards}</div>
  <p class="muted">绿色表示在所列标准内通过；黄色表示已实际运行但只构成方程范围或观测可比性诊断；红色表示真实数据已获取，但必要模型能力缺失。</p>
</section>

<section id="metrics">
  <div class="kicker">06 · Metrics</div><h2>必须联合报告的指标</h2>
  <table class="metric-table"><thead><tr><th>对象</th><th>核心指标</th><th>不能遗漏</th></tr></thead><tbody>
    <tr><td>入渗与产流</td><td>累计入渗、径流体积偏差、产流开始、峰值/峰现、NSE、KGE</td><td>初始土壤湿度与水量闭合</td></tr>
    <tr><td>水深</td><td>MAE、RMSE、峰值偏差、首次超阈与退水时间</td><td>点位过程，而非只看最大范围</td></tr>
    <tr><td>速度</td><td>RMSE(u)、RMSE(v)、向量 RMSE、速度模长 MAE</td><td>表面速度与深度平均速度的观测算子</td></tr>
    <tr><td>方向</td><td>圆周误差中位数、≤15°/30°/45°比例、反向流错误</td><td>预注册低水深/低速度共同掩膜</td></tr>
    <tr><td>范围与业务</td><td>CSI/IoU、POD、FAR、到达时间、高危险召回率</td><td>高危险漏判面积与持续时间</td></tr>
  </tbody></table>
</section>

<section id="calibration">
  <div class="kicker">07 · Experimental protocol</div><h2>参数冻结与盲测</h2>
  <div class="grid"><article class="card"><h3>入渗实验</h3><p>按完整场地/实验划分训练与盲测；比较常量损失和状态型模型，不随机拆分钟样本。</p></article><article class="card"><h3>城市水槽</h3><p>用少数布局校准统一糙率，在未见布局上冻结参数；同时比较水深、出口分流、u/v 与方向。</p></article><article class="card"><h3>真实事件</h3><p>至少 2 场校准、2 场独立验证、1 场极端压力测试；失败事件保留。</p></article></div>
  <p><strong>可辨识性约束：</strong>入渗率和 Manning 糙率可能共同改变局部最大水深。必须联合使用总径流体积、水深过程、峰值时间、断面流量和速度，避免“参数错误但结果碰巧吻合”。</p>
</section>

<section id="data-needs">
  <div class="kicker">08 · Data availability</div><h2>哪些数据我能获取，哪些需要用户提供</h2>
  <table><thead><tr><th>数据</th><th>当前结论</th><th>用途</th></tr></thead><tbody>
    <tr><td>Li 城市水槽 HDF5/LSPIV</td><td><span class="status completed">已获取</span></td><td>微观水深、分流、速度、方向与几何迁移盲测</td></tr>
    <tr><td>NYC FloodNet 事件与部署元数据</td><td><span class="status completed">已获取</span></td><td>真实街道水深时序、峰值、持续时间和潮汐分层</td></tr>
    <tr><td>USGS Muddy Creek 完整模型档案</td><td><span class="status completed">已获取</span></td><td>真实降雨驱动事件、DEM、糙率、连续水位、高水痕</td></tr>
    <tr><td>目标城市私有排水管网、泵闸与运维记录</td><td><span class="status partial">通常需用户</span></td><td>目标城市最终应用、管网回涌和边界真实性</td></tr>
    <tr><td>目标城市高精度 DEM 与同步积水观测</td><td><span class="status partial">公开优先；不足时需用户</span></td><td>把公开基准迁移到用户真正关心的城市</td></tr>
  </tbody></table>
  <p>用户数据清单和格式要求见 <a href="advanced/USER_DATA_REQUEST.md">USER_DATA_REQUEST.md</a>。公开数据足以推进方法论文和适配器开发；若论文要声称“适用于某一目标城市”，仍应补充该城市的本地边界、排水和独立观测。</p>
</section>

<section id="results"><div class="kicker">09 · Actual outputs</div><h2>本轮结果图</h2><div class="gallery">{image_gallery()}</div></section>

<section id="claims">
  <div class="kicker">10 · Claim gate</div><h2>论文结论的允许边界</h2>
  <ul><li>通过代码与解析基准：可称“数值实现通过所列基准”，不可称“现实预测准确”。</li><li>通过城市实验盲测：可称“在所列实验尺度和边界下复现水深/速度/方向”，必须报告表面—平均速度差异。</li><li>通过独立真实事件：才可在相应区域、分辨率、降雨类型和观测误差范围内讨论现实可信性。</li><li>真实事件数据已获取但物理过程不兼容时，结论应为“尚不适用”，不能强行输出评分。</li></ul>
</section>

<section id="sources" class="sources"><div class="kicker">11 · Primary sources</div><h2>数据与规范</h2>
  <a href="https://zenodo.org/records/5254164">Li et al. 城市洪水实验与 LSPIV 数据（Zenodo）</a>
  <a href="https://www.nature.com/articles/s41597-022-01282-w">Laboratory modelling of urban flooding（Scientific Data）</a>
  <a href="https://essd.copernicus.org/articles/12/245/2020/">Ries et al. 132组大型人工降雨实验（ESSD）</a>
  <a href="https://arxiv.org/abs/1110.0288">SWASHES 浅水方程解析解</a>
  <a href="https://www.gov.uk/flood-and-coastal-erosion-risk-management-research-reports/2d-benchmarking-evaluating-the-latest-generation-of-the-hydraulic-models-for-fcrm">UK Environment Agency 二维水动力基准</a>
  <a href="https://www.usgs.gov/publications/flood-june-30-july-1-2018-fourmile-creek-basin-near-ankeny-iowa">USGS Fourmile Creek 2018 真实事件</a>
  <a href="https://data.cityofnewyork.us/d/aq7i-eu5q">NYC Open Data · FloodNet 街道积水事件</a>
  <a href="https://data.cityofnewyork.us/d/kb2e-tjy3">NYC Open Data · FloodNet 传感器部署元数据</a>
  <a href="https://www.floodnet.nyc/methodology">FloodNet NYC 方法与观测限制</a>
  <a href="https://doi.org/10.5066/P969ZOLB">USGS Muddy Creek 完整数据与模型档案</a>
  <a href="https://pubs.usgs.gov/publication/sir20225084">USGS Muddy Creek Scientific Investigations Report</a>
  <a href="https://github.com/CityOfNewYork/nyc-geo-metadata/blob/main/Metadata/Metadata_BuildingFootprints.md">NYC Building Footprints 官方字段与基准元数据</a>
  <a href="https://www.fisheries.noaa.gov/inport/item/64732">NOAA 2017 NYC 裸地 DEM 元数据</a>
  <a href="https://onlinelibrary.wiley.com/doi/full/10.1111/jfr3.12950">Iliadis et al. 建筑在城市水动力模型中的表示</a>
</section>

<footer>本报告由 <code>validation/build_validation_report.py</code> 从本地实验目录自动生成。状态来自实际文件和结构化结果；proposal、部分完成和阻塞项均不计作验证成功。</footer>
</main>
</body></html>"""
    (ROOT / "validation.html").write_text(report, encoding="utf-8")
    print(ROOT / "validation.html")


if __name__ == "__main__":
    main()
