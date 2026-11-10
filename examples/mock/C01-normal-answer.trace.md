# Trace：我每周可以远程办公几天？

- 模式：`offline_mock`　模型：`mock-policy`　知识库：`data/kb`
- 最终状态：**answered**
- 统计：模型调用 3 轮，业务工具 2 次，闸门退回 0 次，耗时 0 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "我每周可以远程办公几天？", "top_k": 5} | “我每周可以远程办公几天？” 命中 5 条：D05#s2 第二条 远程办公天数(现行)；D05#s3 第三条 申请流程(现行)；D05#s1 第一条 适用人员(现行)；D08#s1 技巧一 快速剪辑(现行) | [mock] 先用问题原文检索 | read_section |
| 2 | 2 | read_section | {"doc_id": "D05", "section_id": "s2"} | D05#s2（现行）第二条 远程办公天数：经部门负责人批准，员工每周最多可远程办公 2 天。 | [mock] 读取高分命中的原文 | finish |
| 3 | 3 | finish | {"status": "answered"} | 闸门通过，状态 answered，有效引用 1 条 | [mock] 依据已读原文回答 | （结束） |

## 最终输出

```json
{
  "status": "answered",
  "answer": "经部门负责人批准，员工每周最多可远程办公 2 天。",
  "citations": [
    {
      "doc_id": "D05",
      "section_id": "s2",
      "title": "远程办公制度",
      "section_title": "第二条 远程办公天数",
      "version_date": "2024-06-01",
      "doc_status": "现行",
      "quote": "经部门负责人批准，员工每周最多可远程办公 2 天"
    }
  ],
  "conflicts": [],
  "gaps": [],
  "clarifying_question": null
}
```
