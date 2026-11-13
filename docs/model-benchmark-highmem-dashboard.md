# 高配环境模型测试看板

状态文件：[高配测试状态快照](model-benchmark-highmem-state.json)  
测试计划：[高配测试计划](model-benchmark-highmem-plan.md)

该看板用于 Apple M5 MacBook Air、32 GiB 统一内存环境，测试 8B（不含）以上至 70B（含）的本地翻译模型。模型按队列顺序下载；下载阶段允许并行预取，但进入模型推理时会暂停下载，避免下载 I/O 和网络活动影响 TPS、延迟与内存采样。每个模型完成测试并清理后才进入下一个模型的推理阶段。

本页由测试驱动定期刷新；GitHub 上的静态页面是最近一次提交的快照，本机实时状态以 `dashboard-state.json` 和测试日志为准。队列运行器使用独立缓存、原子状态写入和锁；下载采用 Ollama 结构化流，推理前响应关闭，测试期间 `download_paused=true`。
