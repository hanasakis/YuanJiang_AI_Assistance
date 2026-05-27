# 巡检任务管理策略

**文档编号**: SOP-TASK-004
**版本**: v1.0
**适用范围**: 运营管理

---

## 1. 任务创建规则

### 1.1 自动创建条件

系统在以下情况自动创建巡检任务：

| 触发条件 | 任务类型 | 优先级 | 指派 |
|----------|----------|--------|------|
| seller_delay_rate > 30% | delivery_risk | P0 | 区域经理 |
| low_review_rate > 50% | review_triage | P0 | 客服主管 |
| defect_rate > 40% | quality_inspection | P0 | 品控主管 |
| seller_delay_rate 15%-30% | delivery_risk | P1 | 运营专员 |
| low_review_rate 30%-50% | review_triage | P1 | 客服专员 |
| defect_rate 20%-40% | quality_inspection | P1 | 品控专员 |

### 1.2 任务去重

同一卖家/商品在同一巡检周期内，只保留优先级最高的任务。

```
示例:
卖家 seller_A 同时触发 P0 delivery_risk 和 P1 review_triage
→ 只创建 P0 delivery_risk，P1 合并到同一工单作为子项
```

---

## 2. 任务状态流转

```
待处理 (pending)
    ↓
    ├→ 处理中 (in_progress)
    │       ↓
    │       ├→ 已解决 (resolved)
    │       │       ↓ (7天后自动)
    │       │       已关闭 (closed)
    │       │
    │       └→ 升级 (escalated)
    │               ↓
    │               待处理 (pending) ← 重新指派给上级
    │
    └→ 忽略 (ignored)
            ↓ (需填写忽略原因)
           已关闭 (closed)
```

### 2.1 SLA 时限

| 优先级 | 响应时限 | 解决时限 | 超时升级 |
|--------|----------|----------|----------|
| P0 | 4 小时 | 24 小时 | 自动升级至总监 |
| P1 | 24 小时 | 3 个工作日 | 自动升级至经理 |
| P2 | 3 个工作日 | 2 周 | 加入超时报告 |
| P3 | 无 | 无 | 无 |

---

## 3. 任务模板

### 3.1 delivery_risk 模板

```
任务标题: [物流风险] {seller_id} 延迟率 {delay_rate_pct}%
任务内容:
  - 卖家: {seller_id} ({seller_city}, {seller_state})
  - 延迟率: {delay_rate_pct}%
  - 平均延迟: {avg_delivery_delay_days} 天
  - 总订单: {total_orders}
  - 关联数据: orders_enriched WHERE seller_id = ...
  - SOP 参考: SOP-DELIVERY-001 §1.2
```

### 3.2 review_triage 模板

```
任务标题: [差评风险] {seller_id} 差评率 {low_review_rate_pct}%
任务内容:
  - 卖家: {seller_id}
  - 差评率: {low_review_rate_pct}%
  - 平均评分: {avg_review_score}
  - 差评总数: {negative_reviews}
  - 最新差评内容: (来自 order_reviews, LIMIT 3)
  - SOP 参考: SOP-REVIEW-002 §1.2
```

### 3.3 quality_inspection 模板

```
任务标题: [质量风险] {product_id} 缺陷率 {defect_rate_pct}%
任务内容:
  - 商品: {product_id} ({product_category_name})
  - 缺陷率: {defect_rate_pct}%
  - 平均评分: {avg_review_score}
  - 平均单价: R$ {avg_unit_price}
  - SOP 参考: SOP-PRODUCT-003 §1.2
```

---

## 4. 任务归档与统计

### 4.1 月度统计维度

- 任务创建数（按类型、按优先级）
- 任务解决率（按 SLA 时限）
- 平均解决时间（按类型）
- 升级率（P0/P1 超时未解决占比）
- 复现率（同一卖家 30 天内重复触发同类任务）

### 4.2 季度复盘

每季度对 SOP 阈值进行校准：
- 如果某个阈值的触发率 > 20%（过度敏感），考虑放宽
- 如果某个阈值的触发率 < 1%（过于宽松），考虑收紧
- 阈值调整需运营总监审批
