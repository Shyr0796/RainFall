# 04 入渗—产流验证：132 组真实人工降雨实验

## 结论先行

本实验成功下载并解析 Freiburg 官方 DOI `10.6094/UNIFR/151460` 数据，使用作者标记的有效子区以及完整的平均雨量/地表径流字段，从仓库中的 138 条事件记录得到论文所述的 **132 个可用实验**。23 个站点中，18 个站点（104 个事件）只用于参数校准，5 个完整站点（28 个事件）只用于盲测；没有随机拆分分钟样本，也没有让同一站点同时进入校准和测试。

最简单的“常量有效损失率 + 线性汇流”基线在独立站点盲测上的体积指标为：MAE **20.03 mm**、RMSE **27.66 mm**、总量偏差 **−1.21%**、跨事件 NSE **0.487**、KGE **0.426**。加入初始浅层土壤含水率与孔隙度亏缺的状态衰减模型后，盲测体积 RMSE 降至 **19.63 mm**，跨事件 NSE 升至 **0.742**；但事件流量过程的中位 NSE 仍只有 **0.294**，说明它仍只是低阶诊断模型。

**边界：这只验证 RainFall 中“有效降雨损失/产流响应”这一子机理，不验证二维水深、流速、流向、Manning 摩阻或空间汇流。** 常量损失率可作为 RainFall 当前常量入渗参数的外部基线，但不能据此宣称完整求解器已通过真实物理验证。

## 数据审计

- 原始 ZIP：`data/raw/UNIFR_151460.zip`，159 MiB；SHA-256 见 `source_manifest.csv`。
- 官方 1 分钟数据含降雨、浅层土壤含水率、地表/地下径流及气象变量。
- 132/132 个有效事件均有“实验时长 + 10 分钟退水段”的完整分钟数；无负降雨、无负地表径流；所有事件至少有一项初始浅层土壤含水率。
- 站点 16 缺失 10 cm 总孔隙度，因此其 6 个校准事件用同土地利用类型的站点中位数填补；盲测站点没有该填补。
- 数据文件注释把时序 `Q_OF_mean_selected` 称为 cumulative，但逐分钟值会随退水下降；对每个事件求和与事件总量表相符（最大差 0.005 mm）。因此代码将其按 **1 分钟区间径流深** 解释，再累加成累计径流。这一解释有原始事件总量交叉核验支持。

## 试验设计

固定留出完整站点 `5, 10, 15, 20, 23`，同时覆盖 pasture 与 arable land。参数分别按土地利用类型拟合，只使用其余 18 个站点。

1. `constant_loss`：每分钟有效降雨为 `max(P - f, 0)`，拟合常量损失率 `f` 和线性水库响应时间 `tau`。
2. `soil_state_decay`：入渗容量为 `fc + alpha * (porosity - initial_SM) * exp(-k*t)`，再使用相同的质量守恒线性水库。它是有观测初始状态约束的简化 Horton 型对照，不是严格 Green–Ampt。
3. 校准目标是各事件累计径流误差按该事件总雨量归一化后的均方误差平均，避免长历时或大径流事件完全支配拟合。
4. 报告事件体积、峰值与峰现、产流开始、流量过程 NSE/KGE、累计过程 NSE，以及零径流识别。盲测集恰好没有 `<0.1 mm` 的观测零径流事件，因此其零径流准确率不能用于评价零事件检出；校准集有 6 个，仅作诊断。

## 关键文件

- `results/aggregate_metrics.csv`：校准与盲测汇总指标。
- `results/event_metrics.csv`：每事件、每模型指标。
- `results/time_series_predictions.csv.gz`：逐分钟观测与预测。
- `results/fitted_parameters.csv`：只由校准站点拟合的参数。
- `results/data_qc_summary.json`、`results/data_qc_events.csv`：数据质量审计。
- `results/figures/blind_test_summary.png`、`blind_hydrograph_examples.png`：盲测图。
- `status.json`：机器可读状态与关键结果；`source_manifest.csv`、`artifact_manifest.csv`：哈希清单。
- `SOURCE.md`：来源、引用与许可边界。

## 复现

在项目根目录运行：

```bash
MPLCONFIGDIR=/tmp/rainfall-mpl bash validation/experiments/04_infiltration_runoff/run.sh
```

需要 Python 3.11+、NumPy、pandas、SciPy 和 Matplotlib。完整日志写入 `logs/run.log`。优化器使用固定随机种子 `20260811`。

## 如何进入 RainFall 论文

建议把常量损失率作为“当前模型的等效参数基线”，把状态模型的盲测改善作为升级状态型入渗的证据。论文不能只引用总量偏差接近零：常量模型的单事件 MAE/RMSE 和过程 NSE 显示明显站点异质性与误差抵消。下一步应将同一雨量、初始含水状态和土壤属性输入 RainFall/Green–Ampt 模块，保持本目录的完整留站划分不变，再比较空间模型的出口径流。
