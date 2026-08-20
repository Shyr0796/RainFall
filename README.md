# RainFall：暴雨洪涝仿真模拟

> **寻求合作 · Seeking Research Collaboration**  
> RainFall 欢迎高校、科研机构、公共安全与环境保护组织围绕洪涝水动力、GPU 计算、城市 GIS、真实事件验证和风险决策开展**非商业科研合作**。请通过 GitHub Issue，以 `[Collaboration]` 开头说明团队、研究问题、可提供的数据/基准以及预期成果。  
> We welcome **non-commercial research collaboration** on flood hydrodynamics, GPU computing, urban GIS, real-event validation, and risk-informed decision support.
>
> 合作联系 · Collaboration contact：[songchun2307@gmail.com](mailto:songchun2307@gmail.com) · [个人主页 / Personal website](https://chun-song.com)

> **不可商用 · Non-commercial use only**  
> 本项目采用 [PolyForm Noncommercial License 1.0.0](LICENSE)。未经版权所有者另行书面授权，不得将本项目或其衍生作品用于商业产品、收费服务、商业咨询、商业部署或其他预期商业应用。产业合作或商业许可请先发起 `[Commercial Licensing]` Issue 洽谈。  
> Licensed under the PolyForm Noncommercial License 1.0.0. Commercial use requires a separate written license.

公开仓库：

- EBL 实验室主仓：[Emergent-Balance-Lab/RainFall](https://github.com/Emergent-Balance-Lab/RainFall)
- 个人同步仓：[Shyr0796/RainFall](https://github.com/Shyr0796/RainFall)

合作流程与优先方向见 [CONTRIBUTING.md](CONTRIBUTING.md)。

> 当前阶段：可运行 GPU 交互原型 + 城市 GIS 核心 + 分层验证（2026-08-11）  
> 状态说明：已实现 GeoTIFF DEM 与 Shapefile/GPKG/GeoJSON 建筑的 CRS 对齐、建筑高程烧录和固体占据掩膜，以及空间降雨/入渗/糙率、命名流量/水位边界和简化排水汇；这些能力已通过合成 GIS 与守恒回归，但尚未构成目标城市真实事件验证。

## 立即运行 RainCell GPU

```bash
cd /home/shyr/workspace/RainFall
./start.sh
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。页面可调整降雨区域、雨强、入渗、Manning 糙率、网格和山区 DEM 参数，并实时显示水深、流速、方向、域内水量和质量闭合误差。

完整实现、公式、验证结果、操作步骤与限制见：

- [RainCell GPU 技术与使用报告](docs/RainCell_GPU_技术与使用报告.md)

本原型是教学与算法筛查工具，不可直接用于工程设计或预警发布。

### 城市 DEM 与建筑 Shapefile

```bash
uv sync --extra dev --extra gis
uv run --extra gis python scripts/prepare_urban_domain.py \
  --dem path/to/dem.tif --buildings path/to/buildings.shp \
  --height-field height_m --target-crs EPSG:32650 --resolution-m 2 \
  --dem-vertical-datum NAVD88 --building-vertical-datum NAVD88 \
  --strict-vertical --missing-height-policy error \
  --output data/processed/city_domain.npz
```

预处理会保留 CRS、仿射变换、输入文件散列、建筑数量/面积/高度与垂直单位审计。若 DEM 或建筑高度不是米，必须分别设置 `--vertical-scale-to-m` 和 `--building-height-scale-to-m`，不能共用隐式单位。建筑既写入显示用 `surface_dem_m`，又作为求解器的不可储水固体掩膜。网页后端可调用 `POST /api/domain/load-prepared` 加载 `data/processed/` 下的域文件；可复现实验与结果见 [城市 GIS 核心回归](validation/advanced/10_urban_gis_core/README.md)和[建筑高度—DEM 基准耦合](validation/advanced/11_building_dem_datum/README.md)。

## 1. 项目定位

RainFall 面向大范围强降雨影响下的城市重点区域，构建“区域降雨输入—水文连通分区—重点片区精细水动力计算—灾害风险评估—LLM 辅助决策—分级预警推送”的闭环系统。系统以大范围降雨和完整汇水关系作为统一背景，对高风险片区输出约 30 m 网格的水深、流速和主导方向；30 m 是第一阶段计算分辨率，不预设为已经达到的现实精度。

核心原则：

1. 大范围降雨是统一外部强迫；片区按照地表与排水系统的水文连通关系划分，而不是按照行政边界、规则方格或降雨图斑任意切割。
2. 重点关注区不等于完整计算域。每个关注区必须纳入其上游贡献区、必要缓冲区和可能跨越地表分水岭的管网连接。
3. 分区计算必须交换随时间变化的边界水位/通量和管网流量，保持全域水量守恒，不把片区当作互不影响的独立模型。
4. 元胞自动机（Cellular Automata, CA）或经验证的混合数值引擎负责水深、二维通量、速度、方向、淹没范围和到达时间等可验证计算。
5. 确定性规则负责风险分级、硬阈值、权限和消息校验。
6. 大语言模型（Large Language Model, LLM）只负责工具编排、证据解释、方案草拟和受约束的消息生成，不直接臆测水深或替代正式预警发布人。
7. 所有推送必须能追溯到输入版本、分区与边界版本、仿真运行、风险规则和审批记录。

## 2. 第一版建议范围

先聚焦“城市短历时强降雨导致的地表积水（urban pluvial flooding）”：

- 降雨输入域：覆盖完整强降雨影响区及其时空演变，可显著大于单个重点片区。
- 结果关注区：第一阶段以约 $1\ \mathrm{km^2}$ 的城市重点片区为基本输出对象。
- 水动力计算域：由关注区的地表上游贡献区、洼地溢流关系、河渠边界和 1D 排水网络共同确定；不直接把 $1\ \mathrm{km^2}$ 矩形边界当作封闭边界。
- 空间分辨率：MVP 以现有 30 m DEM 对齐计算；道路、下穿通道和关键设施在获得更高质量数据后评估 5–10 m 局部加密或亚网格表达。
- 预测时效：未来 0–3 小时滚动预测。
- 更新方式：建议每 5 分钟触发一次；具体周期由数据源和计算预算决定。
- 主输出：逐网格水深、$u/v$ 速度分量、速度模长、有效湿单元主导方向、淹没概率、到达时间、持续时间、道路/建筑/人口影响和处置建议。
- 主求解器：显式保存二维通量/速度并考虑惯性的动态波 CA（优先评估 SWFCA）；可选耦合 EPA SWMM 表示 1D 排水管网。WCA2D 等简化 CA 仅作为速度要求较低的对照或筛查模型。
- 计算策略：区域级产流与风险筛查负责发现并激活高风险水文连通片区；精细求解器负责重点片区，片区之间通过守恒边界通量和管网交换耦合。
- 暂不纳入第一版：河道洪水、风暴潮、溃坝、地下空间精细三维水动力和完全自主公开发布。

上述范围是供审阅的建议，不代表已经锁定。

## 3. 文档导航

- [文献调研](docs/01_文献调研.md)：技术谱系、代表文献、可复用结论和研究空白。
- [方法框架](docs/02_方法框架.md)：数据、CA 引擎、风险评估、LLM 决策、实时推送、验证与路线图。
- [审阅与待确认](docs/03_审阅与待确认.md)：需要你反馈的关键选择，以及建议的下一步。
- [水深、流速与方向验证方案](docs/04_水深流速方向验证方案.md)：核心灾害要素的分层验证、指标和通过门槛。
- [来源登记](reference/来源登记.md)：可点击的论文、规范和官方资料清单。

## 4. 长期目录规划与当前落地

```text
RainFall/
├─ README.md
├─ docs/
│  ├─ 01_文献调研.md
│  ├─ 02_方法框架.md
│  ├─ 03_审阅与待确认.md
│  └─ 04_水深流速方向验证方案.md
├─ reference/
│  └─ 来源登记.md
├─ configs/                  # 场景、模型、风险规则、推送渠道配置
├─ data/
│  ├─ raw/                  # 原始 DEM、降雨、管网、暴露数据
│  ├─ processed/            # 对齐后的栅格/矢量数据
│  └─ fixtures/             # 小型可公开测试样例
├─ schemas/                 # ScenarioSpec、EvidenceBundle 等 JSON Schema
├─ src/
│  ├─ ingestion/            # 实时数据接入与质量控制
│  ├─ ca_engine/            # CPU/GPU CA 求解器
│  ├─ drainage/             # SWMM 或简化排水交换
│  ├─ assimilation/         # 状态更新与集合预报
│  ├─ risk/                 # 确定性风险和影响计算
│  ├─ agents/               # LLM 工具编排与审查
│  ├─ alerting/             # CAP 消息、推送与回执
│  └─ api/                  # 服务接口
├─ tests/
├─ benchmarks/
└─ outputs/                 # 带版本和运行 ID 的结果，不提交敏感数据
```

本轮已经落地 `src/ca_engine` 对应的 GPU/CPU 求解能力、`src/api` 对应的本地接口、网页可视化、测试与基准；其余数据接入、管网、风险、智能体和推送模块仍是长期规划，未创建无功能空壳。
