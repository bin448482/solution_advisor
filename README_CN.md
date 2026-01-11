# Solution Advisor · PPT解析与项目画像流水线

将项目介绍类 PPT 自动转换为结构化画像与 RAG 知识库，默认产出以 **category_summary + overview** 为主的高质量 `rag_documents.json`，并可选启用 LangGraph Map-Reduce 自动化生成。

> 项目类型：AI / Tool / CLI / Web App
> 主要语言：Python 3.9+
> 技术栈：LibreOffice、Poppler、LangChain/LangGraph、Chroma、M3E、LLM（可 mock）、Streamlit
> 目标用户：Developers / Internal Teams / Solution Consultants

---

## AI 驱动快速上手（Claude / Codex）

本项目是 **AI 驱动的项目生成与知识沉淀工程**：从 PPT 解析、总结到画像与 RAG 资产生成，流程与实现细节分散在 `docs/`、各模块 `AGENTS.md` 以及 `src/` 代码中。你可以直接用 **Claude / Codex** 作为“项目导读助手”，在不通读全仓库的情况下快速建立全局理解与落地路径。

建议的高频提问（可直接复制给工具）：
- “用一句话说明这个仓库解决什么问题；端到端输入/输出分别是什么？”
- “从 `python -m src --input ppts/... --output ppt_outputs/...` 开始，逐步解释每一步做什么、产物写到哪里、如何复跑/强制重跑。”
- “解释 `category_summary + overview` 的 RAG 产物结构，以及为什么它比逐页 QA 更稳定；对应的实现/配置开关在哪里？”
- “如果我想在新项目上落地：需要准备哪些依赖与配置（LibreOffice/Poppler/LLM/mock），最小可跑的命令是什么？”

## 核心价值（Context Engineering · 类别优先 RAG）

本项目把 RAG 的关键从“检索 + 生成”前移到更底层的第一原理：**决定在每一次 LLM 生成步骤中，什么信息应该被放进上下文窗口（Context Engineering）**。在企业 PPT 这类信息密、结构散、噪声高的资产上，核心价值体现在以下几点：

- **把上下文当稀缺资源而不是“垃圾桶”**：通过离线提炼与结构化，把低密度、强冗余的原始内容转成高密度知识单元，减少无效 token 与注意力分散（Context Rot），让回答更稳定、更一致。
- **用“类别优先”对抗检索碎片化**：摄取阶段先做单页总结，再按主题聚合形成 `category_summary`，把“散落在多页的关键概念”变成可直接装配到上下文的主题部件；运行时优先检索类别摘要、按需补充少量证据页/引用，避免在线“拼图式推理”。
- **Map-Reduce 工程化提炼，支持规模化与可控成本**：使用 Map（局部提炼）→ Merge（语义聚合）→ Reduce（类别成形）的流水线，把方法论变成可调参数与可复现产物（manifest/版本/配置），在批处理与多项目场景下更容易控时延、控费用、控质量。
- **可追溯与可回归：从“炼金术”走向工程迭代**：类别摘要自带来源锚点（slide refs/引用），便于评审与复核；结合黄金问题集/回归评测与监控日志，把每次改动（粒度、合并策略、Top-K、阈值、提示词）量化成可对比的质量/成本/时延指标。

适用的典型场景：
- **售前/解决方案顾问**：快速回答“核心功能/差异点/适用行业/实施路径/成功案例”等高频问题，并能给出可追溯引用。
- **多项目知识库沉淀**：把每份项目 PPT 统一沉淀为可检索的类别摘要资产，跨项目复用，支持项目过滤与低成本部署。
- **交付与内部对齐**：用项目画像与类别摘要驱动需求澄清、交付范围对齐、培训材料生成，减少口径漂移。
- **批量摄取与治理**：当资产来源复杂、格式不一时，用离线提炼（含校验与回退）提升稳定性，避免在线检索质量波动导致的幻觉与返工。

---

## 徽章（可选）
![License](https://img.shields.io/badge/license-Private-blue)
![Build](https://img.shields.io/badge/build-passing-brightgreen)
![Status](https://img.shields.io/badge/status-active-success)

---

## 目录
- [Solution Advisor · PPT解析与项目画像流水线](#solution-advisor--ppt解析与项目画像流水线)
  - [AI 驱动快速上手（Claude / Codex）](#ai-驱动快速上手claude--codex)
  - [核心价值（Context Engineering · 类别优先 RAG）](#核心价值context-engineering--类别优先-rag)
  - [徽章（可选）](#徽章可选)
  - [目录](#目录)
  - [功能特性](#功能特性)
  - [架构 / 设计概览](#架构--设计概览)
  - [前置条件](#前置条件)
  - [安装](#安装)
  - [配置](#配置)
  - [使用示例](#使用示例)
    - [PPT 解析主流程](#ppt-解析主流程)
    - [向量库管理](#向量库管理)
    - [问答 CLI](#问答-cli)
    - [Streamlit Web UI（推荐）](#streamlit-web-ui推荐)
    - [监控与缓存](#监控与缓存)
    - [输出示例](#输出示例)
  - [项目结构](#项目结构)
  - [开发指南](#开发指南)
  - [测试](#测试)
  - [部署（如适用）](#部署如适用)
  - [路线图（可选）](#路线图可选)
  - [贡献指南](#贡献指南)
  - [许可证](#许可证)
  - [维护者 / 联系方式](#维护者--联系方式)
  - [实施过程说明（通俗版，聚焦 category-first RAG）](#实施过程说明通俗版聚焦-category-first-rag)
    - [我们要解决什么问题？](#我们要解决什么问题)
    - [为什么选 “category-first” 路线？](#为什么选-category-first-路线)
    - [方案怎么做？](#方案怎么做)

---

## 功能特性
- 端到端链路：PPT 渲染 → 文本抽取 → 单页总结 → 项目画像 → `rag_documents.json`，默认走**人工高质量生成**（见 `docs/generate_rag_documents.md`，以 category_summary + overview 为主）。
- 可选自动化 RAG：开启 `auto_ragprep_enabled` 时，使用 LangGraph Map-Reduce 生成 category_summary/overview，复刻人工聚合口径；旧 QA 多 chunk 自动链路已退场。
- RAG 形态：主力 chunk 为 `category_summary`（按类别聚合）+ `overview`；`qa_pair/metrics/topic/step` 作为兼容性附加项，可通过开关控制。
- 向量检索与护栏：M3E 中文 embedding + Chroma + 相似度阈值（`top_k/top_n/tau` 可调），缺少高相似度时返回空。
- 多入口：`python -m src` 主流程、`qa_cli` 问答（支持 guided 模式）、`vectordb_cli` 管理嵌入、**Streamlit Web UI**（项目选择、引用、反馈、引导式对话）。
- 监控与缓存：QAMonitor 精确缓存（TTL 7 天，版本可控）+ JSONL 日志；命中时提示 `[cache hit/<level>]`。
- 低耦合配置：LLM/embedding/vectordb/渲染工具均可替换，支持 `llm_provider=mock` 离线调试。

---

## 架构 / 设计概览
- 核心组件：
  - `renderer/libreoffice.py`：PPTX → PDF → PNG 两步渲染
  - `extractor/ppt_extractor.py`：文本与 speaker notes 抽取
  - `summarizer/`：单页总结 + 项目画像生成（LLM，支持 mock）
  - `rag/map_reduce_graph.py`：LangGraph Map-Reduce，自动生成 category_summary + overview（仅在 `auto_ragprep_enabled=true` 时调用）
  - `rag/chunk_generator.py`：QA 对、多类型 chunk 生成（兼容模式，可按开关使用）
  - `embeddings/m3e_model.py`：M3E 中文向量模型（768 维）
  - `vectordb/chroma_store.py`：Chroma 向量库封装 + 检索护栏
  - `qa/qa_engine.py`：检索 + LLM 生成 + 监控/缓存；`qa/dialogue_orchestrator.py` 提供引导式对话
  - `pipeline.py`：端到端编排（支持 refine 与分阶段强制重跑）
- 接口层：
  - `python -m src`：PPT 解析主流程 CLI
  - `src/scripts/qa_cli.py`：命令行问答（`--guided` 触发引导式多轮）
  - `src/scripts/vectordb_cli.py`：向量库管理（导入/批量导入/查询/统计/删除）
  - **`src/ui/streamlit_app.py`：Streamlit Web UI（可视化问答界面）**
- 数据与存储：本地文件系统 + `chroma_db/` 向量库 + `logs/qa_sessions/` 日志 & 缓存
- 扩展点：LLM 客户端、RAG 开关（自动/人工、chunk 类型）、召回与重排参数、guided 模板与提示词

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

# 安装依赖
pip install -r requirements.txt

# 如需使用 Web UI，额外安装 Streamlit
pip install streamlit>=1.30.0
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
  - `auto_ragprep_enabled`：默认 `false`，人工生成 `rag_documents.json`（按 `docs/generate_rag_documents.md`，侧重 category_summary+overview）；置 `true` 时启用 LangGraph Map-Reduce 自动生成。配套参数：`map_batch_size` / `map_max_categories_per_batch` / `reduce_target_categories` / `langgraph_max_concurrency` / `map_temperature` / `reduce_temperature`。
  - Chunk 开关：`enable_category_summary_chunks`（默认 true）控制聚合 chunk；`enable_llm_classify` / `enable_topic_chunks` / `enable_step_chunks` / `enable_metrics_chunks` 为兼容性选项。
  - QA 引导：`qa.guided.enabled` / `templates_path` / `gap_similarity_threshold` / `llm_prompt_path` 控制 guided 模式。
  - 监控与缓存：`qa.cache.cache_ttl_days` / `cache_backend` / `vectordb_version`（统一失效缓存）；
  - `soffice_path` / `pdftoppm_path`：渲染工具路径（可选，默认从 PATH 查找）
- CLI 可通过 `--config` 参数指定配置文件路径；`--no-vectordb` 可跳过入库，仅生成 embeddings。

---

## 使用示例

### PPT 解析主流程
```bash
# 基础用法
python -m src --input ppts/ChatBI产品介绍_2025.pptx --output ppt_outputs/ChatBI产品介绍_2025

# 强制重新运行（忽略 manifest）
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --force

# 仅重跑渲染/抽取或摘要阶段
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --force-capture
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --force-interpret

# 修复模式：仅重跑低置信度页面
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --refine --threshold 0.6 --pages "1,3,5"

# 跳过入库，仅生成 embeddings 文件
python -m src --input ppts/<file>.pptx --output ppt_outputs/<name> --no-vectordb
```

- 默认路径：运行后获得 `slides/`、`slide_texts.jsonl`、`page_summaries/`、`doc_summary/project_profile.json`。**RAG 默认走人工高质量路线**：按 `docs/generate_rag_documents.md` 产出以 category_summary+overview 为主的 `embeddings/rag_documents.json`，再重跑主流程（或用 `vectordb_cli import-docs`）写入向量库。
- 自动 RAG（可选）：`config/settings.yaml` 中设 `auto_ragprep_enabled: true` 时，流水线会调用 LangGraph Map-Reduce 自动生成 category_summary/overview 并入库，适合批量/草稿。
- 产物与错误均写入 `manifest.json`，可复用缓存避免重复计算。

### 向量库管理
```bash
# 导入单个项目
python -m src.scripts.vectordb_cli import-docs --input ppt_outputs/ChatBI/embeddings/rag_documents.json

# 批量导入所有项目（扫描 ppt_outputs/*/embeddings/rag_documents.json）
python -m src.scripts.vectordb_cli batch-import --input-dir ppt_outputs

# 查询向量库
python -m src.scripts.vectordb_cli query --text "ChatBI的核心功能" --top-k 5

# 查看统计信息
python -m src.scripts.vectordb_cli stats

# 列出项目
python -m src.scripts.vectordb_cli list-projects

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

# 引导式对话（澄清/追问建议）
python -m src.scripts.qa_cli -q "数据落地怎么部署" --guided
```

### Streamlit Web UI（推荐）
```bash
# 启动 Web 界面
streamlit run src/ui/streamlit_app.py

# 指定端口
streamlit run src/ui/streamlit_app.py --server.port 8501
```

**功能特性：**
- 项目选择与参数调节（top_k、top_n、tau）
- 自然语言问答（流畅段落回答，无生硬列表）
- 缓存状态显示（⚡ 图标）
- 对话历史管理
- 反馈收集（👍/👎/评论）
- 可选：显示引用来源（调试用）
- 可选：对话引导模式（澄清问题 + 追问建议，复用 DialogueOrchestrator）

**访问地址：** http://localhost:8501

### 监控与缓存
- `qa_cli` 默认启用 `QAMonitor`
- 命中缓存时输出 `[cache hit/<level>]` 前缀
- 日志与精确缓存写入 `logs/qa_sessions/`（按日滚动 JSONL）
- 语义缓存已下线，缓存命中仅依赖精确匹配（TTL 默认 7 天）
- 可通过 `qa.cache.vectordb_version` 统一失效缓存

### 输出示例
- `slides/001.png`…：渲染图片
- `slide_texts.jsonl`：每页抽取的原始文本
- `page_summaries/001.json`…：单页总结
- `doc_summary/project_profile.json`：聚合画像
- `embeddings/rag_documents.json`：RAG 文档（默认以 category_summary + overview 为主，兼容 qa_pair/metrics 等）
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
│     ├─slide_texts.jsonl   # 抽取后的原始文本
│     ├─page_summaries/     # 单页总结 JSON
│     ├─doc_summary/        # 项目画像 JSON
│     ├─embeddings/         # RAG 文档（rag_documents.json）
│     └─manifest.json       # 元数据与错误记录
├─src/                      # 核心代码
│  ├─renderer/              # PPTX → PDF → PNG 渲染
│  ├─extractor/             # 文本与 speaker notes 抽取
│  ├─summarizer/            # 单页总结 + 项目画像生成（LLM）
│  ├─prompts/               # 统一 Prompt 管理
│  ├─rag/                   # RAG 生成：QA 对/多 chunk + LangGraph Map-Reduce 自动聚合
│  ├─embeddings/            # M3E 向量模型封装
│  ├─vectordb/              # Chroma 向量库封装 + 检索护栏
│  ├─qa/                    # QA 引擎 + 监控/缓存
│  ├─ui/                    # Streamlit Web UI
│  ├─scripts/               # CLI 工具（qa_cli、vectordb_cli）
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
├─snapshots/                # 手工截图/验收记录（可选）
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
pytest tests/test_dialogue_orchestrator.py -v   # 引导式对话逻辑

# 带覆盖率报告
pytest tests/ --cov=src --cov-report=html
```
> 若缺少 LibreOffice/Poppler 或未配置 LLM，相关测试会自动跳过；可设置 `llm_provider: mock` 以离线运行。
> Embedding 回归测试：`tests/tmp_run_tests.py` 生成 `tests/tmp_embedding_test_round1.json` 供对比。`src/scripts/qa_eval_llm.py` 可对 `tests/qa_test_results/qa_test_*.json` 进行 LLM 自评。

---

## 部署（如适用）
- 部署目标：本地/自托管服务器
- 交付方式：Python CLI；可封装为容器镜像（自行添加 Dockerfile）
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

## 实施过程说明（通俗版，聚焦 category-first RAG）

### 我们要解决什么问题？
项目介绍类 PPT 往往信息密、结构散、样式不统一。直接把整份 PPT 丢给大模型要么超上下文，要么得到碎片化、不可追溯的答案。目标是把 PPT 里的知识沉淀成可检索、可追溯的 RAG 资产，既能回答「核心功能是什么？」这种高频问题，又能稳定支撑多项目、低成本的内网部署。

### 为什么选 “category-first” 路线？
1) **可追溯且抗碎片**：先做单页总结，再按主题类别聚合生成category_summary，每条都带来源 slide refs。相比逐页 QA，类别级聚合减少重复和噪声。  
2) **上下文可控**：类别数量可控（~6–12），文本长度稳定，向量库更干净，检索时不用在一堆近似重复的 QA 里重排。  
3) **人工与自动双轨**：人工路径保证质量（默认）；需要批处理时开启 LangGraph Map-Reduce 自动产草稿，再人工抽检，成本/效率平衡。  
4) **兼容旧策略**：保留 QA 多 chunk 开关，方便回归或特殊场景，不破坏现有数据。

### 方案怎么做？
1) **可验证链路拆解**：渲染 → 文本抽取 → 单页总结 → 项目画像。任何一步都写 manifest，便于复跑与定位问题。  
2) **类别聚合（人工主路径）**：阅读 `page_summaries/*.json`，按固定提示词把同类 slide 聚合成 `category_summary`（摘要 + 3–5 QA + 来源引用）和项目级 `overview`，落盘 `embeddings/rag_documents.json`。  
3) **自动 Map-Reduce（可选，LangGraph）**：`auto_ragprep_enabled=true` 时走并行 Map-Reduce，产物与人工格式一致（category_summary + overview）：  
   - **批切分**：按 `map_batch_size`（默认 10 页）把 `page_summaries` 分批，控制上下文。  
   - **Map**：每批调用 LLM 产出 3–6 个“局部类别”，每类含 100–150 字摘要、可选 1–2 QA、`source_slide_refs`；温度 `map_temperature`（默认 0.2）。  
   - **Merge**：收集全部局部类别，按名称/语义合并，相似度高的合并，目标总类数受 `reduce_target_categories`（默认 10）约束。  
   - **Reduce**：对合并后的每个全局类别再次调用 LLM，生成 200–300 字 `category_summary` + 3–5 QA，引用去重升序；温度 `reduce_temperature`（默认 0.2）。  
   - **Overview**：基于所有 category_summary 摘要生成 150–200 字项目级 overview。  
   - **并发与兜底**：Map/Reduce 节点受 `langgraph_max_concurrency` 控制；LLM 失败会退回启发式汇总并记录到 manifest。  
   - **输出校验**：结构、长度、来源引用校验后落盘 `embeddings/rag_documents.json`，失败项记录在 manifest.errors。  
4) **向量化与护栏**：用 `moka-ai/m3e-base` 本地批量编码（自动 CPU/CUDA/MPS），metadata 保留 project/slide/level/chunk_type/category_id/confidence，低相似度直接返回空，避免幻觉。  
5) **检索与回答**：`ChromaStore.query_with_guardrails(..., tau=0.5, top_k=8, top_n=5)`，可按项目过滤、细节页加权，QAEngine 统一封装，CLI/UI 直接复用。  
6) **监控与缓存**：QAMonitor 写精确缓存与日志（TTL 7 天，`vectordb_version` 可一键失效），命中时提示 `[cache hit/<level>]`，便于灰度与回溯。
