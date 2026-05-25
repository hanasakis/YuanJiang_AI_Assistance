---
name: dataset-curator
description: >
  Download, verify, and document external datasets used by YuanJiang OpsGuard.
  Handles Kaggle-based Olist dataset acquisition, integrity checks, and
  license tracking.
---

# Dataset Curator

## Description

Guided workflow for acquiring the Olist Brazilian E-Commerce dataset (or any
future dataset) safely and reproducibly. Ensures every dataset has a recorded
source URL, license, and SHA256 checksum before ingestion.

## 适用场景

- 首次获取 Olist 数据集（9 CSV files, ~120 MB）
- 更新到新版本数据集
- 添加新的第三方数据集（如物流承运商 SLA 参考表）
- 验证已有数据集的完整性

## 输入

- 数据集名称或 Kaggle dataset slug（默认: `olistbr/brazilian-ecommerce`）
- 目标目录（默认: `data/raw/`）

## 输出

- `data/raw/*.csv` — 原始数据文件（gitignored）
- `data/raw/MANIFEST.json` — 数据集元信息：
  ```json
  {
    "name": "olist-brazilian-ecommerce",
    "source": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
    "license": "CC BY-NC-SA 4.0",
    "download_date": "2026-05-25",
    "version": "v9",
    "files": [
      {"name": "olist_orders_dataset.csv", "sha256": "...", "rows": 99441, "cols": 8}
    ]
  }
  ```
- `data/sample/olist_sample.parquet` — 1% 分层抽样（可提交，用于测试）

## 执行步骤

1. **确认下载源**
   - 检查 Kaggle CLI 是否已安装 (`kaggle --version`)
   - 如未安装，引导用户安装: `pip install kaggle`
   - 确认 `~/.kaggle/kaggle.json` 已配置

2. **下载**
   ```
   kaggle datasets download olistbr/brazilian-ecommerce -p data/raw/
   unzip data/raw/brazilian-ecommerce.zip -d data/raw/
   rm data/raw/brazilian-ecommerce.zip
   ```

3. **校验**
   - 计算每个 CSV 的 SHA256
   - 验证文件数量（预期 9 个 CSV）
   - 检查行数是否在预期范围内（orders: ~99k, reviews: ~100k）

4. **记录来源**
   - 写入 `data/raw/MANIFEST.json`（包含 license 字段）
   - **禁止跳过 license 记录** — 没有 license 的数据集不能进入 pipeline

5. **创建样本**
   - 从每张表分层抽样 1%
   - 导出为 `data/sample/olist_sample.parquet`
   - 样本可提交到 git（用于测试）

6. **生成数据字典初稿**
   - 扫描每张表的列名和类型
   - 输出到 `docs/data_dictionary.md` 初稿

## 禁止事项

- 禁止提交 `data/raw/` 到 git
- 禁止在没有 license 记录的情况下使用数据集
- 禁止修改原始 CSV 文件（只读，清洗走 `data/processed/`）
- 禁止使用 `curl`/`wget` 直接下载（走 Kaggle CLI 或 Python SDK）
- 禁止在 `MANIFEST.json` 中伪造 SHA256 或行数
