---
name: git-commit-guard
description: >
  Pre-commit safety checklist for YuanJiang OpsGuard. Blocks commits that contain
  .env files, real data, model weights, local indices, or runtime artifacts.
---

# Git Commit Guard

## Description

Automated pre-commit review that checks every staged file against the project's
security baseline. Runs before `git commit` to prevent accidental exposure of
secrets, large binaries, raw data, or local artifacts.

## 适用场景

- 每次 `git commit` 前自动触发
- 在合并 PR 前做最终检查
- 新手第一次提交时的安全教育

## 输入

- `git diff --staged --name-only` — 暂存文件列表
- `git diff --staged --stat` — 每个文件的变更行数
- 暂存文件的实际内容（用于扫描敏感模式）

## 输出

- **审查报告** — 8 项检查清单，每项 ✓ / ✗ / N/A
- **决策** — ✅ APPROVED / ⚠️ NEEDS FIX / ❌ BLOCKED

## 执行步骤

### 1. 敏感文件检查

扫描暂存文件列表，标记匹配以下模式的文件：

```
# 环境变量与密钥
.env
.env.*
*.key
*.pem
*.p12
*.pfx
credentials.*
secret.*
secrets/

# 真实数据
data/raw/*
data/processed/*
data/runtime/*

# 模型权重
*.pt
*.bin
*.safetensors
*.gguf
models/
vector_store/

# 本地索引
data/fts/*
data/bm25/*
*.index
*.idx
chroma/

# 日志
*.log
logs/

# IDE 临时文件
.vscode/
.idea/
*.swp
*.swo

# Python 编译产物
__pycache__/
*.pyc
*.pyo
```

**规则**: 以上任何文件被暂存 → ❌ BLOCKED，不可绕过。

### 2. 大文件检查

- 任何 > 1 MB 的文件被暂存 → ⚠️ NEEDS FIX
- 检查是否应该用 Git LFS 或 .gitignore

### 3. 敏感内容扫描

在暂存文件内容中搜索：

```
# API Key 模式
sk-[a-zA-Z0-9]{20,}
AIza[0-9A-Za-z_-]{35}
api_key\s*=\s*[\'"][^\'"]+[\'"]
access_token\s*=\s*[\'"][^\'"]+[\'"]

# IP 地址（可能是内部基础设施地址）
\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}

# 密码模式
password\s*=\s*[\'"][^\'"]{3,}[\'"]
```

**规则**: 命中 → ⚠️ NEEDS FIX（人工确认是否为测试 mock）

### 4. 冲突标记检查

搜索暂存文件内容：
```
<<<<<<<
=======
>>>>>>>
```

**规则**: 命中 → ❌ BLOCKED

### 5. 调试代码检查

搜索暂存文件内容：
```
breakpoint()
import pdb; pdb.set_trace()
console.log(
print(  # Python 文件中的裸 print（不含测试文件）
```

**规则**: 在非测试文件中命中 → ⚠️ NEEDS FIX

### 6. Commit Message 格式检查

- 必须匹配: `^(feat|fix|chore|docs|test|refactor|style|perf)(\(.+\))?: .+`
- 不能为空
- 不能包含 `WIP` `TEMP` `DEBUG`（除非是临时分支）

### 7. 测试状态关联

- 检查 Test Agent 最后一次报告
- 如果有失败测试 → ⚠️ NEEDS FIX

### 8. .gitignore 完整性检查

- 确认 `.gitignore` 包含本次暂存的所有敏感目录

## 8 项检查清单

```
[ ] 1. 无敏感文件被暂存 (.env, *.key, *.pem, credentials.*, data/raw/, secrets/)
[ ] 2. 无大文件 (> 1 MB) 被暂存
[ ] 3. 暂存内容无 API Key / Token / Password 硬编码
[ ] 4. 无冲突标记 (<<<<<<<, =======, >>>>>>>)
[ ] 5. 无调试代码残留 (breakpoint, pdb, console.log)
[ ] 6. Commit message 格式规范 (type: description)
[ ] 7. 所有测试通过 (关联 Test Agent 报告)
[ ] 8. .gitignore 覆盖了暂存的所有敏感文件类型
```

## 禁止事项

- 禁止在检查未通过时强行 commit（不允许 `--no-verify`）
- 禁止跳过任何一项检查
- 禁止修改业务代码来规避检查（本质是安全流程，不是 lint）
- 禁止将验证失败归因为"测试太严格"而删除测试
