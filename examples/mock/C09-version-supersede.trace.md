# Trace：按现行制度，员工的年假有几天？

- 模式：`offline_mock`　模型：`mock-policy`　知识库：`data/kb`
- 最终状态：**answered**
- 统计：模型调用 3 轮，业务工具 3 次，闸门退回 0 次，耗时 0 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "按现行制度，员工的年假有几天？", "top_k": 5} | “按现行制度，员工的年假有几天？” 命中 5 条：D03#s1 第一条 年假天数(已废止)；D07#s1 第一条 年假天数(现行)；D08#s1 技巧一 快速剪辑(现行)；D07#s4 第四条 生效与废止(现行) | [mock] 先用问题原文检索 | read_section |
| 2 | 2 | read_section | {"doc_id": "D07", "section_id": "s1"} | D07#s1（现行）第一条 年假天数：员工累计工作满 1 年不满 10 年的，年假 7 天；满 10 年不满 20 年的，年假 12 天；… | [mock] 读取高分命中的原文 | read_section |
| 3 | 2 | read_section | {"doc_id": "D08", "section_id": "s1"} | D08#s1（现行）技巧一 快速剪辑：在时间线上双指捏合可以缩放片段，长按片段可以拖动调整顺序。 | [mock] 读取高分命中的原文 | finish |
| 4 | 3 | finish | {"status": "answered"} | 闸门通过，状态 answered，有效引用 1 条 | [mock] 依据已读原文回答 | （结束） |

## 最终输出

```json
{
  "status": "answered",
  "answer": "员工累计工作满 1 年不满 10 年的，年假 7 天。",
  "citations": [
    {
      "doc_id": "D07",
      "section_id": "s1",
      "title": "年假制度（2025 版）",
      "section_title": "第一条 年假天数",
      "version_date": "2025-01-01",
      "doc_status": "现行",
      "quote": "员工累计工作满 1 年不满 10 年的，年假 7 天"
    }
  ],
  "conflicts": [],
  "gaps": [],
  "clarifying_question": null
}
```
