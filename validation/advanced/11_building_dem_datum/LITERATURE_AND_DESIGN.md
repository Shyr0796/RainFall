# 建筑、道路与 DEM 耦合：文献依据和冻结设计

## 1. 文献与数据证据

- NYC Building Footprints 官方元数据同时给出建筑足迹、最低地面高程 `GROUNDELEV` 和相对地面的屋顶高度 `HEIGHTROOF`；`HEIGHTROOF=0/NULL` 表示未知。其现代摄影测量地面高程使用 NAVD88，但记录来源和年代可能不同。数据主页与元数据：[NYC Open Data](https://data.cityofnewyork.us/City-Government/BUILDING/3g6p-4u5s)、[字段定义](https://github.com/CityOfNewYork/nyc-geo-metadata/blob/main/Metadata/Metadata_BuildingFootprints.md)。
- NOAA 2017 NYC Topobathy 产品是去除建筑等人工物的裸地 DEM，原始网格为 1 US survey foot，垂直基准 NAVD88。其开阔裸地精度不能直接外推到建筑足迹内：[NOAA InPort 64732](https://www.fisheries.noaa.gov/inport/item/64732)。
- Iliadis、Glenis 与 Kilsby 比较了城市洪水模型的建筑表示；Building Hole 把建筑从计算域排除，避免把任意屋顶高程作为可储水地形：[Journal of Flood Risk Management, 2024](https://doi.org/10.1111/jfr3.12950)。
- Schubert 与 Sanders 系统比较 building resistance、block、hole 和 porosity 方法，说明建筑表示本身是模型结构选择：[Advances in Water Resources, 2012](https://doi.org/10.1016/j.advwatres.2012.02.012)。
- Muthusamy 等及后续研究表明，网格分辨率会影响城市通道和建筑间隙的连通性；建筑总面积接近并不足以证明街巷拓扑正确：[Journal of Hydrology, 2021](https://doi.org/10.1016/j.jhydrol.2021.126088)、[Journal of Hydrology: Regional Studies, 2022](https://doi.org/10.1016/j.ejrh.2022.101122)。

## 2. 冻结的数据契约

每次预处理必须显式记录以下量，缺一项即停止：

1. DEM 水平 CRS、垂直基准、垂直单位和产品类型（DTM/DSM）。
2. 建筑高度字段的语义（相对高度/绝对屋顶高程）、单位、缺失值编码和要素类型。
3. 建筑地面高程字段的垂直基准、单位和到 DEM 基准的转换依据。
4. 输出求解网格的投影、分辨率、仿射变换和输入散列。

相对高度采用：

```text
z_terrain_m = z_DEM × DEM_unit_to_m
h_building_m = H_attribute × building_unit_to_m
z_roof_m = z_terrain_m + h_building_m
```

绝对屋顶字段才允许直接作为 `z_roof_m`，并且必须已转换到与 DEM 完全相同的垂直基准。若基准不同，只允许使用有出处、适用于该位置的垂直转换；禁止用一个未审计的全域常数猜测。

## 3. 建筑水动力表示

主方案冻结为 Building Hole / solid mask：

- 建筑单元不储水，不接收降雨或入渗；
- 建筑—流体界面的法向通量为零；
- 屋顶 DEM 只用于三维显示、属性 QC 和最低屏障合理性检查；
- 同一足迹下改变屋顶高度不得改变水深或通量，已由自动回归验证。

只有已知门洞、连廊下方、建筑穿堂或可淹地下入口的三维几何和底高程时，才从 solid mask 中开孔。信息未知时不猜测；把位置列为结构不确定性，并用“封闭/开放”两种情景给结果范围。

## 4. 道路与特殊构筑物

没有道路高程、路缘和桥涵数据时，道路采用裸地 DEM 原值，不由道路中心线生成虚构高度，不全域填洼。道路矢量可用于结果抽样、暴露分析和拓扑 QC，但不改变水动力地形。

桥、涵洞、地下通道和门洞不能仅凭二维轮廓可靠转换为一个高度：它们具有上下叠置或开孔语义。当前范围内应从普通地面阻挡建筑中排除 skybridge、悬挑和语义不明要素；缺失构筑物进入局限性清单，不混入“已验证建筑耦合”的结论。

## 5. 质量门控与论文允许表述

- 单位控制：脚误当米会造成 3.28084 倍高度错误；必须由独立比例参数阻断。
- 基准控制：同名 NAVD88 只是必要条件，不代表两个不同时期/观测算子的表面可互换。
- 几何控制：检查无效/重叠多边形、建筑类型、栅格化面积和窄巷连通性；建议城市精细域使用 1–2 m，并逐场地检查关键通道。
- 属性控制：正式运行使用 `missing_height_policy=error`；若为了展示使用默认高度，必须单列数量且不得进入验证样本。
- 水动力控制：建筑内最大水深和跨界面通量必须为零，改变显示屋顶高度后的解必须逐位相同。

本实验允许写作“建筑—DEM 数据契约与固体边界实现通过官方数据耦合诊断”。它不允许写作“城市洪水模型已经通过真实事件验证”，后者仍需要同步降雨、水深/流速和边界观测。
