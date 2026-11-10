# Trace：报销期限多久？

- 模式：`offline_mock`　模型：`mock-policy`　知识库：`data/kb`
- 最终状态：**conflict_needs_confirmation**
- 统计：模型调用 3 轮，业务工具 3 次，闸门退回 0 次，耗时 0 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "报销期限多久？", "top_k": 5} | “报销期限多久？” 命中 5 条：D01#s3 第三条 报销期限(现行)；D02#s1 一、提交期限(现行)；D02#s2 二、电子发票(现行)；D01#s2 第二条 单据要求(现行) | [mock] 先用问题原文检索 | read_section |
| 2 | 2 | read_section | {"doc_id": "D01", "section_id": "s3"} | D01#s3（现行）第三条 报销期限：员工应在费用发生之日起 30 天内提交报销申请，逾期提交须由部门负责人书面说明原因。 | [mock] 读取高分命中的原文 | read_section |
| 3 | 2 | read_section | {"doc_id": "D02", "section_id": "s1"} | D02#s1（现行）一、提交期限：为加快财务结算，员工报销申请应在费用发生后 15 天内提交。 | [mock] 读取高分命中的原文 | finish |
| 4 | 3 | finish | {"status": "conflict_needs_confirmation"} | 闸门通过，状态 conflict_needs_confirmation，有效引用 2 条 | [mock] 两份现行文档数值不同，列出冲突 | （结束） |

## 最终输出

```json
{
  "status": "conflict_needs_confirmation",
  "answer": "资料存在冲突：D01 与 D02 的规定不一致，请确认适用哪份制度。",
  "citations": [
    {
      "doc_id": "D01",
      "section_id": "s3",
      "title": "费用报销制度",
      "section_title": "第三条 报销期限",
      "version_date": "2024-03-01",
      "doc_status": "现行",
      "quote": "员工应在费用发生之日起 30 天内提交报销申请，逾期提交须由部门负责人书面说明原因"
    },
    {
      "doc_id": "D02",
      "section_id": "s1",
      "title": "报销管理补充通知",
      "section_title": "一、提交期限",
      "version_date": "2025-01-10",
      "doc_status": "现行",
      "quote": "为加快财务结算，员工报销申请应在费用发生后 15 天内提交"
    }
  ],
  "conflicts": [
    {
      "description": "两份现行文档给出的天数不同",
      "doc_ids": [
        "D01",
        "D02"
      ]
    }
  ],
  "gaps": [
    "未找到两份文档的优先级或适用范围说明"
  ],
  "clarifying_question": null
}
```
