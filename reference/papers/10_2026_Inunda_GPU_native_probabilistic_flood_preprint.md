---
title: "Inunda: A GPU-Native, Agent-enabled, Differentiable Solver for High-Resolution Flood Inundation Modeling"
pdf: "10_2026_Inunda_GPU_native_probabilistic_flood_preprint.pdf"
date_analyzed: "2026-08-07"
tags: ["GPU原生", "可微分水动力", "概率洪涝", "预印本"]
stars: 5
---

## 论文解读

Inunda 是 GPU 原生、质量守恒、可微分的二维洪涝求解器。论文结合高水位标记、站点过程和 18 成员公里级降雨集合，展示真实事件后报、概率预报和梯度校准。

## 与 RainFall 的关系

它几乎覆盖“GPU + 高分辨率 + 集合降雨 + 概率淹没 + 在线/事件参数估计”的算法愿景，是最强直接竞争工作之一。RainFall 的差异不能再是这些关键词的并列，而应是数据稀缺村镇的多尺度求解切换、守恒雨场下推、行动决策和跨事件盲测。

## 局限

这是很新的单作者预印本，复现性和业务稳定性仍需验证。其代理/智能体标签也不等于已经完成制度化预警发布链。
