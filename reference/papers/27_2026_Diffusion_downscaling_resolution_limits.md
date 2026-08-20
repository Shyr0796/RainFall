---
title: "How far can we downscale? Resolution limits and physical interpretability of diffusion models for African precipitation"
pdf: "27_2026_Diffusion_downscaling_resolution_limits.pdf"
date_analyzed: "2026-08-07"
tags: ["扩散下推", "分辨率极限", "虚假细节", "极端降雨"]
stars: 5
---

## 论文解读

论文系统比较扩散模型与确定性 CNN 在降水下推中的点误差、空间结构和极端尾部，并逐步把输入从 0.25° 降级到 1.0°，检验信息缺失下的生成极限。

## 关键结论

扩散单成员能保持空间方差和重尾极端，但当粗分辨率约束过弱时会错置强对流核并产生局地虚警；集合平均的平滑程度可反映空间不确定性。

## 与 RainFall 的关系

这是“避免精细化幻觉”的关键引用。RainFall 应给出下推可辨识尺度、虚假细节诊断和集合传播，不可把 6 km/3 km 输入直接包装成 30 m 真实雨场。
