---
title: "GPTCast: a weather language model for precipitation nowcasting"
pdf: "03_2024_GPTCast_weather_language_model.pdf"
date_analyzed: "2026-08-07"
tags: ["降水临近预报", "天气语言模型", "集合预报"]
stars: 3
---

## 论文解读

GPTCast 将雷达降水场离散为 token，再用自回归模型生成未来序列。其价值是提供多模态未来和统一序列建模接口，而非证明降雨细节都可被准确恢复。

## 与 RainFall 的关系

它与 RainFall 的“多成员动态降雨场”存在方法重合，但没有水文—水动力闭环。若采用 token 化路线，需重点检查长时滚动误差、雨峰漂移、累计雨量偏差和极端尾部退化。

## 创新判断

“把天气当语言建模”已不是可单独声称的创新。RainFall 更适合把它作为备选雨场生成器，与 NowcastNet、PreDiff、雷达外推和 NWP 集合做统一后验校准。
