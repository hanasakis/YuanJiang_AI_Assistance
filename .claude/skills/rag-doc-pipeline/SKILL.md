---
name: rag-doc-pipeline
description: >
  Convert SOP documents (PDF/Markdown/TXT) into chunked, indexed, retrievable
  text for the RAG layer. Uses Docling as primary parser; falls back to
  PyMuPDF4LLM on failure.
---

# RAG Document Pipeline

## Description

End-to-end document processing pipeline for YuanJiang OpsGuard's SOP knowledge
base. Ingests inspection SOPs, converts them to structured markdown, chunks
by semantic boundaries, indexes with FTS5/BM25, and writes the retrieval
index to `data/fts/`.

## 适用场景

- 导入新的巡检 SOP 文档（PDF/Markdown/TXT）
- 更新已有 SOP 后重建索引
- 批量导入多个部门 SOP（如物流部 + 客服部）
- 诊断检索质量问题（重建索引、调整切片参数）

## 输入

- `docs/sop/*.md` / `*.pdf` / `*.txt` — 巡检 SOP 文档
- 切片策略参数（默认: 按 `##` 标题边界，min 200 chars，max 2000 chars）

## 输出

- `data/fts/` — FTS5 全文索引
- `data/bm25/` — BM25 稀疏检索索引
- `docs/document_index.json` — 切片索引（含 metadata）
- `docs/pipeline_report.json` — 处理报告：
  ```json
  {
    "total_docs": 5,
    "total_chunks": 47,
    "avg_chunk_len": 642,
    "parser_used": {"docling": 4, "pymupdf4llm": 1},
    "fallback_triggered": true,
    "errors": []
  }
  ```

## 执行步骤

1. **扫描文档**
   - 遍历 `docs/sop/`，列出所有 `.md` `.pdf` `.txt`
   - 生成文件清单，确认每个文件的可读性

2. **解析文档（Docling 优先）**
   ```
   for each doc:
       try:
           result = docling.convert(file)  # 主路径
       except DoclingError:
           result = pymupdf4llm.convert(file)  # 降级路径
           log.warning(f"Docling failed for {file}, using PyMuPDF4LLM")
   ```
   - **Docling** 是首选：支持表格保留、阅读顺序检测、文档布局理解
   - **PyMuPDF4LLM** 是后备：纯文本提取，丢失表格结构但仍可检索
   - 降级事件写入 `pipeline_report.json`

3. **Markdown 清洗**
   - 移除页码、页眉/页脚重复内容
   - 规范化空白符和换行
   - 修复编码乱码

4. **语义切片**
   - 按 `##`（H2）标题边界切分
   - 最小切片: 200 chars（过短合并到下一片）
   - 最大切片: 2000 chars（超长按句子边界拆分，保留 10% 重叠）
   - 每个切片提取 metadata: `source` `section` `page` `content_type`

5. **构建 FTS5 索引**
   - 写入 SQLite FTS5 表
   - 支持 `MATCH` 全文搜索
   - 支持 `bm25()` 排序

6. **构建 BM25 索引**
   - 使用 rank-bm25 或自研
   - 保存为 pickle（`data/bm25/index.pkl`）

7. **生成切片索引文件**
   - 写入 `docs/document_index.json`
   - 每个切片的 chunk_id、metadata、前 100 字符预览

8. **验证**
   - 用 3 条已知查询测试检索结果
   - 确认 Top-5 结果包含预期段落

## 禁止事项

- 禁止跳过 Docling 直接使用 PyMuPDF4LLM（必须尝试 Docling 失败后才降级）
- 禁止丢失切片 metadata（source, section, page, content_type 缺一不可）
- 禁止在句子中间切断（切片边界只能落在句号/换行/标题处）
- 禁止使用云端 API 做文档解析（如 OpenAI vision、Google Doc AI）
- 禁止超过 2000 chars 的单一切片（会撑爆上下文窗口）
