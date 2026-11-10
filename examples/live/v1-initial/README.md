# 归档：v1（初版）真实模型运行记录

这里保存的是第一次外部评审之前的运行记录，用于追溯，不代表最终版本的表现。最终版本的结果见 [examples/live/](../report.md)。本目录下的报告都已**按当前（v4）断言重新判定**，没有重跑模型。

| 内容 | 按 v4 断言重新判定 | 说明 |
|---|---|---|
| `C*.output.json` / `C*.trace.md`，[report.md](report.md) | 9/11 | C02、C04 的答案含“在确认前，按较严格的 15 天准备提交”这类替用户选边的建议 |
| [stability/](stability/report.md) | 3/9 | C02、C04 共 6 次运行全部含有类似的选边建议；C10 的 3 次全部通过 |
| [regression-plugins/](regression-plugins/report.md) | 10/11 | 完成检索可插拔、多模型适配、工具插件化之后的回归；C04 未区分“发票”与“报销申请” |

用当前闸门离线回放（`python scripts/replay_gate.py examples/live/v1-initial`）还会发现：C09 和回归中的 C05 / C09 提到了旧版 D03 的“5 天”却没有引用 D03，这 3 份在当前版本中会被闸门退回。（回放中途一度还拦下了稳定性第 2 次的 C02，原因是答案里的“唯一年限”被中文数字换算误读成“1 年”，属于闸门误伤，已随 v3 → v4 的修正一起解决。）

版本变化与原因见 [docs/03-evaluation.md](../../../docs/03-evaluation.md) 第 4 节。
