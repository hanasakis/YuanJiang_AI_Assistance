# Security Architecture — YuanJiang AI Assistance

## 概述

本项目使用**纵深防御**策略保护本地开发环境的安全。三层防线：

```
Layer 1: .gitignore          → 防止敏感文件进入版本控制
Layer 2: Permissions (应用层)  → 控制 Claude Code 工具调用边界
Layer 3: Sandbox (OS 层)      → 限制进程的文件系统访问范围
```

---

## 1. 权限模式（Permission Mode）

本项目使用 `default` 权限模式。规则链：

```
请求到达 → deny 表匹配? → ✗ REJECTED（不可恢复）
       → ask 表匹配?  → 弹窗询问用户 → 用户审批
       → allow 表匹配? → ✓ 静默放行
       → 无匹配       → 弹窗询问用户（等同于 ask）
```

### Deny（不可覆盖的禁止）

| 规则 | 原因 |
|------|------|
| `Read(**/.env)` | .env 可能包含真实 API 密钥 |
| `Read(data/raw/**)` | 原始 Olist 数据不应直接读入 LLM 上下文 |
| `Bash(curl *)` / `Bash(wget *)` | 防止 Agent 下载未审核的远程内容 |
| `Bash(git reset --hard *)` | 防止丢失未提交的工作 |
| `Bash(rm -rf *)` | 防止误删目录 |

### Ask（必须人工确认）

| 规则 | 原因 |
|------|------|
| `git commit` / `git push` | 每次提交必须人类审查 |
| `pip install` | 新依赖必须经过人类确认 |
| `docker` / `ollama` / `kaggle` | 涉及外部进程/网络的操作 |

### Allow（安全的自动化操作）

允许在 `src/`、`tests/`、`docs/`、`data/sample/`、`data/eval/`、`.claude/agents/` 内读写。

---

## 2. Sandbox

### 当前状态：已启用

`settings.json` 中 `"sandbox.enabled": true`。

### 操作系统支持情况

| 操作系统 | Sandbox 机制 | 状态 |
|----------|-------------|------|
| macOS | Seatbelt (App Sandbox) | 完整支持 |
| Linux (5.13+) | Landlock | 完整支持 |
| Windows | Job Objects | **部分支持** |

### Windows 降级策略

如果当前 Windows 环境不支持完整 sandbox：

1. **权限层补偿**：system-reminder deny 规则已在 settings.json 中配置为硬拒绝
2. **推荐 WSL2**：在 WSL2 中运行 Claude Code，获得完整 Linux Landlock sandbox
3. **推荐 Dev Container**：使用 `.devcontainer/` 配置获得容器级隔离
4. **手动审计**：每次 Agent 执行后，Sandbox Guard Agent 审计实际读写路径

降级确认后，在此文档中记录：

```
降级日期: ____
降级原因: Windows 不支持 Landlock/Seatbelt
补偿措施: deny 规则 + Sandbox Guard 审计
确认人: ____
```

---

## 3. Sandbox Guard Agent

**角色**：只读安全审计员，不写业务代码。

**触发时机**：
- 每个 Phase 开始前：评估权限模式是否足够
- 每个 Phase 结束 / commit 前：审计实际读写路径是否越界

**审计清单**（6 项）：
```
[ ] .gitignore 覆盖 data/raw/、data/chroma/、.env、__pycache__/
[ ] .env.example 无真实密钥/Token
[ ] 该阶段无外部 HTTP/API 调用（除 localhost:11434 Ollama）
[ ] 该阶段无 pip install 未审核的包
[ ] 文件写入不超出项目根目录
[ ] 该阶段不涉及密码/密钥硬编码
```

---

## 4. Git Guard Agent

**角色**：Commit 前置审查，不写业务代码。

**检查项**（8 项）：
```
[ ] 无敏感文件被暂存（.env、*.key、data/raw/*）
[ ] 无大文件（> 1MB）被暂存
[ ] 无 .pyc / __pycache__ 被暂存
[ ] 无临时文件被暂存
[ ] Commit message 格式规范
[ ] 所有测试通过
[ ] 无冲突标记
[ ] 无调试代码残留
```

---

## 5. settings.local.json 使用方式

**用途**：存放本机特有的配置，不提交到 git。

**示例**：
```json
{
  "env": {
    "OLLAMA_HOST": "http://192.168.1.100:11434"
  },
  "permissions": {
    "allow": [
      "Bash(python -m http.server *)"
    ]
  }
}
```

**注意事项**：
- `settings.local.json` 已在 `.gitignore` 中
- 它的 allow/ask/deny 与 settings.json 合并（local 优先级更高）
- 不要在 local 中放宽 settings.json 的 deny 规则 — 这会破坏安全基线
- 不要在 local 中存放真实 API key — 用 `.env`（也不提交）

---

## 6. 不可提交的文件类型

```
.env                   — 环境变量（可能含密钥）
.env.*                 — 所有环境变体
*.key / *.pem / *.p12  — 私钥和证书
credentials.*          — 凭证文件
secret.*               — 密钥文件
data/raw/              — 原始 Olist 数据集（约 120MB）
data/processed/        — 处理后的中间数据
data/chroma/           — 向量数据库持久化文件
models/                — 本地模型权重
.claude/settings.local.json — 本机 Claude 配置
```

---

## 7. 安全事件响应

如果怀疑 Agent 越权操作：

1. 检查 `.claude/audit/` 日志（如果启用）
2. 运行 `git diff --stat` 检查意外修改
3. 运行 Sandbox Guard Agent 审计清单
4. 检查 `pip list` 是否有未授权的包
5. 如果确认越权，回滚到上一个安全 commit
