# `src/prompts` 目录说明

职责：集中管理所有 LLM 提示词文本，避免分散在代码中。当前仅提供中文版本，按场景拆分。

文件清单：
- `qa_zh.txt`：RAG 问答主提示，包含 `{context}` / `{question}` 占位符。
- `page_summary_zh.txt`：单页总结 JSON 输出提示。
- `project_profile_zh.txt`：项目画像 JSON 输出提示。
- `guided_templates.yaml`：引导式对话模板（gap prompts、follow-ups 按模块）。
- `__init__.py`：缓存读取器，提供 `get_qa_prompt` / `get_page_summary_prompt` / `get_project_profile_prompt`。

主要消费者：
- `src/qa/qa_engine.py` 构建问答 prompt。
- `src/summarizer/page_summarizer.py` 单页总结。
- `src/summarizer/profile_generator.py` 项目画像生成。
- `src/qa/dialogue_orchestrator.py` 加载 `guided_templates`。

维护约定：
- 保持 `.txt` 为纯模型输入，不写说明性文字；如需备注，放在本文件或 `CLAUDE.md`。
- 修改占位符需同步更新调用方格式化逻辑。
- 若新增多语言/版本，请新增文件并在 `__init__.py` 中添加对应 accessor。

验证建议：
- 快速检查：`python -m src.scripts.qa_cli -q "测试问题" --config config/settings.yaml`（mock/真实均可）。
- Summarizer mock：设置 `LLM_PROVIDER=mock`，运行 pipeline 或单测，确认新 prompt 仍按预期输出结构。
