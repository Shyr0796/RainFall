# 09 USGS Muddy Creek 降雨驱动真实洪水验证

## 结论

该数据可以公开获取，不需要用户另行申请。USGS 完整档案已经下载：包含 HEC-HMS 降雨—径流工程、HEC-RAS 2D 几何与结果、高分辨率地形、Manning 粗糙度、7 个压力水位计的 5 分钟序列、高水位痕迹以及发布者的率定/验证指标。因此它适合成为 RainFall 的“独立真实事件”验证场。

但它还不能直接由当前 RainFall 核心运行。主要工作是把 HEC-DSS 时序转换为公开表格、把英尺/NAVD 88 地形与糙率转换为 RainFall 网格，并实现河道入流和下游水位边界。当前状态是**数据包完整、观测目标已提取、适配器待开发**，不是模型验证完成。

## 预注册事件划分

- 率定：2021-05-27 与 2021-06-25，只率定少量产流、糙率和边界参数。
- 盲测：2021-04-29；参数锁定后一次运行。
- 外部复核：2021-03-17。
- 2019-09-28 只有高水位痕迹，作为峰值空间约束，不进入连续时序评分。

这种划分优先保障真正的盲测；USGS 原报告自己的 calibration/validation 标签只作为参考，不等于 RainFall 的数据分割。

## 论文指标

1. 水位时序：MAE、RMSE、NSE、KGE、峰值误差、峰现时间误差。
2. 空间峰值：压力计和高水位痕迹的水面高程 MAE/RMSE/偏差。
3. 洪水范围：CSI、F1、命中率、虚警率；对 0.05/0.10/0.20 m 阈值做敏感性。
4. 深度栅格：湿区 MAE/RMSE、分位数误差和空间相关性。
5. 守恒：累计降雨、入流、出流、入渗和域内储量的闭合误差。
6. 不确定性：降雨、糙率、入渗、DEM 与边界分别扰动，按事件和监测站 bootstrap 95% 区间。

## 已运行的审计

```bash
bash validation/advanced/09_usgs_muddy_creek/code/fetch_data.sh --full
uv run --with rasterio --with pyshp --with pandas --with matplotlib --with h5py \
  python validation/advanced/09_usgs_muddy_creek/code/audit_usgs.py
```

关键输出在 `results/`：来源散列、栅格/HDF 清单、压力计质量表、事件观测目标、发布者参考指标、诊断图和机器可读状态。

## 官方来源

- USGS 数据发布：<https://www.usgs.gov/data/geospatial-data-and-model-archives-associated-precipitation-driven-flood-inundation-mapping>
- ScienceBase DOI：<https://doi.org/10.5066/P969ZOLB>
- USGS Scientific Investigations Report：<https://pubs.usgs.gov/publication/sir20225084>

许可为 CC0 1.0。USGS 目录中的 XML MD5 与当前端点下载内容发生漂移；ZIP 数据均通过发布者 MD5，XML 异常单独保留在审计结果中。
