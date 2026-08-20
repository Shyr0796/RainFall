---
title: "A highly generalizable data-driven model for spatiotemporal urban flood dynamics real-time forecasting based on coupled CNN and ConvLSTM"
pdf: "23_2026_CNN_ConvLSTM_urban_flood_forecasting.pdf"
date_analyzed: "2026-08-07"
tags: ["城市洪涝", "CNN", "ConvLSTM", "实时预测"]
stars: 5
---

## 论文解读

论文用地形、坡度、管网/检查井等静态特征，加上历史—未来降雨、潮位和过去水深，递归预测下一时段的淹没水深，并允许用观测水深更新动态输入。

## 与 RainFall 的关系

“实时洪涝 + 历史水深反馈 + 数据驱动代理”已有直接先例。RainFall 若训练代理模型，需要特别证明跨雨型、跨地形和跨村镇泛化，以及质量守恒与极端外推安全性。

## 局限

数据驱动模型依赖训练分布和上游模拟数据。递归误差可能累积；其“可同化”接口不等于已完成严格的贝叶斯/集合同化。
