# Trace：我每周可以远程办公几天？

- 模式：`live`　模型：`deepseek-flash`　知识库：`data/kb`　故障注入：`search:always,browse:always,outline:always,read_section:always`
- 最终状态：**tool_error**
- 统计：模型调用 6 轮，业务工具 7 次，闸门退回 0 次，耗时 11504 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "远程办公", "top_k": 8} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 1 次调用） | 用户问每周远程办公天数，先关键词检索相关制度 | search |
| 2 | 1 | search | {"query": "居家办公 每周 天数", "top_k": 8} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 2 次调用） | 换用制度原文可能出现的词再搜一次，避免同义词命中差 | browse |
| 3 | 2 | browse | {"path": ""} | 失败 ServiceUnavailable（可重试）：browse 服务暂时不可用（注入故障，第 1 次调用） | search 连续失败，改用 browse 从根目录定位可能含远程办公规定的文档 | browse |
| 4 | 3 | browse | {"path": ""} | 失败 ServiceUnavailable（可重试）：browse 服务暂时不可用（注入故障，第 2 次调用） | browse 首次失败为可重试故障，再试一次根目录以便定位制度文档 | search |
| 5 | 4 | search | {"query": "考勤 办公地点 弹性", "top_k": 5} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 3 次调用） | search 故障为可重试类型，换关键词再试以确认是否恢复 | browse |
| 6 | 4 | browse | {"path": "制度/人事"} | 失败 ServiceUnavailable（可重试）：browse 服务暂时不可用（注入故障，第 3 次调用） | browse 也可重试，直接猜人事目录以减少目录层级往返 | outline |
| 7 | 5 | outline | {"doc_id": "D01"} | 失败 ServiceUnavailable（可重试）：outline 服务暂时不可用（注入故障，第 1 次调用） | search/browse 均不可用，试探 outline 是否可用；若可用至少能拿到文档元数据 | finish |
| 8 | 6 | finish | {"status": "tool_error"} | 闸门通过，状态 tool_error，有效引用 0 条 | 检索与浏览工具连续多轮不可用，无法取得任何原文证据，按规则以 tool_error 结束并说明缺口 | （结束） |

## 最终输出

```json
{
  "status": "tool_error",
  "answer": "暂时无法回答：知识库检索工具当前全部不可用，我未能读取任何制度原文，因此不能给出「每周可远程办公几天」的可靠答案。\n\n已尝试的手段与结果：\n- search（关键词「远程办公」「居家办公 每周 天数」「考勤 办公地点 弹性」）：3 次均返回 ServiceUnavailable；\n- browse（根目录、制度/人事）：3 次均返回 ServiceUnavailable；\n- outline（探测文档服务）：1 次返回 ServiceUnavailable。\n\n建议稍后重试，或直接告知我远程办公制度的文档名称/文档 ID，我再用 read_section 读取原文答复。请勿以未经验证的口径作为依据。",
  "citations": [],
  "conflicts": [],
  "gaps": [
    "知识库 search / browse / outline 三类工具连续故障（ServiceUnavailable），未能定位或读取远程办公相关制度小节",
    "无法确认远程办公制度是否存在、其版本与适用范围，也无法确认每周远程天数上限及审批要求"
  ],
  "clarifying_question": null
}
```
