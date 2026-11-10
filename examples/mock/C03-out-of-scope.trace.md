# Trace：公司的股票期权怎么行权？

- 模式：`offline_mock`　模型：`mock-policy`　知识库：`data/kb`
- 最终状态：**out_of_scope**
- 统计：模型调用 2 轮，业务工具 1 次，闸门退回 0 次，耗时 0 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "公司的股票期权怎么行权？", "top_k": 5} | “公司的股票期权怎么行权？” 无命中 | [mock] 先用问题原文检索 | finish |
| 2 | 2 | finish | {"status": "out_of_scope"} | 闸门通过，状态 out_of_scope，有效引用 0 条 | [mock] 检索无命中，判定为资料外问题 | （结束） |

## 最终输出

```json
{
  "status": "out_of_scope",
  "answer": "知识库中没有找到与该问题相关的资料，无法回答。",
  "citations": [],
  "conflicts": [],
  "gaps": [
    "知识库未覆盖：公司的股票期权怎么行权？"
  ],
  "clarifying_question": null
}
```
