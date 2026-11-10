# Trace：报销期限多久？

- 模式：`offline_mock`　模型：`mock-policy`　知识库：`data/kb_variants/no_conflict`
- 最终状态：**answered**
- 统计：模型调用 3 轮，业务工具 2 次，闸门退回 0 次，耗时 0 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "报销期限多久？", "top_k": 5} | “报销期限多久？” 命中 4 条：D01#s3 第三条 报销期限(现行)；D01#s2 第二条 单据要求(现行)；D01#s1 第一条 适用范围(现行)；D01#s4 第四条 审批流程(现行) | [mock] 先用问题原文检索 | read_section |
| 2 | 2 | read_section | {"doc_id": "D01", "section_id": "s3"} | D01#s3（现行）第三条 报销期限：员工应在费用发生之日起 30 天内提交报销申请，逾期提交须由部门负责人书面说明原因。 | [mock] 读取高分命中的原文 | finish |
| 3 | 3 | finish | {"status": "answered"} | 闸门通过，状态 answered，有效引用 1 条 | [mock] 依据已读原文回答 | （结束） |

## 最终输出

```json
{
  "status": "answered",
  "answer": "员工应在费用发生之日起 30 天内提交报销申请，逾期提交须由部门负责人书面说明原因。",
  "citations": [
    {
      "doc_id": "D01",
      "section_id": "s3",
      "title": "费用报销制度",
      "section_title": "第三条 报销期限",
      "version_date": "2024-03-01",
      "doc_status": "现行",
      "quote": "员工应在费用发生之日起 30 天内提交报销申请，逾期提交须由部门负责人书面说明原因"
    }
  ],
  "conflicts": [],
  "gaps": [],
  "clarifying_question": null
}
```
