---
title: "Efficient Urban Inundation Model for Live Flood Forecasting with Cellular Automata and Motion Cost Fields"
pdf: "18_2020_CAMC_live_flood_forecasting.pdf"
date_analyzed: "2026-08-07"
tags: ["元胞自动机", "实时洪涝", "CAMC", "速度局限"]
stars: 5
---

## 论文解读

CAMC 将元胞自动机与 Motion Cost 场结合，在约 1.2 万栋建筑的 Wuppertal 案例中比 ANUGA 更快，并嵌入网页“live”预警界面。水深一致性尚可，但速度表现明显较弱。

## 关键结果

论文报告水深平均 NSE 0.61、RMSE 0.39 m；速度 NSE 0.34、RMSE 0.13 m/s。作者明确指出，忽略动量守恒使 CA 在速度矢量、结构冲击和入射角方面先天不利。

## 与 RainFall 的关系

它直接否定“简化 CA 同时可靠输出水深、速度和方向”的宽泛表述。RainFall 可把简化 CA 放在区域快筛层，高风险区必须切换到动态波 CA 或 SWE，并通过守恒通量连接。
