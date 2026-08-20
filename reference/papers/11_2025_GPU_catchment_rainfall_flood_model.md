---
title: "An Integrated Hydrological-Hydrodynamic Model Based on GPU Acceleration for Catchment-Scale Rainfall Flood Simulation"
pdf: "11_2025_GPU_catchment_rainfall_flood_model.pdf"
date_analyzed: "2026-08-07"
tags: ["水文水动力耦合", "GPU", "流域洪水", "降雨径流"]
stars: 5
---

## 论文解读

该文把降雨产汇流与二维水动力耦合并使用 GPU 加速，说明县域/流域降雨洪水不能只做地表“摊水”，初始土壤、汇流和河网边界必须进入系统。

## 与 RainFall 的关系

“GPU 水文—水动力一体化”已有直接重合。RainFall 可进一步研究 30 m 全域筛查与重点村精算之间的守恒状态传递、集合雨场的误差传播和山区涵洞/小河道的显式表达。

## 局限

结论依赖流域率定、土壤状态与河网数据。其个案性能不能迁移为广西承诺，且没有覆盖道路可达性与撤离行动验证。
