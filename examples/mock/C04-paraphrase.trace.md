# Trace：发票最晚多少天内要交上去？

- 模式：`offline_mock`　模型：`mock-policy`　知识库：`data/kb`
- 最终状态：**answered**
- 统计：模型调用 3 轮，业务工具 3 次，闸门退回 0 次，耗时 0 ms

| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |
|---|---|---|---|---|---|---|
| 1 | 1 | search | {"query": "发票最晚多少天内要交上去？", "top_k": 5} | “发票最晚多少天内要交上去？” 命中 2 条：D01#s2 第二条 单据要求(现行)；D02#s2 二、电子发票(现行) | [mock] 先用问题原文检索 | read_section |
| 2 | 2 | read_section | {"doc_id": "D01", "section_id": "s2"} | D01#s2（现行）第二条 单据要求：报销须提供合规发票或电子发票，发票抬头为公司全称，金额与实际支出一致；无发票的支出不予报销。 | [mock] 读取高分命中的原文 | read_section |
| 3 | 2 | read_section | {"doc_id": "D02", "section_id": "s2"} | D02#s2（现行）二、电子发票：自本通知发布之日起，优先使用电子发票报销；纸质发票须在背面注明报销人姓名。 | [mock] 读取高分命中的原文 | finish |
| 4 | 3 | finish | {"status": "answered"} | 闸门通过，状态 answered，有效引用 1 条 | [mock] 依据已读原文回答 | （结束） |

## 最终输出

```json
{
  "status": "answered",
  "answer": "报销须提供合规发票或电子发票，发票抬头为公司全称，金额与实际支出一致。",
  "citations": [
    {
      "doc_id": "D01",
      "section_id": "s2",
      "title": "费用报销制度",
      "section_title": "第二条 单据要求",
      "version_date": "2024-03-01",
      "doc_status": "现行",
      "quote": "报销须提供合规发票或电子发票，发票抬头为公司全称，金额与实际支出一致"
    }
  ],
  "conflicts": [],
  "gaps": [],
  "clarifying_question": null
}
```
