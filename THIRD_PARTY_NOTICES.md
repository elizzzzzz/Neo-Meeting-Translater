# Third-party notices / 第三方说明

The Apache-2.0 license in this repository covers NMT's original work. It does not replace the licenses of third-party software, models, system resources or evaluation data. This file describes that boundary; it is not an exhaustive license inventory of a frozen binary's transitive dependencies.

本仓库的 Apache-2.0 许可证适用于 NMT 原创成果，不替代第三方软件、模型、系统资源与评估数据的许可证。本文说明授权范围，不作为已打包二进制全部间接依赖的完整许可证清单。

## Software and models / 软件与模型

- Python and native dependencies are declared in [pyproject.toml](pyproject.toml); their own distribution licenses and notices continue to apply. Redistributors must preserve the notices required by the actual versions they distribute.
- Apple SpeechAnalyzer and its language resources are provided and managed by Apple under Apple's terms.
- Ollama, llama.app, SGLang, BlackHole and Loopback are separate projects or products; mentioning or integrating with them does not grant their rights under NMT's license.
- Speech-recognition and translation model weights are not included in the repository or App release. Downloading, using, modifying or distributing a model is subject to that model's license, including any attribution or commercial-use conditions.

Python 和原生依赖的版本范围见 `pyproject.toml`，再分发时仍需保留实际分发版本要求的许可证与声明。Apple 系统资源、外部推理服务和音频驱动遵循各自条款。模型不随 NMT 分发；商用部署应同时核对选定模型与依赖的授权条件。

## Evaluation materials / 评估材料

Historical evaluations reference external datasets. Original recordings, full reference transcripts and model weights are not included in the repository or release packages. Any identifiable dataset-derived excerpts or outputs retain their source material's applicable terms rather than being relicensed by this repository.

- **AISHELL-4**: AISHELL contributors; [OpenSLR 111](https://www.openslr.org/111/) and [official dataset](https://huggingface.co/datasets/AISHELL/AISHELL-4). The evaluation records identify the license as **CC BY-SA 4.0**.
- **YODAS2**: Xinjian Li and co-authors, ESPnet, and the original Creative Commons video creators; [dataset](https://huggingface.co/datasets/espnet/yodas2). The evaluation records identify the license as **CC BY 3.0**, with revision and sample identifiers recorded in the manifests.

Source identifiers, attribution, transformations and measurement limits are documented in [the evaluation report](docs/asr-evaluation-0.2.4.md) and [the evaluation manifest](docs/evaluations/streaming-0.2.4.json). Refer to these records and the original providers before reusing evaluation material.

历史评估中的来源、署名、数据标识、处理步骤及限制见上述报告与清单。引用的数据片段或输出仍适用来源材料的相应条款，不因仓库采用 Apache-2.0 而重新授权；复用前请核对原始提供方的许可。

## Names and affiliation / 名称与关系

Product names belong to their respective owners. NMT is an independent project; references to third-party products do not imply endorsement or affiliation.

产品名称归其权利人所有。NMT 为独立项目，提及或接入第三方产品不代表官方合作或背书。
