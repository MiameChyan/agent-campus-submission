# Trace：我每周可以远程办公几天？

- 模式：`offline_mock`　模型：`mock-policy`　知识库：`data/kb`　故障注入：`search:always,browse:always,outline:always,read_section:always`
- 最终状态：**tool_error**
- 统计：模型调用 3 轮，业务工具 2 次，闸门退回 0 次，耗时 0 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "我每周可以远程办公几天？", "top_k": 5} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 1 次调用） | [mock] 先用问题原文检索 | search |
| 2 | 2 | search | {"query": "我每周可以远程办公几天？", "top_k": 5} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 2 次调用） | [mock] 检索失败一次，按建议重试 | finish |
| 3 | 3 | finish | {"status": "tool_error"} | 闸门通过，状态 tool_error，有效引用 0 条 | [mock] 检索连续失败两次，停止并报告 | （结束） |

## 最终输出

```json
{
  "status": "tool_error",
  "answer": "检索服务连续失败，暂时无法回答该问题，请稍后重试。",
  "citations": [],
  "conflicts": [],
  "gaps": [
    "search 工具连续两次失败"
  ],
  "clarifying_question": null
}
```
