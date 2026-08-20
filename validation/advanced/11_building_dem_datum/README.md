# 11 建筑高度—DEM 垂直基准耦合验证

## 核心问题

建筑矢量中的高度字段不能直接加到 DEM 上。必须先回答：字段是相对高度还是绝对屋顶高程，单位是米还是英尺，建筑基底与 DEM 是否使用同一垂直基准，以及 DEM 是裸地 DTM 还是包含屋顶的 DSM。

本实验使用两套独立官方数据：

- NYC OTI Building Footprints：轮廓、`GROUNDELEV` 和 `HEIGHTROOF`；官方定义 `HEIGHTROOF` 为屋顶相对建筑地面的高度，零或空值表示未知；
- NOAA 2017 NYC Topobathy bare-earth DEM：1 US survey foot 网格，水平 CRS `EPSG:6539`，垂直基准 NAVD88、单位 US survey foot。

从 NYC ArcGIS 服务提取的 752 个普通建筑被保存为真正的高度 Shapefile：`data/processed/nyc_buildings_height.shp`。Skybridge、悬挑、占位符和施工中建筑未进入这一基准。

## 冻结的转换规则

```text
z_dem_m  = z_dem_ftUS × 1200 / 3937
h_bldg_m = HEIGHTROOF_ft × 0.3048
z_roof_m = z_dem_m + h_bldg_m
```

建筑的水动力表示采用 solid mask（Building Hole）：建筑足迹不储水、不接收降雨/入渗、跨建筑面通量为零。屋顶高度用于单位/基准审计、三维显示和最低屏障合理性检查，不进入地表通量公式。因此，只要建筑仍为不可进入实体，屋顶高度误差不会悄悄改变二维水动力结果。

`GROUNDELEV` 只用于独立 QC，不覆盖 NOAA DEM。原因由本实验实测决定：虽然字段名义上与现代数据同为 NAVD88，它与 2017 DEM 的建筑足迹最低值仍存在明显差异；缺少逐建筑来源/年代/精度标志时，强行用它抬升或压低地形反而会破坏道路—建筑边界。

## 道路策略

在没有路缘、桥涵和道路高程矢量时，道路不另造高度：`active_mask & ~building_mask` 的裸地 LiDAR DEM 就是地表流动域。保留真实洼地，不做全局填洼。道路中心线只能用于标注和结果抽样，不能凭中心线生成路面高程。

这一策略不会声称表达路缘、地下通道、桥下净空或门洞。相关位置必须在论文中标记为模型结构不确定性，不能用任意高度猜测补齐。

## 复现

```bash
uv run --extra dev --extra gis python \
  validation/advanced/11_building_dem_datum/code/run_validation.py
```

主要结果为 `results/metrics.json`、逐建筑误差表、分辨率敏感性表和 `vertical_coupling_validation.png`。
