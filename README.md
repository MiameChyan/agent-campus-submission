# 企业知识问答 Agent（小影校招 · 第 3 题）

本项目是小影科技 2027 校招 AI Agent 笔试的提交作品，选题为第 3 题“企业知识问答 Agent”。它帮助员工从公司制度与产品资料中找到有出处的答案：由模型自己决定检索、浏览目录、查看文档版本、阅读原文、追问还是结束，每个结论都附上文档编号、小节和逐字原文。遇到资料冲突时，它会先核查版本、适用范围和替代关系；查得清就按现行制度回答，查不清就列出冲突，请用户确认，不会自行选一个答案。

**决策由真实模型驱动（DeepSeek 官方 `deepseek-flash`，即 V4.1 Flash），评测结果见 `examples/live/`。知识库为合成数据，“星剪 App”是虚构产品。离线 Mock 模式只用于验证流程，不代表真实模型的决策效果。**

## 快速运行

环境：Python 3.12（开发与测试环境为 3.12.7 / Windows 11）；网页演示另外需要 Node.js 20.19+。以下命令都在仓库根目录执行。

安装依赖：

```bash
pip install -r requirements.txt
```

复制配置文件，然后在 `.env` 中填写 `DEEPSEEK_API_KEY`（只跑离线 Mock 时可以不填）。Windows 的 cmd 下请用 `copy` 代替 `cp`：

```bash
cp .env.example .env
```

**1. 离线验证（不需要密钥）**：运行自动化测试，并用 Mock 模型跑全部用例。

```bash
python -m pytest -q
python scripts/run_eval.py --mode mock
```

**2. 真实模型**：单个问题、单个用例、全部用例。

```bash
python -m src.main --question "报销期限多久？"
python -m src.main --input examples/cases/C02-doc-conflict.input.json --output out.json --trace-md trace.md
python scripts/run_eval.py --mode live --out-dir out/live
```

**3. 审核要点演示**：替换文档（使用去掉 D02 的变体知识库）、模拟工具失败、调低执行上限。

```bash
python -m src.main --question "报销期限多久？" --kb no_conflict
python -m src.main --question "我每周可以远程办公几天？" --fail search:always
python -m src.main --question "报销期限多久？" --max-llm-turns 1
```

**4. 网页对话界面（可选）**：先启动后端，再在另一个终端启动前端，然后打开 http://localhost:5173 。

```bash
uvicorn src.server:app --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

**运行说明**

- 命令行把最终结果以 JSON 输出到标准输出，把每一步的动作、参数、返回摘要和决策依据输出到标准错误。
- 结果中的 `status` 表示任务状态：`answered`、`conflict_needs_confirmation`、`need_clarification`、`out_of_scope`、`tool_error`、`incomplete`、`model_error`、`cancelled`，含义见[需求说明](docs/01-requirements.md)。
- 业务结果（包括失败和未完成）的退出码都是 0；输入文件或知识库不合法时，退出码为 2。
- 常用参数：`--mock` 离线运行、`--kb` 切换知识库、`--fail` 模拟工具故障、`--provider` / `--model` 切换模型、`--retriever` 切换检索方式（`bm25` / `vector` / `hybrid`）、`--max-llm-turns` / `--max-tool-calls` 调整执行上限。完整说明见 `python -m src.main --help`，全部配置项见 [.env.example](.env.example)。
- `scripts/run_eval.py --mode live` 不加 `--out-dir` 时会覆盖 `examples/live/` 中提交的原始记录，复核时建议指定其他目录。

## 项目目录

```text
.
├── README.md                         # 环境、安装、运行、评审入口
├── requirements.txt                  # Python 依赖（pymilvus 为可选）
├── .env.example                      # 配置项模板，不含真实密钥
├── pytest.ini
├── src/
│   ├── main.py                       # 命令行入口
│   ├── server.py                     # HTTP 接口：逐步推送执行过程，支持停止
│   ├── config.py                     # 读取 .env 与默认值
│   ├── evaluation.py                 # 用例断言
│   ├── agent/                        # 主循环、状态栏、提交闸门（引用校验）、提示词、执行记录
│   ├── tools/                        # 核心工具（计划、追问、提交）、插件机制、故障模拟
│   │   └── plugins/                  # 业务工具插件：检索、浏览目录、查看大纲、读原文（可热加载）
│   ├── kb/                           # 知识库加载与校验
│   │   └── retrievers/               # 可插拔检索：BM25、向量（内存 / Milvus）、混合
│   └── llm/                          # 模型提供方配置、通用适配器、离线 Mock 模型
├── data/
│   ├── kb/                           # 合成知识库：8 篇制度与产品文档
│   └── kb_variants/no_conflict/      # 去掉 D02 的变体库，用于“替换文档”演示
├── frontend/                         # 网页对话界面（React + TypeScript）
├── scripts/
│   ├── run_eval.py                   # 批量运行用例并按预期自动判定
│   └── stability.py                  # 关键用例重复运行
├── tests/                            # 88 个自动化测试
├── examples/
│   ├── cases/                        # 11 个用例的输入与预期
│   ├── live/                         # 真实模型的输出、执行记录与评测报告
│   │   ├── stability/                # 稳定性复跑
│   │   └── regression-plugins/       # 扩展改造后的回归评测
│   ├── mock/                         # 离线 Mock 的输出与报告
│   └── test-results.txt              # 自动化测试的实际输出
└── docs/
    ├── 01-requirements.md            # 用户、目标、范围和成功标准
    ├── 02-solution.md                # 调用流程、动态决策、技术取舍、可扩展性
    ├── 03-evaluation.md              # 测试预期、实际结果、失败和限制
    ├── 04-ai-usage.md                # AI 辅助内容、个人修改及验证
    └── 05-retrospective.md           # 最难问题、学习收获、下一步
```

## 评审导航

| 检查项 | 入口 |
|---|---|
| 业务目标、范围、任务状态定义 | [需求说明](docs/01-requirements.md) |
| 调用流程、动态决策、技术取舍 | [方案设计](docs/02-solution.md) |
| 不同工具结果下的两条执行路径 | [C02 冲突待确认](examples/live/C02-doc-conflict.trace.md)、[C08 替换文档后直接回答](examples/live/C08-kb-replaced.trace.md)、[C06a 检索失败后改用目录浏览](examples/live/C06a-tool-failure-switch.trace.md) |
| 测试预期、实际结果、失败与限制 | [测试与评估](docs/03-evaluation.md) |
| 真实模型评测（11/11 通过） | [评测报告](examples/live/report.md) |
| 关键用例稳定性（9/9 通过） | [稳定性复跑报告](examples/live/stability/report.md) |
| 扩展改造后的回归（11/11 通过） | [回归评测报告](examples/live/regression-plugins/report.md) |
| 离线 Mock（只证明流程） | [Mock 评测报告](examples/mock/report.md) |
| 用例输入与预期 | [用例目录](examples/cases/) |
| 自动化测试（88/88 通过） | [测试记录](examples/test-results.txt) |
| 检索可插拔、多模型适配、工具热加载 | [方案设计 · 可扩展性](docs/02-solution.md#可扩展性) |
| 知识库格式与新增文档 | [方案设计 · 知识库格式](docs/02-solution.md#知识库格式与新增文档) |
| AI 辅助边界 | [AI 使用说明](docs/04-ai-usage.md) |
| 不足、实际用时与下一步 | [复盘](docs/05-retrospective.md) |

题目的 6 个验收点与用例的对应关系：

| 验收点 | 用例 | 真实模型的表现 |
|---|---|---|
| 明确答案 | C01、C08 | 引用远程办公制度、报销制度回答 |
| 文档冲突 | C02、C09 | 报销期限冲突时请求确认，不擅自回答 15 天；年假新旧版本冲突时查到替代关系，按 2025 版回答 |
| 资料外问题 | C03 | 返回超出资料范围，不用常识补全 |
| 改写后的相似问题 | C04 | 改写检索词并查证后，结论与 C02 一致 |
| 上下文追问 | C05 | 结合上一轮对话，回答“满 10 年 12 天” |
| 工具失败 | C06a、C06b | 检索失败时改用目录浏览完成；全部工具失败时如实返回失败 |

另有 C07（执行上限）、C08（替换文档）、C10（文档中的注入文本）三个补充用例。每个用例的输入、真实输出和逐步执行记录都在 `examples/` 下。

## 提交约定

- 题号：第 3 题 企业知识问答 Agent。所有代码、文档、合成数据与运行结果都在本仓库中。
- 仓库不含真实密钥：`.env` 已被 git 忽略，`.env.example` 只列出变量名。知识库为合成数据，不含真实业务或个人信息。
- `examples/live/` 是真实模型的运行记录；`examples/mock/` 是离线 Mock 的结果，不能作为模型效果的依据。
- 除 DeepSeek 外的模型提供方、真实 embedding 服务与 Milvus 只完成了适配和单元测试，没有在真实环境中评测，详见[测试与评估](docs/03-evaluation.md)。
- AI 辅助的范围、个人修改与验证方式见 [AI 使用说明](docs/04-ai-usage.md)；实际用时与未完成部分见[复盘](docs/05-retrospective.md)。
