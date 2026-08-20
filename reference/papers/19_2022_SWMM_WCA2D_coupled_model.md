---
title: "Simulation Performance Evaluation and Uncertainty Analysis on a Coupled Inundation Model Combining SWMM and WCA2D"
pdf: "19_2022_SWMM_WCA2D_coupled_model.pdf"
date_analyzed: "2026-08-07"
tags: ["SWMM", "WCA2D", "1D-2D耦合", "不确定性"]
stars: 5
---

## 论文解读

论文在广州把 SWMM 的降雨—径流—管网过程与 WCA2D 地表漫流耦合，并以 SWMM/LISFLOOD-FP 为对照。CA 耦合模型在个案中快约 3–5 倍。

## 关键发现

地形分辨率和降雨时间分辨率影响显著；该案例中 DEM 粗于 15 m、降雨间隔粗于 30 min 时结果可信度下降。粗糙度和模型类型对部分最大水深指标影响相对有限，但不能外推为普遍规律。

## 与 RainFall 的关系

“SWMM + CA 快速耦合”已被做过。RainFall 若无可靠管网数据，应避免形式化耦合；若有数据，创新应是山地村镇地表—沟渠—涵洞—小河网的守恒交换、动态激活与跨尺度误差控制。
