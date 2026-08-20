---
title: "Residual corrective diffusion modeling for km-scale atmospheric downscaling"
pdf: "04_2025_CorrDiff_km_scale_downscaling.pdf"
date_analyzed: "2026-08-07"
tags: ["气象下推", "CorrDiff", "概率集合", "公里尺度"]
stars: 5
---

## 论文解读

CorrDiff 先做确定性回归，再用扩散模型生成残差细节，将约 25 km 场下推到约 2 km，并表达台风雨带等小尺度不确定性。它是 RainFall “概率化精细雨场”最直接的算法先例之一。

## 与 RainFall 的关系

- **高重合**：生成式概率下推、集合样本、极端结构恢复。
- **未解决**：降雨总量严格守恒、雷达—站点—NWP 在线融合、2 km 到村镇尺度的真实性，以及不确定性向洪涝行动的传播。

## 结论

“使用 CorrDiff 下推”本身创新性较低。可形成贡献的是：以水文守恒和洪涝后果为约束的在线融合、错误细节检测，以及针对广西复杂地形的独立事件验证。
