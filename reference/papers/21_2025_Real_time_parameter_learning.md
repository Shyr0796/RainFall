---
title: "Real-Time Flood Inundation Modeling With Flow Resistance Parameter Learning"
pdf: "21_2025_Real_time_parameter_learning.pdf"
date_analyzed: "2026-08-07"
tags: ["在线参数学习", "贝叶斯优化", "实时洪涝", "传感器布设"]
stars: 5
---

## 论文解读

该文把快速二维模型、敏感性驱动的水深传感器布设和贝叶斯优化组成“观测—校准—预报”循环，在线估计代表未解析地表影响的阻力参数。

## 关键结果

在 52 km² 合成观测案例中，50 次以内模型—优化迭代即可收敛；相较固定阻力参数，到达时间误差减少 3.13 h，部分淹没指标超过 90%。

## 与 RainFall 的关系

它与“在线参数更新”高度重合。RainFall 可扩展为多尺度、多参数和异质观测，但必须避免把合成真值结果当现场证据。真正的贡献应包括观测选址、实时预算、可辨识性和独立事件性能。
