# 07 城市水槽多构型率定—盲测

## 设计

使用 Li 等人的官方城市街区实验。`CO/CE/Ref` 只用于选择一套全局 Manning 参数和一个“深度平均速度→LSPIV 表面速度”的观测算子；随后锁定参数，对 `Px5/Py5/BU/BS/BD` 做盲测。比较入口水深、三个出口分流、表面速度大小与方向，并运行 1/2/4 cm 网格敏感性。

边界位置已依据论文 Fig. 3c 明确：HDF 数组 `y=0` 是物理上方入口 A，数组 `y=max` 是出口 1/2；左边从上到下为 B、C，右边为出口 3。论文 Fig. 3/4 的官方图片及 SHA256 保存在 `data/`。

## 诚实性边界

当前实验仍使用 `experiments/05_urban_lspiv/code/urban_adapter.py`，并非生产 RainFall API。建筑/流体掩膜由非零 LSPIV 单元推导；若某开口观测为零速，掩膜可能误删真实开口。脚本因此先执行六开口几何门控，不通过就停止该构型，不手工补造流场。

此外，入口水深只在计算开口取样，不是超声传感器的精确坐标；LSPIV 测得表面速度，模拟输出深度平均速度。它们都必须作为观测算子不确定性报告。

## 复现

```bash
MPLCONFIGDIR=/tmp/mpl-flume python3 validation/advanced/07_urban_flume_blind/code/run_blind_protocol.py
```

结果包括所有率定候选、锁参盲测、网格敏感性、几何门控、图和机器可读状态。只有五个盲测构型全部通过几何门控、观测算子固定且能力合入生产引擎后，才能将其称为正式验证。

## 来源

- 论文：<https://www.nature.com/articles/s41597-022-01282-w>
- 数据：<https://doi.org/10.5281/zenodo.5254164>

论文和数据均为 CC BY 4.0。
