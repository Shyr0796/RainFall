---
title: "PreDiff: Precipitation Nowcasting with Latent Diffusion Models"
pdf: "02_2023_PreDiff_precipitation_nowcasting.pdf"
date_analyzed: "2026-08-07"
tags: ["降水临近预报", "扩散模型", "概率集合", "知识约束"]
stars: 4
---

## 论文解读

PreDiff 把降水临近预报建模为潜空间条件扩散过程，并引入知识对齐机制，使多个未来样本能够表达不确定性。它说明“一个确定性未来”不足以描述强对流雨团演变。

## 与 RainFall 的关系

- **重合**：概率化雨场生成与多成员情景直接重合。
- **差异**：PreDiff 重点是雷达序列，不处理雨量守恒、地形下推后的水文一致性和洪涝决策。
- **启示**：可作为降雨集合基线；创新应落在区域总量、移动连续性、极端尾部校准和洪涝损失函数的联合约束。

## 局限

主要实验基于 SEVIR 等数据。扩散样本的视觉真实性不等于位置准确性，RainFall 应同时报告 CRPS、可靠度、极端阈值命中和水动力结果敏感性。
