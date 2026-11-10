# 企业知识问答 Agent（小影校招 AI Agent 笔试 · 第 3 题）

帮助员工从公司制度与产品资料中找到**有引用依据**的答案：模型自主决定检索、浏览目录、查看大纲、读取原文、追问或结束；资料冲突时先查证，查不清就列出冲突请求确认，而不是自行选一个答案。

- 模型：DeepSeek 官方接口 `deepseek-flash`（DeepSeek-V4.1-Flash，思考模式 + strict 工具调用）
- 知识库：层次型（Markdown 目录树，L0 目录摘要 / L1 文档大纲 / L2 小节原文），jieba + BM25 关键词检索，无向量库
- Agent：原生实现的 ReAct harness（状态栏、提交闸门、预算、故障注入、完整 trace），未使用 Agent 框架
- 评审主入口：**CLI**；另有 FastAPI（SSE）+ React 对话式界面（类似 ChatGPT / DeepSeek）作为演示入口
- 结果：真实模型 11/11 用例通过（[报告](examples/live/report.md)），关键用例复跑 9/9 通过（[报告](examples/live/stability/report.md)），57 个自动化测试通过（[记录](examples/test-results.txt)）

## 快速运行

Python 3.10+（开发环境 3.12.7，Windows 11）。在仓库根目录执行：

```bash
pip install -r requirements.txt
cp .env.example .env          # 填写 DEEPSEEK_API_KEY；离线 Mock 不需要
```

```bash
# 1) 离线（无需密钥，只验证流程）：测试 + Mock 跑全部用例
python -m pytest -q
python scripts/run_eval.py --mode mock

# 2) 真实模型：单个问题 / 单个用例 / 全部用例
python -m src.main --question "报销期限多久？"
python -m src.main --input examples/cases/C02-doc-conflict.input.json --output out.json --trace-md trace.md
python scripts/run_eval.py --mode live

# 3) 审核要点演示：替换文档（换成去掉 D02 的变体库）、注入工具故障、调小预算
python -m src.main --question "报销期限多久？" --kb no_conflict
python -m src.main --question "我每周可以远程办公几天？" --fail search:always
python -m src.main --question "报销期限多久？" --max-llm-turns 1

# 4) 知识库校验（修改或新增 .md 后运行）
python -m src.kb.check
```

CLI 把结果 JSON 打印到标准输出，把每一步（动作、参数、返回摘要、决策依据）打印到标准错误。业务结果（包括失败和未完成）都以 JSON 状态返回，退出码为 0；输入或知识库非法时退出码为 2。

**可选：前后端演示**（需要 Node 20.19+；React 19 + TypeScript + react-router + zustand + Vite 8）

```bash
uvicorn src.server:app --port 8000                     # 后端
cd frontend && npm install && npm run dev              # 前端 http://localhost:5173
```

## 评审导航

| 检查项 | 入口 |
|---|---|
| 需求、范围、成功标准 | [需求说明](docs/01-requirements.md) |
| 调用流程、动态决策、技术取舍（含放弃向量检索的原因） | [方案设计](docs/02-solution.md) |
| 测试预期、实际结果、失败与限制 | [测试与评估](docs/03-evaluation.md) |
| AI 辅助范围、个人修改与验证 | [AI 使用说明](docs/04-ai-usage.md) |
| 最难问题、收获、下一步 | [复盘](docs/05-retrospective.md) |
| 真实模型运行记录（输出 + trace） | [真实模型评测报告](examples/live/report.md) |
| 关键用例稳定性复跑 | [稳定性复跑报告](examples/live/stability/report.md) |
| 离线 Mock 运行记录（只证明流程） | [Mock 评测报告](examples/mock/report.md) |
| 用例输入与预期 | [用例目录](examples/cases/) |
| 自动化测试实际输出 | [测试记录](examples/test-results.txt) |

### 6 个验收点对应的用例

| 验收点 | 用例 | 真实模型结果 |
|---|---|---|
| 明确答案 | C01、C08 | `answered`，引用 D05 / D01 |
| 文档冲突 | C02（D01 写 30 天，D02 写 15 天）；C09（D07 替代 D03，可查证） | C02 `conflict_needs_confirmation`，不擅自回答；C09 依据 D07 回答 |
| 资料外问题 | C03 | `out_of_scope` |
| 改写后的相似问题 | C04 | 改写检索词并查证后，与 C02 结论一致 |
| 上下文追问 | C05 | 结合历史回答“满 10 年 12 天” |
| 工具失败 | C06a / C06b | search 故障时改用目录浏览完成；全部故障时返回 `tool_error` |
| 执行上限 / 替换文档 / 注入 | C07 / C08 / C10 | `incomplete` / 答案随知识库改变 / 未执行注入指令 |

## 项目目录

```text
.
├── README.md
├── requirements.txt / .env.example / pytest.ini
├── src/
│   ├── main.py              # CLI 入口
│   ├── server.py            # FastAPI：/api/ask（SSE）、/api/kb/tree
│   ├── config.py            # .env 与默认值
│   ├── evaluation.py        # 用例断言
│   ├── agent/               # harness 主循环、status_bar 状态栏、gate 提交闸门、prompts、state、trace
│   ├── tools/               # 工具定义（strict schema）、注册表、故障注入
│   ├── kb/                  # 知识库加载与校验、BM25 检索、check 命令
│   └── llm/                 # DeepSeek 接入、离线 MockLLM、测试用 ScriptedLLM
├── data/
│   ├── kb/                  # 合成知识库（8 篇文档，制度/财务、人事、行政；产品/星剪App）
│   └── kb_variants/no_conflict/   # 去掉 D02 的变体库
├── scripts/                 # run_eval.py 批量运行 + 断言 + 报告；stability.py 稳定性复跑
├── tests/                   # 57 个 pytest 测试
├── examples/
│   ├── cases/               # 11 个用例输入（expect 内嵌）
│   ├── live/                # 真实模型输出、trace、报告
│   ├── mock/                # 离线 Mock 输出、trace、报告
│   └── test-results.txt     # pytest 实际输出
├── frontend/                # React 对话界面：侧栏对话列表 / 可折叠检索过程 / 引用卡片 / 可停止
└── docs/01~05
```

## 如何新增一篇文档

知识导入默认已经完成：本项目不解析 PDF/Word，也不自动生成摘要。新增文档时，按下面的模板写 Markdown，放进对应目录，再运行 `python -m src.kb.check`。下次运行时自动生效，没有需要重建的索引文件。

```markdown
---
doc_id: D09                  # 唯一，形如 D01
title: 文档标题
version_date: 2026-01-01     # YYYY-MM-DD
status: 现行                  # 现行 / 已废止
scope: 适用范围（没有就写“未注明”）
supersedes: []               # 本文替代的文档
superseded_by: null          # 被哪篇替代（需与对方的 supersedes 一致）
links: []                    # 相关文档
abstract: 一句话摘要（L0）
---
## 第一条 小节标题
小节原文……
```

## 提交信息与边界

- 题号：第 3 题 企业知识问答 Agent
- 知识库全部为合成数据，“星剪 App”是虚构产品；仓库中不含真实密钥。
- Mock 模式只证明流程可运行，不代表真实模型的决策效果。真实模型效果以 `examples/live/` 为准。
- 实际用时与未完成部分见 [复盘](docs/05-retrospective.md)。
