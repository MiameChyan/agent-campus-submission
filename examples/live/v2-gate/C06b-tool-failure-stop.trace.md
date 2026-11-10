# Trace：我每周可以远程办公几天？

- 模式：`live`　模型：`deepseek-flash`　知识库：`data/kb`　故障注入：`search:always,browse:always,outline:always,read_section:always`
- 最终状态：**tool_error**
- 统计：模型调用 6 轮，业务工具 8 次，闸门退回 0 次，耗时 12740 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "远程办公", "top_k": 8} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 1 次调用） | 直接检索“远程办公”关键词，找相关制度 | search |
| 2 | 1 | search | {"query": "居家办公 天数 每周", "top_k": 8} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 2 次调用） | 换用制度原文可能出现的“居家办公”等词补充检索 | browse |
| 3 | 2 | browse | {"path": ""} | 失败 ServiceUnavailable（可重试）：browse 服务暂时不可用（注入故障，第 1 次调用） | search 连续失败，改用目录浏览定位考勤/办公方式相关制度 | browse |
| 4 | 3 | browse | {"path": ""} | 失败 ServiceUnavailable（可重试）：browse 服务暂时不可用（注入故障，第 2 次调用） | browse 首次失败为可重试故障，重试根目录浏览 | search |
| 5 | 3 | search | {"query": "远程办公 居家", "top_k": 8} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 3 次调用） | search 前次为可重试故障，换关键词重试 | browse |
| 6 | 4 | browse | {"path": "制度/人事"} | 失败 ServiceUnavailable（可重试）：browse 服务暂时不可用（注入故障，第 3 次调用） | 确认 browse 服务是否整体不可用，尝试定位人事制度目录 | search |
| 7 | 4 | search | {"query": "考勤", "top_k": 5} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 4 次调用） | 换更基础的“考勤”关键词，测试 search 是否恢复 | search |
| 8 | 5 | search | {"query": "灵活办公 办公地点 申请", "top_k": 5} | 失败 ServiceUnavailable（可重试）：search 服务暂时不可用（注入故障，第 5 次调用） | 最后一次探测 search 是否恢复，避免仅因短暂故障就放弃作答 | finish |
| 9 | 6 | finish | {"status": "tool_error"} | 闸门通过，状态 tool_error，有效引用 0 条 | 检索与浏览服务持续故障，无法取得任何原文证据，按 tool_error 结束并说明缺口，避免凭常识编造天数。 | （结束） |

## 最终输出

```json
{
  "status": "tool_error",
  "answer": "抱歉，暂时无法回答「每周可远程办公几天」这个问题：本次检索工具故障，未能取得任何制度原文，因此不能给出天数结论（也不应凭常识推断）。\n\n已尝试的动作：\n- search 关键词检索 5 次（「远程办公」「居家办公 天数 每周」「远程办公 居家」「考勤」「灵活办公 办公地点 申请」），全部返回 ServiceUnavailable；\n- browse 目录浏览 3 次（根目录 2 次、制度/人事 1 次），同样返回 ServiceUnavailable。\n\n目前状态：知识库中与远程办公/居家办公相关的制度（含版本、状态、适用范围）尚未读取到任何内容，无法判断是否存在可远程办公的天数规定，也无法查证多份制度间的版本或替代关系。\n\n建议：待检索服务恢复后重试；如你已知相关制度的名称或文档 ID（例如人事类考勤/灵活办公制度），告诉我可直接定位读取，确认后我再给出带原文引用的答案。",
  "citations": [],
  "conflicts": [],
  "gaps": [
    "检索与浏览工具（search×5、browse×3）全部因 ServiceUnavailable 失败，未能读取任何制度原文，远程办公天数规定未知。",
    "未确认公司是否存在远程/居家办公制度，以及其版本、状态（有效/已废止）与适用范围。",
    "需要用户提供相关制度名称或文档 ID，或待服务恢复后重试检索。"
  ],
  "clarifying_question": null
}
```
