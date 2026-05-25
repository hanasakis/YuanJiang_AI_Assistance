---
name: interview-coach
description: >
  Convert each completed YuanJiang OpsGuard module into interview-ready
  explanations. Generates structured Q&A covering architecture decisions,
  code-level details, and system design trade-offs.
---

# Interview Coach

## Description

After each module is committed, read the real source code, tests, and commit
history, then generate interview-style Q&A that a candidate might face when
explaining this project on their resume. Every answer is grounded in real
code — no fabricated metrics or hypotheticals.

## 适用场景

- 每个模块 commit 后自动触发
- 准备技术面试前复习项目
- 为团队新人编写 onboarding 材料

## 输入

- 模块 source code（`src/<module>/`，只读）
- 模块 test code（`tests/`，只读）
- 最近一次 commit 的 diff
- Test Agent 的真实测试报告

## 输出

- `docs/interview/<module_name>.md` — 结构化面试问答

## 执行步骤

### 1. 提取核心概念

从源码中提取该模块的 3-5 个核心概念：

```
示例（llm 模块）:
- Ollama Python client 封装
- DeepSeek-R1 输出清洗（ 标签剥离）
- Token 预算管理
- System prompt 模板设计
```

### 2. 生成面试问题（3 层金字塔）

```
Q9-Q10: 架构设计 (Why)
  例: "为什么自建 Agent 循环而不直接使用 LangChain AgentExecutor？"
  答案要点: checkpointer、human-in-the-loop、routing control

Q5-Q8: 源码分析 (How)
  例: "DeepSeek-R1 的 标签如何处理？读取 src/llm/output_cleaner.py:23"
  答案要点: 正则提取、思维链与最终答案分离逻辑

Q1-Q4: 基础理解 (What)
  例: "为什么要用 DuckDB 而不是 SQLite？"
  答案要点: OLAP vs OLTP、列式存储、向量化执行
```

### 3. 验证答案可追溯性

每个参考答案必须满足：
- 至少引用 1 个真实文件:行号
- 至少引用 1 个真实的测试用例
- 设计决策引用 `docs/architecture.md` 相应段落

### 4. 添加延伸追问

每个问题后追加 1-2 个延伸追问：

```
Q5: "sqlglot 如何校验 LLM 生成的 SQL？"
  A: ...（主答案）
  追问 1: "如果 sqlglot 校验通过但 SQL 语义错误，怎么防御？"
  追问 2: "sqlglot 支持 DuckDB 方言吗？不支持怎么办？"
```

### 5. 格式输出

```markdown
# <模块名> — 面试问答

## 核心概念速览
| 概念 | 一句话 |
|------|--------|
| ... | ... |

## Q1-Q4: 基础理解
### Q1: <问题>
**参考答案**: ...
**源码验证**: `src/xxx.py:42-56`
**延伸追问**: ...

## Q5-Q8: 源码分析
...

## Q9-Q10: 架构设计
...

## 自测清单
- [ ] 能画出模块间数据流图
- [ ] 能解释每个设计决策的 trade-off
- [ ] 能手写核心函数的简化版
```

## 禁止事项

- 禁止编造性能数据（如"检索延迟从 500ms 降到 200ms"，除非 Test Agent 提供了真实基准）
- 禁止引用不存在的文件或行号
- 禁止伪造测试覆盖率
- 禁止跳过"难"的问题只写简单的（面试官不会）
- 禁止用"显然""众所周知""毫无疑问"等话术掩盖复杂的细节
