---
title: "Laboratory modelling of urban flooding"
pdf: "22_2022_Laboratory_urban_flooding_dataset.pdf"
date_analyzed: "2026-08-07"
tags: ["实验数据", "LSPIV", "水深", "速度场验证"]
stars: 5
---

## 论文解读

论文发布城市街区实验数据，包括入口水深、出口流量和八种城市形态下的 LSPIV 二维表面速度场，适合验证水深、流量分配、速度与方向。

## 与 RainFall 的关系

这是动态波 CA/SWE 原型的重要独立基准。RainFall 应先在可控实验和标准算例上验证水深、$u/v$、方向与质量守恒，再进入广西历史事件。

## 局限

LSPIV 测表面速度，二维模型通常输出深度平均速度；缩尺、几何畸变、反光和低纹理也会带来误差。需要预先定义换算和掩膜规则。
