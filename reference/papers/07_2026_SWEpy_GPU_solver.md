---
title: "SWEpy: an open-source GPU-accelerated solver for inundation and tsunami modeling"
pdf: "07_2026_SWEpy_GPU_solver.pdf"
date_analyzed: "2026-08-07"
tags: ["洪涝水动力", "GPU", "开源求解器", "浅水方程"]
stars: 4
---

## 论文解读

SWEpy 提供开源 GPU 浅水方程求解器，采用高阶重构和适合并行的数组计算，在消费级硬件上展示实时或快于实时的潜力。

## 与 RainFall 的关系

它削弱了“开发一个 GPU 浅水求解器”作为独立创新的力度，但可作为重点区 5–10 m 精算引擎的技术参照。RainFall 的差异应来自动态激活、降雨—产流接口、村镇微地形、在线同化和行动产品，而非 CUDA 化本身。

## 局限

论文重点包括近场淹没与海啸，不是完整的山地村镇暴雨业务系统。迁移时需要重新验证直接降雨、陡坡、建筑绕流、涵洞和干湿界面。
