# Claude 指南（`src/prompts`）

- 编辑 prompt 时仅修改 `.txt` 文件正文，保持 `{context}` / `{question}` 占位符不变；不在文件内加入说明性文字。
- 如需版本化或多语言，新增同名后缀文件（如 `qa_en.txt`）并在 `__init__.py` 添加 accessor。
- 评审提示变化：关注结构、长度、禁止外部知识等约束是否仍满足；必要时在 PR 描述说明改动目的。
- 运行/验证：可用 `LLM_PROVIDER=mock` 查看实际送入模型的字符串，QA 路径用 `python -m src.scripts.qa_cli ...`，Summarizer 路径用 pipeline 或相关单测。
