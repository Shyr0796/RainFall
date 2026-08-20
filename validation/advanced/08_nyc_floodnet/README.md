# 08 NYC FloodNet 真实城市街道积水验证

## 本轮完成程度

纽约市官方洪水事件表、传感器部署表、数据字典和方法说明已经下载并校验。`code/audit_floodnet.py` 会审计每个事件的水深序列、时间轴、峰值、持续时间与部署有效期，并按事件间隔构建全市风暴候选集。

这一步是**真实观测目标构建**，还不是 RainFall 验证结果。缺少与候选事件同步的降雨、潮位、DEM、排水与边界条件时，不能把观测水深直接拿来宣称模型精度。

## 后续正式实验

1. 预先冻结两个非潮汐事件用于率定、一个非潮汐事件用于盲测；另设潮汐事件作为外部边界扩展实验。
2. 获取 NYS Mesonet/NYC Micronet 5 分钟降雨，潮汐组获取 NOAA/USGS 6 分钟水位。
3. 使用 NYC 高分辨率地形和公开排水资料构建计算域；所有地形修正、建筑与路缘处理保留版本和散列值。
4. 率定阶段只允许调整预注册的少量参数；盲测事件参数锁定。
5. 对传感器位置和局部低点分别报告峰值水深误差、峰现时间误差、持续时间误差、整段水深 MAE/RMSE、阈值超限 CSI/F1，并用传感器分组 bootstrap 给出 95% 区间。

## 观测算子

FloodNet 传感器常位于人行道上方，并不一定处于街道局部最低点。主比较应使用“传感器正下方网格”的模拟水深；局部低点水深仅作为二级指标，按部署表中的 `lowest_point_height_delta_inches` 做显式高程差修正。潮汐影响站点必须单独报告，不能与纯降雨积水混合汇总。

## 复现

```bash
MPLCONFIGDIR=/tmp/mpl-floodnet python3 validation/advanced/08_nyc_floodnet/code/audit_floodnet.py
```

输出：`results/qc_summary.json`、`candidate_storms.csv`、`event_sensor_metrics.csv`、两张诊断图及 `data/processed/event_profiles_long.csv`。

## 官方来源

- NYC Open Data 事件表：<https://data.cityofnewyork.us/d/aq7i-eu5q>
- NYC Open Data 部署表：<https://data.cityofnewyork.us/d/kb2e-tjy3>
- FloodNet 方法说明：<https://www.floodnet.nyc/methodology>

原始文件未作修改；本目录的处理结果不能替代原发布方数据。
