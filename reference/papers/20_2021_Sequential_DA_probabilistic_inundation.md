---
title: "Sequential data assimilation for real-time probabilistic flood inundation mapping"
pdf: "20_2021_Sequential_DA_probabilistic_inundation.pdf"
date_analyzed: "2026-08-07"
tags: ["数据同化", "EnKF", "概率淹没", "LISFLOOD-FP"]
stars: 5
---

## 论文解读

论文用多变量集合卡尔曼滤波将流量和水位站观测同化到 LISFLOOD-FP，同时更新状态与参数，面向实时概率淹没图。合成实验与 Hurricane Harvey 案例均用于评估。

## 关键结果

作者报告概率淹没精度和可靠度改善约 5%–7%，并强调确定性洪水图可能误导决策。

## 与 RainFall 的关系

“观测同化 + 在线参数更新 + 概率洪水图”整体并非新概念。RainFall 的空间在于分钟级山洪、异质观测质量、状态与参数可辨识性、风险驱动传感器选择，以及同化收益对行动提前量的真实验证。

## 局限

原框架主要为河流洪水、日尺度更新和点位站观测，不能直接代表短历时村镇暴雨。
