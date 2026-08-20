---
title: "Dynamic-wave cellular automata framework for shallow water flow modeling"
pdf: null
access: "source-only"
date_analyzed: "2026-08-07"
tags: ["动态波CA", "SWFCA", "动量", "实时洪涝"]
stars: 5
---

## 来源状态

已核验 [期刊 DOI](https://doi.org/10.1016/j.jhydrol.2022.128449)、作者机构条目与全文页面；自动下载被出版平台验证码阻断，因此未伪造本地 PDF。

## 论文解读

SWFCA 用 Bernoulli 水头连接水深与速度，在 CA 框架中同时传播质量和惯性。论文用 4 个规则流与 6 个强间断基准验证，并与 WCA2D 和 FV-HLLC 比较。

## 与 RainFall 的关系

动态波 CA 本身已被提出并验证，RainFall 不能把“CA 原生输出速度方向”作为全新贡献。可创新的是 GPU 化、多尺度异构切换、直接降雨/管网耦合、复杂地形盲测和面向行动的误差证书。
