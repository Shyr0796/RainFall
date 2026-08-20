---
title: "A high-performance approach with cellular automata framework and GPU parallelization for real-time waterflows and pollutant transport simulations of pluvial and fluvial floods"
pdf: null
access: "source-only"
date_analyzed: "2026-08-07"
tags: ["GPU", "动态波CA", "污染物输运", "实时模拟"]
stars: 5
---

## 来源状态

已核验 [开放获取期刊页](https://doi.org/10.1016/j.wroa.2025.100397) 及可检索全文；出版平台验证码阻断自动 PDF 下载。

## 论文解读

论文把 SWFCA 与高级 CA 溶质输运求解器耦合，并用 OpenCL/CUDA 并行。报告相对有限体积替代方案最高约 74.2 倍加速，约 11 万网格的 24 h 场景在其硬件上约 20 s 完成。

## 与 RainFall 的关系

“GPU 并行动态波 CA 实时模拟”已被直接做过。RainFall 的创新应从单求解器转向风险触发的多尺度系统、降雨与观测不确定性、排水/河道耦合和行动效果；论文自身也把管网与河流耦合作为未来工作。
