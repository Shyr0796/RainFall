---
title: "LISFLOOD-FP 8.2: GPU-accelerated multiwavelet DG solver with dynamic resolution adaptivity"
pdf: "06_2025_LISFLOOD_FP_8_2_GPU_multiscale.pdf"
date_analyzed: "2026-08-07"
tags: ["洪涝水动力", "GPU", "动态分辨率", "LISFLOOD-FP"]
stars: 5
---

## 论文解读

LISFLOOD-FP 8.2 将 GPU、二维浅水方程、多小波 DG 与逐时间步动态分辨率适配结合，用局部加粗/加密减少单元数并保持多尺度洪水过程。

## 与 RainFall 的关系

- **极高重合**：GPU + 动态多尺度计算已经被直接实现，因此“事件驱动多尺度”不能只停留在动态加密概念。
- **可区分方向**：RainFall 可研究由水文拓扑、人口/道路风险和误差估计共同触发的 30 m→5–10 m→1–2 m 切换，以及 CA 与 SWE 异构求解器之间的守恒接口。

## 局限与基线作用

论文案例以快速、多尺度水动力为主，不等于完整降雨—产流—管网—行动链。它应作为求解器速度和精度的强基线，而不是仅作背景引用。
