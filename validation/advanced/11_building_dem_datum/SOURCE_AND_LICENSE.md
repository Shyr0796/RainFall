# 官方来源与使用边界

## NYC Building Footprints

- 数据主页：<https://data.cityofnewyork.us/City-Government/BUILDING/3g6p-4u5s>
- 官方元数据：<https://github.com/CityOfNewYork/nyc-geo-metadata/blob/main/Metadata/Metadata_BuildingFootprints.md>
- ArcGIS Feature Service：<https://services6.arcgis.com/yG5s3afENB5iO9fj/ArcGIS/rest/services/BUILDING_view/FeatureServer/0>
- 查询范围：`[-73.965, 40.795, -73.955, 40.805]`，仅 `FEATURE_CODE=2100` 且高度和基底非空/正值。
- 查询参数：`geometry=-73.965,40.795,-73.955,40.805`、`geometryType=esriGeometryEnvelope`、`inSR=4326`、`outSR=4326`、`spatialRel=esriSpatialRelIntersects`、`outFields=*`、`f=geojson`；过滤式为 `FEATURE_CODE=2100 AND HEIGHT_ROOF>0 AND GROUND_ELEVATION IS NOT NULL`。
- 原始查询响应：`data/raw/nyc_buildings_official.geojson`，不手工修改。
- 当前快照：752 个 Polygon；全部 `FEATURE_CODE=2100`，高度为正且地面高程非空；750,453 bytes；SHA-256 `220accdf2ec43bbe21fca9acecdb5f27fb5fe939424b83e5d75b62c2449fe2f1`。
- NYC Open Data 使用条款适用。

## NOAA 2017 NYC bare-earth DEM

- 元数据：<https://www.fisheries.noaa.gov/inport/item/64732>
- 批量目录：<https://noaa-nos-coastal-lidar-pds.s3.us-east-1.amazonaws.com/dem/NYC_topobathy_BE_DEM_2017_9307/>
- 使用瓦片：`be_NYC_029.tif`；原始 CRS `EPSG:6539`，NAVD88 ftUS，1 ft 网格。
- 直接文件：<https://noaa-nos-coastal-lidar-pds.s3.us-east-1.amazonaws.com/dem/NYC_topobathy_BE_DEM_2017_9307/be_NYC_029.tif>
- 当前快照：25,000 × 12,511 cells；316,459,579 bytes；SHA-256 `d66b19ab0a3b643a2ad683a48f020ddbeb77e00fdf20a32755d30610c9729498`。
- NOAA 元数据报告开阔裸地 NVA 为 0.074 m（95%），但这不能直接外推到建筑足迹内插值。
- 数据公开，无访问限制；使用时必须保留 NOAA 的时效和关键应用限制声明。

`results/metrics.json` 保存原始文件 SHA-256。派生裁剪 DEM、Shapefile 和 NPZ 均可由脚本重建。

`be_NYC_002.tif` 是选瓦片时保留的未使用候选，不参与本实验、结果散列或论文样本定义。
