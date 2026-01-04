# QA 问答批量测试与 LLM 自评说明

目标：在无需 Gradio 的情况下高效跑一批问题，并用第二个 LLM 做自动主观评分，输出可追溯的 JSON 结果文件。

## 批量 QA（问答执行）
- 脚本：`tests/test_qa_questions.py`
- 命令：`python tests/test_qa_questions.py`
- 题库：脚本内 `QUESTIONS` 列表（行 13-48），可直接增删问题；支持中文/英文。
- 配置：默认 `config/settings.yaml`（可切换为 example 或自定义文件）；使用 `LLM_PROVIDER=mock` 可零成本检查检索链路。
- 输出：`tests/qa_test_results/qa_test_<timestamp>.json`，包含每题耗时/缓存命中/返回码，终端打印汇总。

## LLM 自评（答案评分）
- 脚本：`src/scripts/qa_eval_llm.py`
- 基本命令：
  - 指定输入：`python -m src.scripts.qa_eval_llm --input tests/qa_test_results/qa_test_YYYYMMDD_HHMMSS.json --config config/settings.yaml`
  - 自动取最新：`python -m src.scripts.qa_eval_llm --config config/settings.yaml`
- 关键参数：`--eval-provider` / `--eval-model` 覆盖评估模型；`--limit N` 抽样评估；`--temperature` 默认为 0。
- 评分逻辑：从 qa_cli 输出中截取“回答:”段落，构造严格 JSON-only judge prompt，返回 score 0-10、relevance/completeness/hallucination_risk 等字段；解析失败会记录 `judge_raw` 便于复查。
- 输出：`tests/qa_test_results/qa_eval_<timestamp>.json`，含 meta（来源文件、模型）、summary（avg_score 等）与逐题评分。

## 推荐工作流
1) 跑批量问答：`python tests/test_qa_questions.py`（必要时先设 `LLM_PROVIDER=mock` 做烟测）。
2) 跑自评：`python -m src.scripts.qa_eval_llm --config config/settings.yaml --eval-provider openai --eval-model gpt-5.1`（替换为可用模型）。
3) 查看 `qa_eval_*.json`：关注 avg_score、低分题的 `judge_raw`/`answer_excerpt`，用于回归和调优。

## 目录约定
- 问答结果：`tests/qa_test_results/qa_test_*.json`
- 自评结果：`tests/qa_test_results/qa_eval_*.json`
- 相关脚本：`tests/test_qa_questions.py`、`src/scripts/qa_eval_llm.py`
