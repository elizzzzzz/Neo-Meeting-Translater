# M5 / 32 GiB 冻结证据：2026-11-19

这是[32 GB MacBook 模型选型参考表](../../model-benchmark-2026-11-19-m5-32gb.md)的可核验快照。采集完毕不等于质量通过；当前 39/40 项文字采集完整，7项已完成144题质量评审入榜，32项未完整评审配置排除。

| 文件 | 用途 |
|---|---|
| [configuration-metrics.csv](configuration-metrics.csv) / [JSON](configuration-metrics.json) | 全部 40 项状态、TPS、整句延迟、P95、内存有效性、截断提示、评审覆盖与模态线索 |
| [environment.json](environment.json) | 机器、运行时版本与测量边界 |
| [model-sources.json](model-sources.json) | GGUF manifest / capability 元数据，MLX 仓库标识与清理状态 |
| [cases.jsonl](cases.jsonl) / [scenes.json](scenes.json) / [corpus.sha256.json](corpus.sha256.json) | 冻结的 144 题、参考译文、原子事实和语料哈希 |
| [outputs.jsonl](outputs.jsonl) | 5,616 条最终采集输出与计时的可读合并版，按 configuration + case_id 关联语料 |
| [raw-evidence.zip](raw-evidence.zip) / [source-audit.json](source-audit.json) | 原样保留每配置 outputs、summary、conditions、memory 文件及 SHA256；包括先前失败行和重试内存样本 |
| [annotations.jsonl](annotations.jsonl) / [progress.json](progress.json) | 1,584条逐项评审及覆盖进度；仅7项配置评审齐全 |
| [case-scores.csv](case-scores.csv) / [quality-ranking.csv](quality-ranking.csv) | 7项完整配置的1,008条逐题分数与综合排名 |
| [review-completion-scope.json](review-completion-scope.json) / [new-review-decisions.jsonl](new-review-decisions.jsonl) | 本次预选范围、454条新增隐藏标签题包及明确评分 |
| [reviewed-output-audit.json](reviewed-output-audit.json) / [critical-error-examples.json](critical-error-examples.json) | 完整覆盖审计与关键错误例句 |
| [direction-quality.json](direction-quality.json) / [register-quality.json](register-quality.json) | 六方向、正式与非正式场景分数 |
| [ranking.json](ranking.json) | 7项完整配置的综合排名；其余32项已评/未评数量 |
| [measurement-invalidations.json](measurement-invalidations.json) | Qwen2.5 14B Q4 两后端 RSS/swap/available 作废原因；原始错误值仍在 ZIP 的 summary 中，仅作审计 |
| [failures.json](failures.json) / [scope.json](scope.json) | Qwen3.6 / llama.cpp 失败与按资源策略排除的配置 |
| [queue-policy-20261115.md](queue-policy-20261115.md) | 当时的范围决策；其中“约4–5 TPS”的上界概括已被本报告的 MoE 53 TPS 实测更新，具体结论以本快照为准 |
| [collection-code/](collection-code/) / [运行时补丁](sglang-mlx-auxiliary-state-20261116.patch) | 采集、模板、评分与内存回退逻辑证据；不含运行环境或权重 |
| [SHA256SUMS.json](SHA256SUMS.json) / [verify.py](verify.py) | 发布文件完整性清单与离线校验器 |

所有速度均使用每道题最后记录的成功输出，部分配置跨断点重试。内存使用归档中全部保留样本的极值，包含先前失败/重试；原始 summary 的最终运行数值也保留在 JSON 的 `summary_run_*` 字段（作废配置留空）。RSS 不是独立 GPU 显存，swap 为整机值。P95 采用 nearest-rank，即排序后第 ceil(0.95×N) 项。

`outputs.jsonl` 保留原 prompt、response、thinking、计时与后端统计；完整原文件位于 ZIP。`source-audit.json` 中的路径均相对 ZIP 根目录。原样文件只含固定合成语料及运行记录，没有私人会议转写或模型权重。

`annotations.jsonl` 是标签隐藏的本助手辅助评审，含与 M3 研究逐题语料和译文完全一致时复用的记录；无独立人类译者复核。仅完整评审配置才可生成质量/综合分，本快照有7项这样的配置；其余32项不发布质量分。

源码按原研究布局引用兄弟目录；仅为审计，不是一键重跑包。`sglang_runner.py` 的本机 Python 与缓存绝对路径已换成示例路径，其余代码保留；原始与发布哈希及路径处理记录见 [provenance.json](collection-code/provenance.json)。离线校验器使用 Python 标准库，不启动模型、不联网：

```bash
python3 docs/benchmarks/2026-11-19-m5-32gb/verify.py
```

校验器检查所有文件哈希、ZIP 成员、逐题输出与原始日志一致性、冻结语料、速度重算、保留样本内存极值、无效采样留空，以及评审数量与身份关联。文件哈希用于发现快照损坏，不替代独立测量或人工译者复核。
