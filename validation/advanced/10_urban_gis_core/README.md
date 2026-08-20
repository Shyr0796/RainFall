# 10 城市 GIS—建筑—边界核心回归

## 目的

本实验验证生产求解器新增的城市几何链，而不是验证某个真实城市：GeoTIFF 地面 DEM 与 ESRI Shapefile 建筑在统一 CRS/网格中对齐；建筑属性生成屋顶高程，同时建筑足迹作为不可储水、不可降雨、不可入渗、不可交换面通量的固体体积；三个指定流量入口与三个固定水深出口分别记账。

## 设计

- CRS：`EPSG:32650`，2 m 方格，60 × 80 格；
- DEM：有明确东西坡降的合成地面；
- Shapefile：8 个规则街区，字段 `height_m`；
- 配对场景：相同 DEM、入口、出口和参数，只改变是否启用建筑固体掩膜；
- 主要门控：建筑内水深为零、建筑相邻面通量为零、建筑栅格化面积与矢量面积一致、相对水量闭合误差小于 `5e-5`；
- 探索性结果：比较有/无建筑时最大水深和速度，不能当作实测精度。

## 本轮结果

全部五项核心门控通过：建筑栅格面积误差、建筑内最大水深和跨建筑面通量均为 0，相对水量闭合误差为 `8.25e-7`。在完全相同的边界和参数下，启用建筑后相对无建筑场景的全域水深 MAE 为 11.68 mm、最大局部水深差为 40.72 mm、速度模长 MAE 为 0.0576 m/s，说明建筑几何确实改变了计算流场；这些差值没有实测真值，只用于敏感性和代码回归。

## 复现

```bash
uv run --extra gis python validation/advanced/10_urban_gis_core/code/run_experiment.py
```

结果写入 `data/`、`results/` 和 `logs/`。核心通用预处理命令为：

```bash
uv run --extra gis python scripts/prepare_urban_domain.py \
  --dem path/to/dem.tif --buildings path/to/buildings.shp \
  --height-field height_m --target-crs EPSG:32650 \
  --resolution-m 2 --output data/processed/city_domain.npz
```

网页 API 只允许从项目内 `data/processed/` 加载已准备的 `.npz`，避免任意服务器路径访问。真实应用仍须确认 DEM 垂直基准、建筑高度语义、桥涵/门洞、道路与路缘微地形，以及入口/出口的物理定义。
