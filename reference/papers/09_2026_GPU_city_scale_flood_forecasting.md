---
title: "GPU-accelerated city-scale urban flood forecasting for real-time decision-making"
pdf: "09_2026_GPU_city_scale_flood_forecasting.pdf"
date_analyzed: "2026-08-07"
tags: ["实时洪涝", "GPU", "城市决策", "SynxFlow"]
stars: 5
---

## 论文解读

该研究使用 SynxFlow 在芝加哥都会区 10 m 网格上求解浅水方程，以 Sentinel-1 洪水范围验证，并对比 SWMM–HEC-RAS-2D 与 HAND。论文展示四张 A100 上约 3 h 完成一次实际暴雨模拟，强调“快于事件演变”对决策的意义。

## 与 RainFall 的关系

GPU 城市尺度实时水动力和决策表述已经高度重合。RainFall 不能仅用“分钟级 + GPU + 高分辨率”作为创新；差异应是山区村镇、多尺度预算、集合概率、在线观测更新和可执行转移窗口。

## 局限

其运行时间仍非分钟级滚动集合，验证主要是洪水范围，排水和独立水深/流速证据有限。可作为强工程基线，而非证明 RainFall 已可行。
