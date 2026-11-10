# Trace：报销期限多久？

- 模式：`offline_mock`　模型：`mock-policy`　知识库：`data/kb`
- 最终状态：**incomplete**（llm_turns_exhausted）
- 统计：模型调用 1 轮，业务工具 1 次，闸门退回 0 次，耗时 0 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "报销期限多久？", "top_k": 5} | “报销期限多久？” 命中 5 条：D01#s3 第三条 报销期限(现行)；D02#s1 一、提交期限(现行)；D02#s2 二、电子发票(现行)；D01#s2 第二条 单据要求(现行) | [mock] 先用问题原文检索 | (budget) |
| 2 | 1 | (budget) | {} | 模型调用轮数达到上限 1，以未完成状态结束 |  | （结束） |

## 最终输出

```json
{
  "status": "incomplete",
  "answer": "",
  "citations": [],
  "conflicts": [],
  "gaps": [
    "达到执行上限，任务未完成；以下为已收集但未形成结论的证据：无"
  ],
  "clarifying_question": null
}
```
