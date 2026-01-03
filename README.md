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
- 一键处理 PPT：渲染 → 文本提取 → 单页总结 → 项目画像 → RAG 文档生成
- RAG v2 QA-pair 方案：自动生成问答对、LLM 分类、多类型 chunk（qa_pair/topic/step/metrics/overview）
- 向量检索与重排：M3E 中文 embedding + Chroma 向量库 + 相似度护栏（top_k/top_n/tau 可调）
- 多种交互方式：CLI 批处理、QA CLI 问答、Gradio Web UI 引导式对话
- 可切换 LLM 提供商，支持 `mock` 模式离线调试
- 与 LibreOffice / Poppler 集成的可移植渲染链路
- 监控与缓存：精确缓存（TTL 7 天）+ JSONL 日志记录

---

## 架构 / 设计概览
- 核心组件：
  - `renderer/libreoffice.py`：PPTX → PDF → PNG 两步渲染
  - `extractor/ppt_extractor.py`：文本与 speaker notes 抽取
  - `summarizer/`：单页总结 + 项目画像生成（LLM）
  - `rag/`：QA 对生成 → LLM 分类 → 多类型 chunk 生成（RAG v2）
  - `embeddings/m3e_model.py`：M3E 中文向量模型（768 维）
  - `vectordb/chroma_store.py`：Chroma 向量库封装 + 检索护栏
  - `qa/qa_engine.py`：RAG 检索 + LLM 生成 + 监控/缓存
  - `pipeline.py`：端到端编排
- 接口层：
  - `python -m src`：PPT 解析主流程 CLI
  - `src/scripts/qa_cli.py`：命令行问答
  - `src/scripts/qa_gradio.py`：Gradio Web UI（引导式对话）
  - `src/scripts/vectordb_cli.py`：向量库管理（导入/查询/统计/删除）
- 数据与存储：本地文件系统 + `chroma_db/` 向量库 + `logs/qa_sessions/` 日志
- 扩展点：LLM 客户端、RAG 开关（enable_llm_classify/enable_*_chunks）、召回与重排参数、prompt 模板

详见 `docs/` 下的实施方案与设计文档，以及各模块的 `AGENTS.md` / `CLAUDE.md`。

---

## 前置条件
- Python 3.9+
- LibreOffice（提供 `soffice` 可执行）
- Poppler（提供 `pdftoppm`）
- 可选：真实 LLM API Key（无则使用 `llm_provider: mock` 模式）

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
如未在 PATH，可在 `config/settings.yaml` 中设置绝对路径（详见"配置"）。

---

## 配置
- 复制模板配置：`config/settings.example.yaml -> config/settings.yaml` 并按需调整
- 主要配置项：
  - `llm_provider` / `llm_model` / `llm_api_key` / `llm_base_url`：LLM 配置（支持 `mock` 模式）
  - `vectordb_enabled` / `vectordb_provider` / `vectordb_persist_dir`：向量库配置
  - `embedding_model` / `embedding_device`：M3E 模型与设备选择（cpu/cuda/mps）
  - `enable_llm_classify` / `enable_topic_chunks` / `enable_step_chunks` / `enable_metrics_chunks`：RAG v2 功能开关
  - `soffice_path` / `pdftoppm_path`：渲染工具路径（可选，默认从 PATH 查找）
- CLI 可通过 `--config` 参数指定配置文件路径

---

## 使用示例

### PPT 解析主流程
```bash
# 基础用法
python -m src --input ppts/ChatBI产品介绍_2025.pptx --output ppt_outputs/ChatBI产品介绍_2025

# 强制重新运行（忽略缓存）
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --force

# 详细日志
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --verbose
```

### 向量库管理
```bash
# 导入单个项目
python -m src.scripts.vectordb_cli import --input ppt_outputs/ChatBI/embeddings/rag_documents.json

# 批量导入所有项目
python -m src.scripts.vectordb_cli batch-import --input-dir ppt_outputs

# 查询向量库
python -m src.scripts.vectordb_cli query --text "ChatBI的核心功能" --top-k 5

# 查看统计信息
python -m src.scripts.vectordb_cli stats

# 删除项目
python -m src.scripts.vectordb_cli delete --project ChatBI
```

### 问答 CLI
```bash
# 基础问答
python -m src.scripts.qa_cli -q "ChatBI的核心功能是什么" --config config/settings.yaml

# 指定项目过滤
python -m src.scripts.qa_cli -q "核心功能是什么" -p ChatBI --config config/settings.yaml

# 自定义检索参数
python -m src.scripts.qa_cli -q "架构设计" --top-k 8 --top-n 5 --tau 0.5
```

### Gradio Web UI（推荐）
```bash
# 启动引导式对话界面
python -m src.scripts.qa_gradio --config config/settings.yaml
```
访问 http://localhost:7860 使用 Web 界面进行问答。

### 监控与缓存
- `qa_cli` 和 `qa_gradio` 默认启用 `QAMonitor`
- 命中缓存时输出 `[cache hit/<level>]` 前缀
- 日志与精确缓存写入 `logs/qa_sessions/`（按日滚动 JSONL）
- 语义缓存已下线，缓存命中仅依赖精确匹配（TTL 默认 7 天）
- 可通过 `qa.cache.vectordb_version` 统一失效缓存

### 输出示例
- `slides/001.png`…：渲染图片
- `page_summaries/001.json`…：单页总结
- `doc_summary/project_profile.json`：聚合画像
- `embeddings/rag_documents.json`：RAG 文档（包含 qa_pair/topic/step/metrics/overview 多种 chunk）
- `manifest.json`：元数据与错误记录

---

## 项目结构
```bash
.
├─docs/                     # 需求、设计、方案文档
├─ppts/                     # 输入 PPT 资产
├─ppt_outputs/              # 渲染与总结产物（构建输出）
│  └─<project>/
│     ├─slides/             # PNG 渲染图片
│     ├─page_summaries/     # 单页总结 JSON
│     ├─doc_summary/        # 项目画像 JSON
│     ├─embeddings/         # RAG 文档（rag_documents.json）
│     └─manifest.json       # 元数据与错误记录
├─src/                      # 核心代码
│  ├─renderer/              # PPTX → PDF → PNG 渲染
│  ├─extractor/             # 文本与 speaker notes 抽取
│  ├─summarizer/            # 单页总结 + 项目画像生成（LLM）
│  ├─prompts/               # 统一 Prompt 管理
│  ├─rag/                   # RAG v2：QA 对生成 + LLM 分类 + 多类型 chunk
│  ├─embeddings/            # M3E 向量模型封装
│  ├─vectordb/              # Chroma 向量库封装 + 检索护栏
│  ├─qa/                    # QA 引擎 + 监控/缓存
│  ├─scripts/               # CLI 工具（qa_cli、qa_gradio、vectordb_cli）
│  ├─pipeline.py            # 端到端编排
│  ├─config.py              # 配置加载
│  ├─models.py              # Pydantic 数据模型
│  └─__main__.py            # CLI 入口
├─tests/                    # 单元与端到端测试
├─config/                   # 配置模板与默认设置
│  ├─settings.example.yaml  # 配置模板
│  └─settings.yaml          # 实际配置（gitignored）
├─chroma_db/                # Chroma 向量库持久化目录
├─logs/                     # 日志与缓存
│  └─qa_sessions/           # QA 日志与精确缓存（JSONL）
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
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_pipeline_e2e.py -v

# 带覆盖率报告
pytest tests/ --cov=src --cov-report=html
```
> 若缺少 LibreOffice/Poppler 或未配置 LLM，相关测试会自动跳过；可设置 `llm_provider: mock` 以离线运行。
> Embedding 回归测试：`tests/tmp_run_tests.py` 生成 `tests/tmp_embedding_test_round1.json` 供对比。

---

## 部署（如适用）
- 部署目标：本地/自托管服务器
- 交付方式：Python CLI + Gradio Web UI；可封装为容器镜像（自行添加 Dockerfile）
- 关键参数：`config/settings.yaml` 中的 LLM、向量库、渲染工具路径配置
- 依赖服务：LibreOffice、Poppler、LLM API（或 mock 模式）、Chroma 向量库

---

## 路线图（可选）
- [ ] 完善 Docker 化与一键安装脚本
- [ ] RAG v2 优化：自动化嵌入质量基线与回归测试
- [ ] 增强多模型策略与重排参数自动调优
- [ ] 增加任务队列与批处理能力
- [ ] 扩充异常 PPT 样本，完善解包和告警回退

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

## 实施过程说明（通俗版，聚焦 RAG v2）

### 整体思路
从第一性原理出发，我们先把 PPT 拆成最小可验证的链路：渲染出图片、提取文本、做单页总结，再聚合成项目画像。所有这些中间结果最终落到一份统一的 RAG 嵌入文档 `embeddings/rag_documents.json`，这样后续检索和问答都不必重复解析 PPT。

### RAG v2：QA-Pair 方案
不同于 v1 的单 chunk 方案，v2 采用 QA-pair 为中心的多类型 chunk 生成策略：

1. **QA 对生成**：每页 PageSummary 生成 5-10 个自然问答对，包含问题、答案、替代问法、关键词
2. **LLM 批量分类**：8-10 个 QA 对一次性分类到 8 个类别（positioning/features/architecture/deployment/integration/cases/comparison/roadmap）
3. **多类型 Chunk**：
   - `qa_pair`（主力）：问答对 + 替代问法 + 关键词，适合精确匹配
   - `topic`（可选）：主题块，适合长文本回答
   - `step`（可选）：流程步骤，适合操作指南
   - `metrics`（可选）：性能数据，适合数据查询
   - `overview`（项目级）：聚合画像，适合全局问题

4. **成本优化**：批量分类相比逐条分类节省 80% token 成本
5. **功能开关**：`enable_llm_classify` / `enable_topic_chunks` / `enable_step_chunks` / `enable_metrics_chunks` 可按需启用/关闭

### Embedding 与向量化
- **文本准备**：轻量清洗、去空字段、解包嵌套 JSON，按语义段落拼接，保持上下文完整
- **批量向量化**：使用 `moka-ai/m3e-base`（768 维）本地推理，自动选择 CPU/CUDA/MPS，OOM 时自动降低 batch
- **选择 M3E 的原因**：中文语义效果稳定、模型体量适中（可本地离线）、社区基准表现良好；相比英文化模型，中文召回与断句更可靠；开源许可便于内网部署
- **向量库集成**：向量生成后写入 Chroma，metadata 保留 `project_name/slide_no/page_type/chunk_type/category_id/level/confidence` 等字段，便于后续过滤与重排
- **结果记录**：Embedding 与插入耗时、成功/失败数写入 manifest，便于回溯

### 检索与重排
- **包装函数**：`ChromaStore.query_with_guardrails(text, project_name=None, where=None, top_k=8, top_n=5, tau=0.5)`（src/vectordb/chroma_store.py）
- **项目过滤**：若未传 where，单项目场景自动过滤；多项目可传 `project_name` 或自定义 `where`
- **召回与重排**：`top_k=8` 召回 → 相似度 + 细节页/slide 加分 → 取前 5
- **阈值护栏**：Top-1 相似度 `< 0.5` 返回空列表（由上层决定"未找到相关内容"的文案）
- **QA-aware 检索**：`query_with_qa_ranking` 支持问题相似度加权，提升问答匹配精度
- **测试回归**：`tests/tmp_run_tests.py` 直接调用包装函数，输出 `tests/tmp_embedding_test_round1.json` 供对比调参效果

### 监控与缓存
- **QAMonitor**：`qa_cli` 和 `qa_gradio` 默认启用，命中缓存会在答案前打印 `[cache hit/<level>]`
- **精确缓存**：基于问题文本的精确匹配，TTL=7 天，可用 `qa.cache.vectordb_version` 统一失效
- **日志记录**：日志与缓存写入 `logs/qa_sessions/qa_logs_YYYYMMDD.jsonl` / `qa_cache.jsonl`（按日滚动）
- **语义缓存已下线**：仅保留精确缓存，避免误命中

### 持续改进方向
- 建立自动化的嵌入质量基线与回归测试
- 继续优化 QA 对生成质量与分类准确率
- 补齐 Docker/一键安装、任务队列和可视化看板
- 扩充异常 PPT 样本，完善解包和告警回退，提升鲁棒性  
