# Repository Guidelines

This repository is currently **document- and asset-driven**: it stores project PPTs and design/requirements docs, plus generated snapshot outputs.

## Project Structure & Module Organization

- `docs/`: Source-of-truth documentation (requirements, designs, notes). Prefer Markdown (`.md`).
- `ppts/`: Input PPT/PPTX assets (e.g. `ppts/ChatBI产品介绍_2025.pptx`).
- `ppt_outputs/`: Generated outputs (slide images, per-page summaries, manifests). Treat as build artifacts unless explicitly needed for review.
- `.claude/`: Local agent/tool settings (keep minimal; avoid committing secrets).

If you add executable code, introduce clear top-level directories:
- `src/` for implementation, `tests/` for automated tests, `scripts/` for CLI utilities.

## Build, Test, and Development Commands

There is **no build/test runner committed yet**. Common repo checks:

- `git status` — confirm only intended files are staged/modified.
- `find docs -name "*.md" -maxdepth 1` — list key docs for review.
- `ls -la ppts ppt_outputs` — verify inputs vs generated artifacts.
- `python -m src.scripts.qa_cli -q "ChatBI的核心功能是什么" [-p <项目名>] --config config/settings.yaml` — 运行 RAG 问答 CLI（top_k/top_n/tau 可调）。

When adding an automation pipeline (PPT→images→summaries), provide a single entrypoint, e.g. `python -m <module> --input ppts/... --out ppt_outputs/...`.

## Coding Style & Naming Conventions

- Prefer consistent, descriptive naming:
  - PPT inputs: `ppts/<ProjectName>_<Year>.pptx`
  - Snapshot outputs: `ppt_outputs/<ppt_basename>/slides/001.png`
  - Docs: `docs/<Topic>.md`
- Docs naming (docs/): `<领域/产品>_<主题>_<类型>.md`，类型常用 `需求分析/实施计划/测试方案/复盘`；示例：`PPT解析与项目画像_MVP实施计划.md`。保持中文文件名、首字母大写，避免空格。
- Keep Markdown concise and scannable: short sections, bullet lists, and explicit file paths.

## Testing Guidelines

- If code is added, include basic tests in `tests/` and document how to run them in this file.
- Add at least one “smoke test” that validates the end-to-end pipeline on a small PPT sample.
- Embedding回归：`tests/tmp_run_tests.py` / `ChromaStore.query_with_guardrails` 默认 project 过滤 + Top-K=8 召回、细节页/slide 加分重排 + 0.5 相似度阈值，生成 `tests/tmp_embedding_test_round1.json` 供对比。

## Commit & Pull Request Guidelines

- Git history uses short, direct commit messages (often Chinese), e.g. “保存…/更新…”. Keep messages **1 line**, describing the change intent.
- PRs should include:
  - A brief description of what changed and why
  - Links to relevant docs under `docs/`
  - Notes on any generated artifacts under `ppt_outputs/` (and whether they should be committed)

## Security & Configuration Tips

- Do not commit API keys, tokens, or customer-sensitive content.
- If `ppt_outputs/` is treated as generated output, add/update `.gitignore` accordingly.

## 分层 @AGENTS.md 职责与更新规范

- **根目录 `AGENTS.md`（本文件）**：定义全局开发规范、目录职责与公共命令，同时充当索引，必须列出并简述所有子目录的 `AGENTS.md`。
- **模块内 `AGENTS.md`**：记录该目录下实现的职责、入口脚本、关键依赖与运行/测试要点，只关注本模块。
- **变更同步**：完成某模块功能或接口调整后，须同时更新对应目录的 `AGENTS.md`（若属全局变更，也需同步本文件）。
- **新增目录**：新增模块时在该目录创建 `AGENTS.md`，并在根目录表格中添加引用说明。

| 子目录 `AGENTS.md` | 职责概述 |
| --- | --- |
| `src/AGENTS.md` | 总览 PPT 解析主流程、配置、核心依赖与 CLI 入口。 |
| `src/renderer/AGENTS.md` | PPTX → PDF/PNG 渲染策略与对 `soffice`/`pdftoppm` 依赖。 |
| `src/extractor/AGENTS.md` | 幻灯片文本抽取逻辑与数据对齐假设。 |
| `src/summarizer/AGENTS.md` | LLM 客户端、单页总结与项目画像生成流程。 |
| `src/prompts/AGENTS.md` | 统一管理问答/总结/画像的 Prompt 文本与加载器。 |
| `src/rag/AGENTS.md` | QA 对生成、LLM 分类与多类型 chunk 生成逻辑（RAG v2）。 |
| `src/embeddings/AGENTS.md` | M3E 向量模型加载、设备选择与批量编码策略。 |
| `src/vectordb/AGENTS.md` | Chroma 存储封装、检索护栏与项目过滤约定。 |
| `src/qa/AGENTS.md` | QA 引擎、监控与缓存（JSONL 精确缓存，语义缓存已移除）职责与配置。 |
| `src/scripts/AGENTS.md` | CLI 工具（qa_cli、vectordb_cli）参数与输出规范。 |
| `tests/AGENTS.md` | 测试覆盖范围、跳过条件与烟囱测试说明。 |

## Code status (MVP skeleton)
- Python pipeline lives in `src/` with CLI entry `python -m src --input ppts/... --output ppt_outputs/... --force`.
- Core pieces: rendering (`renderer/libreoffice.py`), text extraction (`extractor/ppt_extractor.py`), LLM summarization (`summarizer/`), orchestration (`pipeline.py`), config (`config.py`), CLI (`__main__.py`), utilities (`utils.py`).
- RAG 文档生成（v2）：`src/rag/` 包实现 QA-pair 方案，包含 `qa_generator.py`（问答对生成）、`classifier.py`（LLM 批量分类）、`chunk_generator.py`（多类型 chunk 生成）；`pipeline.py` 调用生成 `ppt_outputs/<ppt>/embeddings/rag_documents.json`，包含 qa_pair/topic/step/metrics/overview 多种 chunk 类型。
- RAG 开关：`config.Settings` 中的 `enable_llm_classify` / `enable_topic_chunks` / `enable_step_chunks` / `enable_metrics_chunks` 控制是否启用分类和可选 chunk（默认关闭，便于回滚/控成本）；refine 流程与主流程使用同一 RAG 生成逻辑。
- QA 问答：`src/qa/qa_engine.py` + `src/scripts/qa_cli.py`，调用 `ChromaStore.query_with_guardrails` 或 `query_with_qa_ranking`（QA-aware 检索）+ `LLMClient.generate`，默认 top_k=8 / top_n=5 / tau=0.5；可选监控/缓存中间层（`QAMonitor`）写 `logs/qa_sessions/*.jsonl`，仅提供精确命中（TTL/VDB 版本绑定），语义缓存已下线。
- Tests under `tests/` include model sanity and an e2e smoke that requires `soffice` + `pdftoppm` and uses `LLM_PROVIDER=mock`.
- Dependencies listed in `requirements.txt`; config template in `config/settings.example.yaml`; usage in `README.md`.
