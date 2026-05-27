# YuanJiang OpsGuard

基于本地 Ollama DeepSeek-R1 的电商履约与卖家风险巡检 Agent。

## 业务背景

电商运营人员日常需要监控平台卖家：
- **履约异常**：订单延迟发货、超时未达、无故取消
- **物流风险**：承运商 SLA 偏离、偏远地区积压
- **差评聚类**：低分评价激增、关键词告警
- **卖家分层**：高风险卖家自动识别与巡检任务生成

传统方式依赖人工查表、经验判断，效率低且容易遗漏。OpsGuard 将巡检 SOP 文档化为知识库，结合 Olist 公开电商数据，由本地 LLM 自动执行巡检推理与任务创建。

## 数据集

[Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
（约 120 MB，9 张 CSV 表，覆盖 100k+ 订单、3 年交易记录）

核心表：orders、order_items、products、sellers、customers、order_payments、order_reviews、geolocation、product_category_name_translation

## 核心功能

1. **自然语言巡检**：输入"检查上周物流延迟超过 3 天的卖家"，Agent 自动查询数据、匹配 SOP 规则、生成巡检报告
2. **风险自动分级**：P0（需立即处理）→ P3（观察），每级有明确的指标阈值和升级规则
3. **SOP 知识库**：巡检标准、阈值定义、处理流程全部存储在可检索的文档库中
4. **任务追踪**：每次巡检自动创建可追踪任务，支持状态流转（待处理 → 处理中 → 已解决）

## 技术栈

| 层 | 选型 | 用途 |
|---|---|---|
| LLM 推理 | Ollama + DeepSeek-R1:8b | 纯本地推理，无云端依赖 |
| 工作流引擎 | LangGraph | 有状态 Agent 循环（ReAct + 工具调用） |
| 数据分析 | DuckDB + Pandas | OLAP 查询、卖家指标计算 |
| SQL 安全 | sqlglot | 校验 LLM 生成的 SQL 再执行 |
| 文档解析 | Docling / PyMuPDF4LLM | PDF/Markdown SOP 转结构化文本 |
| 检索 | FTS5 / BM25 | 全文 + 关键词混合检索 |
| UI | Streamlit | 巡检对话界面 |
| 工具定义 | Pydantic | 巡检工具箱 schema 与参数校验 |

## 运行方式

```bash
# 1. 启动 Ollama（确保已拉取 DeepSeek-R1:8b）
ollama serve

# 2. 安装依赖
pip install -r requirements.txt

# 3. 准备数据（二选一）
#  a) Demo 模式：使用内置 sample 数据，无需下载
#  b) 完整模式：从 Kaggle 下载 Olist 数据集到 data/raw/

# 4. 构建 DuckDB 数据库（demo 模式使用 sample 数据）
python -m src.data_ops.build_duckdb

# 5. 构建 SOP 检索索引
python -c "from src.rag.fts_index import build_fts_index; build_fts_index()"

# 6. 启动运营工作台
streamlit run src/app/main.py
```

Demo 模式无需 Ollama 也能体验：侧边栏提供预设查询，展示指标查询、SOP 检索和任务创建流程。

## 项目结构

```
src/
├── app/          LangGraph 工作流 + Streamlit UI
├── llm/          Ollama 调用、prompt 模板、输出清洗
├── data_ops/     Olist 数据下载、DuckDB 指标计算、SQL 校验
├── rag/          文档转换、切片、混合检索、SOP 回答
├── tools/        巡检工具函数与 Pydantic schema
└── eval/         检索/工具/端到端质量评估
data/
├── raw/          原始 CSV（不提交）
├── processed/    清洗后中间数据（不提交）
├── sample/       小样本测试数据（可提交）
├── runtime/      运行时临时文件（不提交）
└── eval/         评估结果与黄金标准
docs/
├── sop/          巡检 SOP 文档（Markdown/PDF）
├── architecture.md
└── learning_notes.md
tests/            测试代码（镜像 src/）
```

## 安全约束

- 运行时模型：仅本地 Ollama DeepSeek-R1，无云端 LLM 调用
- 子 Agent（Claude）仅参与开发/审查/测试，不替代运行模型
- 详见 `docs/security.md`
