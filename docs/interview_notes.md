# YuanJiang OpsGuard — Interview Notes

## 项目概述（30 秒电梯演讲）

YuanJiang OpsGuard 是一个**本地优先的电商运营巡检 Agent**。
它使用本地 Ollama DeepSeek-R1 模型，结合 Olist 公开电商数据和企业巡检 SOP，
自动识别卖家履约风险、物流延迟、差评趋势和订单异常，
并生成可追踪的巡检任务。整个系统运行在一台笔记本上，不需要任何云端 API。

## 技术亮点

### 1. 全本地 LLM 推理（隐私 + 成本）

- 运行时零 API 调用：Ollama DeepSeek-R1:8b 完全本地推理
- 所有电商数据（订单、客户、评价）不出本机
- Claude 子 Agent 只参与开发/测试，不参与运行时推理

### 2. LangGraph 条件路由（不是链式调用）

- 5 条意图路由：sop_qa / metric_query / create_task / mixed / unknown
- mixed 自动链式调用：查数据 → 检索 SOP → 创建任务 → 汇总答案
- 图结构可观测：每一步的输入/输出都有日志

### 3. SQL 安全三道防线

- 单语句强制（拒绝 `SELECT ...; DROP TABLE`）
- SELECT-only 白名单（拒绝 INSERT/UPDATE/DELETE）
- 表名白名单（14 个允许表/视图，拒绝任意表名）

### 4. FTS5 全文检索 + BM25（零外部依赖）

- 无需下载嵌入模型（省 500MB+ 磁盘）
- 无需 GPU（纯 CPU SQLite 查询）
- 3 阶段查询回退：AND → OR → LIKE

### 5. 文档管道：Docling → PyMuPDF4LLM 降级

- Docling 保留表格、阅读顺序、章节层级
- 降级到 PyMuPDF4LLM 继续工作（不崩溃）
- 每个 chunk 带 6 项 metadata（source/section/page/content_type/element_id）

## 面试常见问题

### Q1: 为什么选择 LangGraph 而不是 LangChain AgentExecutor？

**Answer**: LangGraph 提供了显式的状态图控制。我需要在分类、查数据、检索 SOP、创建任务之间做条件路由。
AgentExecutor 把路由隐藏在内部，无法做 human-in-the-loop 或中间结果注入。
LangGraph 的 conditional edges 让我可以在图中插入检查点（如"数据是否满足创建任务的阈值"），这是一个纯粹的 ReAct 循环做不到的。

### Q2: 如何保证 LLM 生成的 SQL 不会破坏数据库？

**Answer**: 三道防线。第一层 sqlglot AST 解析，只允许单条 SELECT 语句。
第二层语句类型检查，拒绝 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE 六种危险操作。
第三层表名白名单，只允许 14 个预定义的表和视图。
DuckDB 连接还加了 `read_only=True`。四层防御，LLM 不可能执行写操作。

### Q3: 为什么用 FTS5/BM25 而不是向量模型？

**Answer**: 三个原因。数据规模小（4 份 SOP，~40 个 chunks），BM25 已经足够精确。
冷启动快（不需要加载嵌入模型，0ms vs 3-10s）。
零外部依赖（SQLite FTS5 是 Python 标准库的一部分，clone 后不用 pip install 额外的东西就能跑测试）。
当 SOP 文档数量超过 500 时，再考虑引入向量检索做 hybrid search。

### Q4: 本项目与 ChatGPT + RAG 有什么区别？

**Answer**: 三个核心区别：
1. **完全本地**：所有数据不离开本机。电商订单数据涉及客户隐私，本地推理是合规前提。
2. **工具闭环**：不是只回答问题，而是"查数据 → 匹配 SOP → 创建可追踪任务"的完整运营闭环。
3. **安全架构**：LLM 只操作 JSON 查询计划，SQL 永远是预编译的查询函数生成的，不直接执行 LLM 的输出。

### Q5: 混合查询的难点在哪？

**Answer**: 用户说"查卖家 A 延迟率，超 30% 就建 P0 任务"——
这需要 Agent 先查数据、再读 SOP 阈值、再判断是否满足创建条件、最后创建任务。
LangGraph 的条件路由解决了"要不要继续下一步"的判断：
`route_after_metrics` 检查 `_should_create_task()`，
如果数据返回 P0/P1 且 query 包含"创建"关键词，才进入 task 节点。
没有这个判断，Agent 会对所有 mixed 请求都创建任务。

### Q6: 183 个测试覆盖了什么？

**Answer**:
- `test_data_schema.py` (11): DuckDB 建库和视图
- `test_ecommerce_metrics.py` (22): 风险指标计算和权重
- `test_sql_guard.py` (29): SQL 安全校验（安全/危险/边界）
- `test_doc_convert.py` (18): 文档转换和 metadata
- `test_sop_retrieval.py` (14): chunker + FTS 索引 + 检索器
- `test_sop_answer.py` (7): 溯源回答 + 拒答 + 失败处理
- `test_inspection_tools.py` (23): Pydantic + 持久化 + 工具函数
- `test_ollama_config.py` (8): Ollama 配置
- `test_output_cleaner.py` (23): R1 输出清洗 + JSON 提取
- `test_yuanjiang_graph.py` (28): LangGraph 工作流 + 6 个端到端用例

## 架构图

```
Streamlit UI
    │
    ▼
LangGraph (7 nodes, conditional routing)
    ├── classify_intent → intent
    ├── plan_query       → JSON plan
    ├── run_metric_tool  → DuckDB data
    ├── retrieve_sop     → FTS5/BM25 chunks
    ├── create_task      → YJ-YYYYMMDD-NNNN
    ├── ask_clarify      → help message
    └── final_answer     → synthesized response
```

## 技术栈

| Layer | Technology | Why |
|-------|-----------|-----|
| LLM | Ollama + DeepSeek-R1:8b | Local-only, no API cost |
| Workflow | LangGraph | Conditional routing, state graph |
| Data | DuckDB + Pandas | OLAP on Olist (9 tables, 100k orders) |
| SQL Security | sqlglot | AST validation, 3-layer defense |
| Documents | Docling → PyMuPDF4LLM | Reading order + table structure |
| Retrieval | SQLite FTS5 + BM25 | Zero deps, sub-ms latency |
| Tools | Pydantic | Schema validation + OpenAI function calling |
| UI | Streamlit | Internal ops workbench, thin display layer |
| Testing | pytest | 183 tests, < 10s full suite |

## 关键数字

- **183** 个测试，零回归
- **11** 个语义化 commit
- **23** 个源文件，5 个模块
- **32** 条评估问题
- **93.8%** 意图识别准确率
- **100%** 工具调用成功率
- **87.5%** SOP 检索命中率
