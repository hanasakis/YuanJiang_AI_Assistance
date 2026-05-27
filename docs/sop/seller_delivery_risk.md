# 卖家履约延迟风险巡检 SOP

**文档编号**: SOP-DELIVERY-001
**版本**: v1.0
**适用范围**: 所有平台卖家

---

## 1. 风险定义

卖家履约延迟指订单从发货到签收的时间超过平台承诺的预计送达日期。

### 1.1 关键指标

| 指标 | 公式 | 数据来源 |
|------|------|----------|
| delivery_delay_days | 实际送达日期 - 预计送达日期 | orders_enriched |
| seller_delay_rate | 延迟订单数 / 总订单数 | seller_delivery_metrics |
| avg_delivery_delay_days | AVG(delivery_delay_days) | seller_delivery_metrics |

### 1.2 风险等级判定

**P0 紧急（立即下架 + 人工介入）**:
- seller_delay_rate > 30%
- 或单笔订单 delay > 15 天

**P1 重要（24h 内创建整改任务）**:
- seller_delay_rate 15% ~ 30%
- 或 avg_delivery_delay_days > 7

**P2 关注（周度巡检关注）**:
- seller_delay_rate 5% ~ 15%
- 或 avg_delivery_delay_days 3 ~ 7

**P3 观察（月度趋势监控）**:
- seller_delay_rate < 5% 但呈上升趋势

---

## 2. 检查流程

### 2.1 数据查询

```
1. 查询 top_risky_sellers, metric_name=top_risky_sellers
2. 筛选 risk_type=logistics_delay 的卖家
3. 对 P0/P1 卖家展开 seller_profile 详细分析
```

### 2.2 证据收集

对每个风险卖家收集：
- 最近 30 天订单列表（含 delivery_delay_days）
- 承运商分布（是否集中在特定承运商）
- 地区分布（是否集中在特定区域）
- 季节性因素（是否为旺季）

### 2.3 任务创建

```
P0 → 自动创建"紧急整改"任务，抄送区域经理
P1 → 创建"限期整改"任务，3 个工作日追踪
P2 → 加入周度巡检清单
P3 → 加入月度趋势图表
```

---

## 3. 豁免场景

以下情况不触发延迟告警：
- 买家主动要求延迟发货（需 ticket 记录证明）
- 不可抗力（自然灾害、疫情封控，需区域主管审批）
- 预售商品（需在商品页标注预售周期）

---

## 4. 常见案例

### 案例 1：系统性延迟

卖家 seller_A 连续 30 天 delay_rate 23%，avg_delay 8 天。
分析发现该卖家 80% 订单发往偏远地区，承运商 SLA 不覆盖。
**处理**: 建议卖家切换承运商或设置偏远地区不发货。

### 案例 2：偶发延迟

卖家 seller_B delay_rate 35%，但仅 20 笔订单。
分析发现其中 7 笔延迟发生在同一天（仓库停电）。
**处理**: P2 关注即可，不触发 P0。
