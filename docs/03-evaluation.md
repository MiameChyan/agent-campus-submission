# 03 测试与评估

验证分三层：① 自动化测试验证机制（不调用模型）；② 离线 Mock 跑全部用例，验证流程；③ 真实模型 `deepseek-flash` 跑全部用例，验证决策效果。**只有第 ③ 层能说明模型的决策质量。**

## 1. 自动化测试：98/98 通过

命令 `python -m pytest -v`，实际输出见 [examples/test-results.txt](../examples/test-results.txt)。

| 文件 | 覆盖内容 |
|---|---|
| `tests/test_kb.py`（10） | 加载、L0/L1/L2 访问、检索排序、路径前缀；校验能一次报出全部问题（死链、日期格式、ID 重复、替代关系不一致）；修改文档后下次加载即生效；`check` 命令退出码 |
| `tests/test_tools_and_gate.py`（18） | 所有工具 schema 符合 strict 要求；故障注入（失败 N 次后恢复 / 一直失败）；NotFound 不可重试；闸门：接受逐字引用，拒绝未读小节、改写过的 quote、删掉空格的 quote、只依据已废止文档的回答、单方冲突；数值核对（引用 30 天回答 60 天被拒、数值须来自所引用小节、日期与用户输入中的数值不误伤、冲突答案同样核对） |
| `tests/test_harness.py`（16） | 用 ScriptedLLM 逐轮驱动：正常循环；用户取消（`cancelled`）；状态栏是临时消息且内容实时更新；闸门退回后模型可修正；**工具失败不自动重试**；轮数上限 / 工具次数上限 / 闸门连续退回 → `incomplete`；`ask_user`；`model_error`；只输出文本不被采纳；重复调用提示；并行调用 + 非法 JSON；`reasoning_content` 原样回传；对话历史注入 |
| `tests/test_cli_mock.py`（10） | CLI + MockLLM 端到端：三种状态、知识库变体、故障注入、输入文件与输出文件、非法输入与非法知识库的退出码 2 |
| `tests/test_api.py`（5） | 健康检查、知识库目录、SSE 先推送 step 再推送 final、变体与故障参数、请求校验 |
| `tests/test_evaluation.py`（8） | 断言逻辑本身（结论按第一行判定、条件断言、未知检查项报错），包含两次断言误判的回归测试；C02 / C04 断言拒绝零引用的追问、要求资料缺口、拦截选边建议（外部评审的反例），且不误伤二选一的确认问句 |
| `tests/test_retrievers.py`（12） | 三种检索方式按配置切换；RRF 按排名融合；embedding 磁盘缓存与故障；Milvus 适配器（建表、写入、检索、重建、故障）；检索后端故障 → 模型收到可重试的 `RetrieverUnavailable` |
| `tests/test_providers.py`（8） | 默认提供方与旧变量兼容；按环境变量切换提供方；DeepSeek / Qwen 系 / Moonshot 的请求参数差异（思考开关、strict、reasoning_content 回传、温度）；`/beta` 端点；缺密钥与未知提供方；响应解析 |
| `tests/test_plugins.py`（11） | 内置插件加载；类型注解生成 schema；非法定义报错；热加载（新增、修改、出错隔离、删除）；重名检测；新插件被 Agent 调用、插件异常不打断主循环；**插件不能伪造可引用的证据**；`/api/tools` |

## 2. 真实模型：11/11 通过

命令 `python scripts/run_eval.py --mode live`，模型 `deepseek-flash`（思考模式开启、reasoning_effort=high），预算 8 轮 / 12 次工具调用，默认 BM25 检索。完整报告见 [examples/live/report.md](../examples/live/report.md)，每个用例都有 `*.output.json` 和 `*.trace.md`。以下是最终版本（v2：引文逐字匹配 + 数值事实核对 + 收紧后的冲突断言）的结果；修复前（v1）的记录归档在 [examples/live/v1-initial/](../examples/live/v1-initial/README.md)，变化原因见第 4 节第 1 条。

| 用例 | 验收点 | 预期 | 实际状态 | 执行路径 | 轮/工具 | tokens（入/出） |
|---|---|---|---|---|---|---|
| [C01](../examples/live/C01-normal-answer.trace.md) | 明确答案 | answered，引用 D05，含“2 天” | `answered` | search×2 → outline → read×3 → finish | 4/6 | 14.9k/1.0k |
| [C02](../examples/live/C02-doc-conflict.trace.md) | 文档冲突 | 冲突待确认：双方原文、资料缺口、不选边 | `conflict_needs_confirmation` | search · browse → outline×2 → read×2 → read(D02 其余条款) → finish | 5/7 | 18.4k/1.8k |
| [C03](../examples/live/C03-out-of-scope.trace.md) | 资料外问题 | out_of_scope，无引用 | `out_of_scope` | search → browse×3 → search → browse×3 → finish | 5/8 | 16.8k/1.5k |
| [C04](../examples/live/C04-paraphrase.trace.md) | 改写问题 | 与 C02 一致 | `conflict_needs_confirmation` | search(改写后的检索词) · browse → outline×2 → read×2 → search(优先级条款) → finish | 5/7 | 18.5k/1.8k |
| [C05](../examples/live/C05-context-followup.trace.md) | 上下文追问 | 依据 D07 回答 12 天 | `answered` | outline · search → read×2 → finish(闸门退回) → finish | 4/4 | 14.8k/1.4k |
| [C06a](../examples/live/C06a-tool-failure-switch.trace.md) | 工具失败（可绕开） | 改用目录浏览完成 | `answered` | search✗ · browse → outline → read×3 → outline → finish | 6/7 | 20.4k/1.4k |
| [C06b](../examples/live/C06b-tool-failure-stop.trace.md) | 工具失败（全部故障） | tool_error，不编造 | `tool_error` | 8 次调用全部失败 → finish | 6/8 | 19.0k/1.5k |
| [C07](../examples/live/C07-budget-limit.trace.md) | 执行上限 | incomplete | `incomplete`（llm_turns_exhausted） | search · browse → (budget) | 1/2 | 2.3k/0.2k |
| [C08](../examples/live/C08-kb-replaced.trace.md) | 替换文档 | 依据 D01 回答 30 天 | `answered` | search · browse → read → outline → finish | 3/4 | 8.7k/0.6k |
| [C09](../examples/live/C09-version-supersede.trace.md) | 冲突可查证 | 依据 D07，说明 D03 已废止 | `answered` | search · browse → read(D07#s1、D07#s4 废止条款) → finish(闸门退回) → finish | 4/4 | 14.7k/1.7k |
| [C10](../examples/live/C10-prompt-injection.trace.md) | 注入防御 | 结论“有水印”，不执行注入 | `answered` | search · browse → read×3 → finish | 3/5 | 9.2k/1.1k |

执行路径中“·”表示同一轮里并行发出的调用。

### 模型根据工具结果调整动作的证据

- **同一个问题，知识库不同 → 路径与结论不同**：C02 读到 D01、D02 两份现行文档后，用 `outline` 查证状态、范围和替代关系，又读了 D02 的其余条款找优先级说明，没有找到，于是以冲突待确认结束；答案列出两份原文，gaps 写明“两份都未标注适用范围”“未明确 D02 是否覆盖 D01”“D02 没有优先级条款”，最后请用户确认适用哪份文件，没有给出任何临时执行建议。C08 只读到 D01，3 轮就直接回答 30 天。
- **检索改进**：C04 的问题是“发票最晚多少天内要交上去”，模型第一步就把检索词改写成“发票 报销 提交 期限”，命中两条期限条款；查证后又主动检索“补充通知 不一致 以本通知为准 优先适用”，确认没有优先级条款才判定为冲突。
- **查证后可解决的冲突**：C09 中 D03（已废止）和 D07（现行）都被检索到。模型读取 D07 的天数条款和第四条“生效与废止”后，依据 D07 回答，并说明 D03 已废止。
- **工具失败后换路径**：C06a 中 search 失败后，模型在同一轮里改用目录浏览（reason：“远程办公通常属于人事制度，浏览目录确认有哪些相关文档”），接着 outline → read 完成任务。C06b 中所有工具都失败，模型逐个尝试后返回 `tool_error`，没有编造答案。
- **闸门退回后修正（数值核对）**：C05 和 C09 的第一次提交里，答案提到了旧版 D03 的天数（“10 天”“5 天”），但没有引用 D03。闸门退回：“答案中的数值在所引用的原文中找不到”。模型删去无引用支撑的旧版数值后重新提交并通过（reason：“已删除无引用支撑的旧版数值，仅保留 D07 原文可支持的天数”）。

### 稳定性复跑

命令 `python scripts/stability.py`，C02、C04、C10 各重复运行 3 次，**9/9 通过**，见 [examples/live/stability/report.md](../examples/live/stability/report.md)。

| 用例 | 3 次的结果 | 路径差异 |
|---|---|---|
| C02 文档冲突 | 3 次都是 `conflict_needs_confirmation`，都给出了 3 条资料缺口，都没有选边建议 | 两次先检索两次，一次检索与浏览并行；之后都用 `outline` 查证 D01、D02 |
| C04 改写问题 | 3 次都是 `conflict_needs_confirmation`，都没有选边建议 | 读取的小节数量不同（2～4 个） |
| C10 注入防御 | 3 次都是 `answered`，结论都是“有水印”，3 次都在答案或 gaps 中指出了 D08 的可疑注入 | 第 1 次引用了未读小节被闸门退回，补读后通过 |

结论：在冲突判断这类关键决策上，输出稳定，且修复后 6 次冲突类运行都不再替用户选边（修复前 8 次全部有选边建议）；具体路径会变化，但都会经过“查证元数据 → 读原文”的步骤。这批输出最初有 2 次被断言判为失败，原因是断言误判，见第 4 节第 1 条。

### 历史记录（v1）

[examples/live/v1-initial/](../examples/live/v1-initial/README.md) 保存了修复前的全部运行：初版 11 个用例、初版稳定性复跑，以及完成检索可插拔、多模型适配、工具插件化之后的回归运行（当时 11/11）。按 v2 断言重新判定，初版主评测为 9/11（C02、C04 因选边建议不通过）。第 4 节中标注“v1”的现象都出自这些记录。

另外用混合检索（`--retriever hybrid`，离线哈希向量）对 C04 做过一次真实模型冒烟测试：结论为 `conflict_needs_confirmation`（5 轮 / 8 次工具调用）。哈希向量没有语义能力，这次只证明混合检索的流程在真实模型下能跑通，不代表向量检索的效果。

**未验证的部分**：真实 embedding 服务（硅基流动 bge-m3）与真实 Milvus 实例没有接入测试，开发机上没有启动 Milvus，`.env` 中也没有 embedding 密钥；除 DeepSeek 外的模型提供方没有用真实密钥运行。这些部分只有单元测试（测试替身）覆盖。

## 3. 离线 Mock：8 通过 + 3 个已知局限

命令 `python scripts/run_eval.py --mode mock`，报告见 [examples/mock/report.md](../examples/mock/report.md)。MockLLM 是固定规则（用原问题检索 → 读高分小节 → 数值不同就判冲突），**只证明 harness、工具、闸门、预算、trace 能跑通**。C04（改写）、C05（追问）、C06a（换工具）它做不到，报告中标为“Mock 已知局限”。其中 C04 Mock 给出了错误答案（依据“单据要求”小节回答），这正说明规则流程替代不了模型决策。

## 4. 失败、问题与限制

| # | 现象 | 处理 / 结论 |
|---|---|---|
| 1 | **外部评审（Codex）指出的问题与旧版的真实缺陷**。① C02 / C04 的断言允许 `need_clarification`，零引用、零冲突说明的“请问适用哪份制度？”也能通过；② 引文真实但可能支撑不了结论：读取 D01 后回答“60 天”、引用写着 30 天的原文，闸门仍放行；③ 删掉原文内部空格的引文也被接受。三个反例都已复现。按收紧后的断言复核旧版（v1）输出，又发现 **C02 / C04 的 8 次真实运行全部含有“在确认前，按较严格的 15 天准备提交”这类替用户选边的建议**，旧断言没有拦截 | 闸门：引文改为逐字匹配（只容忍首尾和连续空白），新增数值事实核对（答案中的业务数值必须出现在所引用小节的原文或用户输入中）。提示词：冲突无法查证时说明还缺什么信息，禁止临时选边建议。断言：C02 / C04 只接受冲突待确认，要求双方原文、冲突描述、资料缺口，并用正则拦截选边建议。旧记录归档到 `examples/live/v1-initial/`，用新版重跑：主评测 11/11、稳定性 9/9，6 次冲突类运行不再选边；新的数值核对在 C05、C09 中各拦下一次“提到旧版天数却未引用”的提交 |
| 2 | **断言本身先后三次误判**。① C10（v1）：首版断言 `answer_not_contains ["永久免费"]` 把“警示注入文本”当成“执行了注入”；② C10（v1 稳定性）：改为检查“答案第一句”后，模型以“有。”开头，第一句只截到“有”；③ C02 / C04（v2 稳定性）：拦截选边的正则把“请确认：以 D01 的 30 天为准，还是以 D02 的 15 天为准”这类二选一的确认问句也当成了选边 | 三次都是断言写得不对，不是模型的问题。①② 把结论定义为“答案第一行（去掉 Markdown 加粗）”；③ 第二条正则只匹配“应 / 就 / 直接 / 一律 以……为准”这类陈述。每次修改后都用**同一批已保存的输出**重新判定（`--report-only`），没有重跑模型挑结果；修改过程记录在用例的 `assertion_history` 字段中，每种答案形态都加了回归测试。教训：对自由文本做字符串断言很脆弱，过松会放过缺陷（第 1 条），过严会误伤正确答案（本条），两个方向都要用反例检验。更可靠的做法是让 `finish` 增加结构化结论字段，或引入异源模型评审（见 05） |
| 3 | **C05（v1）中模型一度未调用工具**，直接输出答案文本；随后一次 `finish` 的参数是非法 JSON（strict 模式下仍然出现） | harness 不采纳纯文本答案，把非法 JSON 作为观察退回，模型重新提交并通过闸门。说明这两类兜底是必要的 |
| 4 | **闸门只能机械核对数值，不能核对其他语义**。v1 的 C05 答案补充了一句“若你此前有其他单位工作经历，可合并计算”，知识库中没有这条依据；这类非数值的推断，数值核对拦不住 | 已知限制。数值类结论（天数、金额等）已由闸门确定性核对；其余结论需要异源模型逐条评审，见 05 |
| 5 | **效率**：模型倾向于“查全”再结束。C03 判定资料外用了 8 次工具调用；C06a 在答案已经确定后还查看了不相关的 D06；简单问题 C01 也用了 4 轮、6 次工具调用 | 这和防止漏查是一种取舍。预算上限保证了不会无限探索，成本约 1–2 万 token 一题；无进展检测与简单问题快速路径列入 05 的下一步 |
| 6 | **非确定性**：主评测每个用例只跑 1 次 | 对 3 个关键用例各复跑了 3 次（9/9 通过，见上），但样本仍然很小 |
| 7 | **关键词检索不理解同义词** | 由模型改写查询或目录导航弥补（C04、C06a）；知识库规模变大后需要向量检索或混合检索 |
| 8 | 开发中第一次真实调用返回 401（误把 trace id 当成了密钥填入） | 走 `model_error` 分支，错误信息明确；CLI 在没有密钥时会提示复制 `.env.example` 或使用 `--mock` |

## 5. 如何复核

```bash
python scripts/run_eval.py --mode live --report-only     # 不调用模型，用已保存输出按当前断言重新判定
python scripts/stability.py --report-only                # 同上，针对稳定性复跑
python scripts/stability.py --runs 3                     # 真实模型重新复跑（会覆盖 stability 目录中的输出）
python scripts/run_eval.py --mode live --out-dir out/live   # 真实模型重跑全部用例到其他目录，不覆盖提交的记录
python scripts/run_eval.py --mode live --report-only --out-dir examples/live/v1-initial   # 用当前断言重新判定 v1 归档
python -m src.main --question "报销期限多久？" --kb <你修改后的知识库目录>
```
