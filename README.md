# Solution Advisor · PPT解析与项目画像流水线

将项目介绍类 PPT 自动转换为结构化画像与 RAG 知识库，支持端到端渲染、抽取、总结与问答。

> 项目类型：AI / Tool / CLI  
> 主要语言：Python 3.9+  
> 技术栈：LibreOffice、Poppler、Chroma、LLM（可 mock）、FastAPI/CLI（内部）  
> 目标用户：Developers / Internal Teams

---

## 徽章（可选）
![License](https://img.shields.io/badge/license-Private-blue)
![Build](https://img.shields.io/badge/build-passing-brightgreen)
![Status](https://img.shields.io/badge/status-active-success)

---

## 目录
- [功能特性](#功能特性)
- [架构 / 设计概览](#架构--设计概览)
- [前置条件](#前置条件)
- [安装](#安装)
- [配置](#配置)
- [使用示例](#使用示例)
- [项目结构](#项目结构)
- [开发指南](#开发指南)
- [测试](#测试)
- [部署（如适用）](#部署如适用)
- [路线图（可选）](#路线图可选)
- [贡献指南](#贡献指南)
- [许可证](#许可证)
- [维护者 / 联系方式](#维护者--联系方式)

---

## 功能特性
- 一键处理 PPT：渲染 → 文本提取 → 单页总结 → 项目画像 → manifest
- 针对内部项目画像的 RAG 知识库生成与检索
- 可切换 LLM 提供商，支持 `LLM_PROVIDER=mock` 离线调试
- 与 LibreOffice / Poppler 集成的可移植渲染链路
- CLI 入口便于批处理，QA CLI 支持带护栏的问答

---

## 架构 / 设计概览
- 核心组件：`renderer/libreoffice.py`（渲染）、`extractor/ppt_extractor.py`（文本抽取）、`summarizer/`（LLM 总结）、`rag.py` & `pipeline.py`（编排与 RAG 文档生成）
- 接口层：`python -m src` CLI；`src/scripts/qa_cli.py` 提供问答接口
- 数据与存储：本地文件系统 + `chroma_db/` 向量库
- 扩展点：LLM 客户端、召回与重排参数、pipeline 配置、输出 manifest

详见 `docs/` 下的实施方案与设计文档。

---

## 前置条件
- Python 3.9+
- LibreOffice（提供 `soffice` 可执行）
- Poppler（提供 `pdftoppm`）
- 可选：真实 LLM Key（无则使用 `LLM_PROVIDER=mock`）

---

## 安装
```bash
# 克隆仓库
git clone https://github.com/your-org/solution_advisor.git
cd solution_advisor

# 安装依赖（示例）
pip install -r requirements.txt
```

安装 LibreOffice / Poppler（PPT 渲染必需）：
- Windows：安装 LibreOffice，确保 `soffice.exe` 在 PATH；安装 Poppler for Windows，将 `pdftoppm.exe` 所在目录加入 PATH。
- macOS：`brew install --cask libreoffice`，`brew install poppler`
- Linux：`apt/yum install libreoffice`，`apt/yum install poppler-utils`
验证：
```bash
soffice --headless --version
pdftoppm -h | head -n 1
```
如未在 PATH，可在 `.env` 中设置绝对路径（详见“配置”）。

---

## 配置
- 复制示例环境：`.env.example -> .env`，填入 LLM 及路径配置
- 复制模板配置：`config/settings.example.yaml -> config/settings.yaml` 并按需调整
- 确保 `soffice` 与 `pdftoppm` 在 PATH，或在 `.env` 中指定绝对路径

---

## 使用示例
```bash
# 运行主流水线（覆盖输出目录需加 --force）
python -m src --input ppts/ChatBI产品介绍_2025.pptx --output ppt_outputs/ChatBI产品介绍_2025 --force

# 运行问答 CLI（示例）
python -m src.scripts.qa_cli -q "ChatBI的核心功能是什么" --config config/settings.yaml
```

输出示例：
- `slides/001.png`…：渲染图片
- `page_summaries/001.json`…：单页总结
- `doc_summary/project_profile.json`：聚合画像
- `manifest.json`：元数据与错误记录
- `ppt_outputs/<ppt>/embeddings/rag_documents.json`：RAG 文档

---

## 项目结构
```bash
.
├─docs/                     # 需求、设计、方案文档
├─ppts/                     # 输入 PPT 资产
├─ppt_outputs/              # 渲染与总结产物（构建输出）
├─src/                      # 核心代码（pipeline、渲染、抽取、summarizer、QA）
├─tests/                    # 单元与端到端测试
├─config/                   # 配置模板与默认设置
└─venv/                     # 本地虚拟环境（可选）
```

---

## 开发指南
- 代码风格：PEP8；建议使用 `black`/`isort`（未强制）
- 提交规范：简短中文描述，例如“更新渲染异常处理”
- 分支策略：`main` 常备，功能分支 `feature/*`

---

## 测试
```bash
pytest
```
> 若缺少 LibreOffice/Poppler 或未配置 LLM，相关测试会自动跳过；可设置 `LLM_PROVIDER=mock` 以离线运行。

---

## 部署（如适用）
- 部署目标：本地/自托管服务器
- 交付方式：Python CLI；可封装为容器镜像（自行添加 Dockerfile）
- 关键参数：`.env`、`config/settings.yaml` 中的路径与 LLM 配置

---

## 路线图（可选）
- [ ] 完善 Docker 化与一键安装脚本
- [ ] 增强多模型策略与重排参数自动调优
- [ ] 增加可视化 Web 界面与任务队列

---

## 贡献指南
- 提交 PR 前请确保通过全部测试并更新相关文档
- 如需讨论新功能/问题，请先提交 Issue 或在内部渠道同步
- 代码评审由核心维护者轮值

---

## 许可证
本项目当前为内部使用，许可证：Private（未公开）。如需外部分发请先与维护者确认。

---

## 维护者 / 联系方式
- Owner：Solution Advisor 团队（internal）
- 协作渠道：企业微信/邮件（请在内网通讯录查找）

---

## 实施过程说明（通俗版，聚焦 RAG / Embedding）
从第一性原理出发，我们先把 PPT 拆成最小可验证的链路：渲染出图片、提取文本、做单页总结，再聚合成项目画像。所有这些中间结果最终落到一份统一的 RAG 嵌入文档 `embeddings/rag_documents.json`，这样后续检索和问答都不必重复解析 PPT。

嵌入文档分两层：每一页的标题、one-liner、要点、详情被拼成可搜索的语义文本，metadata 里写明页码、页面类型、实体标签；整份画像再生成一条项目级综述，标记为 `level=project`，用来覆盖全局问题。为减少噪声，发现 `details/bullets` 是嵌套 JSON 时会尝试解包，缺失字段用默认值补齐，避免空壳文档进入索引。所有生成数量、异常与回退都会写进 manifest，QA CLI 直接读取这些嵌入文档做检索与重排。

我们在内部问答集上对 `top_k / top_n / tau` 以及相似度阈值（默认 0.5）做过一轮微调，实验结果存放在 `tmp_embedding_test_round1.json`，并将较优参数固化到 `ChromaStore.query_with_guardrails`，让默认体验开箱可用。

还在改进的方向包括：建立自动化的嵌入质量基线与回归；继续优化切分、去重和重排参数；补齐 Docker/一键安装、任务队列和可视化看板；扩充异常 PPT 样本，完善解包和告警回退，提升鲁棒性。

### Embedding 具体做法与模型选择
- 文本准备：对 slide/项目级文本先做轻量清洗、去空字段、解包嵌套 JSON，再按语义段落拼接，不做过度切碎，保持上下文完整以减少语义丢失。  
- 批量向量化：使用 `moka-ai/m3e-base`（768 维）本地推理，自动选择 CPU/CUDA/MPS，OOM 时自动降低 batch；首次运行自动下载并缓存模型。  
- 选择 M3E 的原因：中文语义效果稳定、模型体量适中（可本地离线）、社区基准表现良好；相比英文化模型，中文召回与断句更可靠；开源许可便于内网部署。  
- 向量库集成：向量生成后写入 Chroma，metadata 保留 `project_name/slide_no/page_type/level/confidence` 等字段，便于后续过滤与重排；同一流程可被 QA CLI 和向量库管理脚本共享。  
- 结果记录：Embedding 与插入耗时、成功/失败数写入 manifest，便于回溯；测试回归数据保存在 `tmp_embedding_test_round1.json` 以对比调参效果。
