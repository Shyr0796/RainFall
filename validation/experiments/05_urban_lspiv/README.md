# 05 城市街区 LSPIV 验证

## 本轮结论

官方轻量数据已完整获取、校验和解包，观测审计已完成，并实际运行了一个 `Ref` 城市形态的 RainFall 局部惯性边界适配诊断基线。**这不是正式验证成功**：现有生产引擎缺少该实验要求的三入口、三定水位出口与显式建筑边界；此外 LSPIV 是表面速度，RainFall 输出深度平均速度。

## 数据与质量

- Zenodo 的 4 个目标文件均通过官方 MD5、文件大小和本地 SHA256 检查；未下载约 26 GB 原始视频。
- 解压得到 44 个文件，包含 19 个 HDF5、发布者结构说明和读取示例。
- Dataset 1 有 128 个实际存储测试组（包含 P2/P3 等重复测量）；Dataset 2 有 8 个城市形态与 `V/Vx/Vy`、水深和进出口流量。
- HDF5 共审计 4,704 个 dataset。逐字段结果见 `data/processed/hdf5_inventory.csv`。
- 论文给出的观测边界：水深仪器精度约 1 mm，水深时序标准差常见 0.5--2 mm，流量计精度 0.5%，率定曲线 $R^2>0.99$；除很小流量外总进出流量差通常不超过 2.5%。
- Dataset 2 本地复算的八构型质量平衡差为 -1.075% 到 +0.158%，均在上述 2.5% 范围内。
- LSPIV 60 s 与 90 s 平均速度在超过 90% 测点上的差小于 0.01 m/s；墙边约 1 cm 带为 NaN。HDF5 经 h5py 读取后速度数组轴序为 `(x,y)`。

完整来源与许可见 [SOURCE_AND_LICENSE.md](SOURCE_AND_LICENSE.md)，自动审计见 `results/observation_quality_audit.json`。

## 已执行的 Ref 基线

实验局部适配器复用了生产引擎相同的局部惯性通量、Manning 摩阻和单元出流限制，并新增：矩形网格、不可渗建筑掩膜、三个规定流量入口、三个定水位出口。它位于 `code/urban_adapter.py`，没有修改主程序。

- 数据：`Config_Ref.h5`；从处理后非零 LSPIV 区域提取几何并由 1 cm 降至 2 cm。
- 网格：135 x 99；`dx=0.02 m`；未校准 `n=0.010`。
- 运行：20.0004 s，6,269 步，CPU 用时约 3.52 s。
- 守恒：边界交换全部入账，相对入流质量误差约 `5.26e-15`。
- 仅作诊断的非等价比较：速度 RMSE `0.1203 m/s`，MAE `0.0923 m/s`；双方速度均大于 `0.02 m/s` 的格点上方向 MAE `27.29°`。
- 本轮用论文 Fig. 3c 复核并修正了早期烟雾测试的轴向解释：HDF `y=0` 是物理上方入口 A，`y=max` 是出口 1/2；左侧由上至下为 B、C。

这些误差不能写作论文验证指标，因为本轮直接比较了表面速度与深度平均速度，且尚未证明 20 s 已达稳态，也没有做参数、网格和边界标签复核。详细值和限制见 `results/ref_baseline_metrics.json`。

## 目录说明

- `data/raw/`：原始官方归档、Zenodo 元数据与局部解压工具包。
- `data/extracted/`：发布者 HDF5、结构说明和读取脚本。
- `data/processed/`：清单、字段盘点、Dataset 1/2 摘要、Ref 紧凑观测。
- `code/audit_dataset.py`：完整性、HDF5、质量和平衡审计及绘图。
- `code/urban_adapter.py`：实验局部边界/几何适配器。
- `code/run_ref_baseline.py`：Ref 基线运行与指标/图/场输出。
- `results/`：JSON、CSV、PNG 和压缩场。
- `logs/`：运行日志。

## 复现

从仓库根目录执行：

```bash
MPLCONFIGDIR=/tmp/mpl-lspiv python3 validation/experiments/05_urban_lspiv/code/audit_dataset.py
python3 validation/experiments/05_urban_lspiv/code/test_urban_adapter.py
MPLCONFIGDIR=/tmp/mpl-lspiv python3 validation/experiments/05_urban_lspiv/code/run_ref_baseline.py
```

依赖：Python 3.11+、NumPy、h5py、Matplotlib。

## 下一步成为正式验证所需工作

1. 将矩形掩膜、规定流量和定水位边界作为经过测试的能力正式合入生产引擎。
2. 跑到稳态并开展 `dx=0.01/0.02/0.04 m`、时间步和 Manning 敏感性分析。
3. 预注册表面速度到深度平均速度的观测算子，或只把方向作为主要速度场指标。
4. 三个构型校准一套参数、其余五个构型完全盲测；同时报告水深、出口分流、速度向量和方向误差。
