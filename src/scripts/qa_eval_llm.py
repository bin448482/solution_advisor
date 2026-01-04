"""批量对 QA 结果做 LLM 自评打分。

用法示例：
  python -m src.scripts.qa_eval_llm --input tests/qa_test_results/qa_test_20260104_101010.json \
    --config config/settings.yaml --eval-provider openai --eval-model gpt-4o-mini

默认会自动寻找 tests/qa_test_results 目录下最新的 qa_test_*.json。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from src.config import Settings
from src.summarizer import LLMClient


def _extract_answer(cli_output: str) -> str:
    """从 qa_cli 的标准输出中提取回答正文。

    规则：找到“回答:”行后开始收集，遇到“来源:/推荐追问/状态/问题”开头的行时停止。
    """
    if not cli_output:
        return ""

    lines = cli_output.splitlines()
    collecting = False
    answer_lines: List[str] = []
    sentinels = ("来源:", "推荐追问", "状态:", "问题:")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("回答:"):
            collecting = True
            continue
        if collecting:
            if not stripped:
                # 跳过空行但不终止
                continue
            if any(stripped.startswith(s) for s in sentinels):
                break
            answer_lines.append(stripped)

    return "\n".join(answer_lines).strip()


def _build_prompt(question: str, answer: str) -> str:
    """构建评估提示词。"""
    return f"""You are an impartial QA judge. Score the assistant's answer ONLY based on how well it addresses the user's question.
Return a compact JSON object with fields:
  - score: integer 0-10 (higher = better)
  - rationale: <=60 chars summary of why the score was given
  - relevance: one of ["low","medium","high"]
  - completeness: one of ["low","medium","high"]
  - hallucination_risk: one of ["low","medium","high"]
Rules: be strict; if answer is empty or off-topic, score 0-3. Output JSON only, no extra text.

Question: {question}
Answer: {answer or '[empty]'}
"""


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    """尝试从 LLM 输出中解析 JSON，宽容处理前后噪声。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 寻找第一个 { ... } 片段
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return None
    return None


def _pick_latest_result() -> Path:
    """返回 tests/qa_test_results 下最新的 qa_test_*.json。"""
    base = Path("tests/qa_test_results")
    candidates = sorted(base.glob("qa_test_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("未找到 qa_test_*.json，请先运行 tests/test_qa_questions.py")
    return candidates[0]


@click.command()
@click.option("--input", "input_path", type=click.Path(path_type=Path), help="QA 测试结果 JSON（默认取最新 qa_test_*.json）")
@click.option("--config", default="config/settings.yaml", show_default=True, help="配置文件路径")
@click.option("--eval-provider", default=None, help="评估使用的 LLM provider（覆盖配置）")
@click.option("--eval-model", default=None, help="评估使用的模型名称（覆盖配置）")
@click.option("--limit", type=int, default=None, help="只评估前 N 条，便于快速抽样")
@click.option("--temperature", type=float, default=0.0, show_default=True, help="评估模型温度")
def cli(input_path: Path | None, config: str, eval_provider: str | None, eval_model: str | None, limit: int | None, temperature: float):
    """读取 qa_cli 批量结果，调用另一 LLM 逐条打分并输出汇总 JSON。"""

    try:
        settings = Settings.from_yaml(config)
    except Exception as e:
        click.echo(f"加载配置失败: {e}", err=True)
        sys.exit(1)

    overrides = {"llm_temperature": temperature}
    if eval_provider:
        overrides["llm_provider"] = eval_provider
    if eval_model:
        overrides["llm_model"] = eval_model
    eval_settings = settings.with_overrides(**overrides)

    llm = LLMClient(eval_settings)
    if llm.is_mock:
        click.echo("警告：当前评估 LLM 为 mock/none，评分仅返回提示词，无法产生真实评估。", err=True)

    qa_result_path = input_path or _pick_latest_result()
    if not qa_result_path.exists():
        click.echo(f"结果文件不存在: {qa_result_path}", err=True)
        sys.exit(1)

    payload = json.loads(qa_result_path.read_text(encoding="utf-8"))
    qa_items: List[Dict[str, Any]] = payload.get("results", [])
    if not qa_items:
        click.echo("结果文件中未找到 results 字段。", err=True)
        sys.exit(1)

    if limit:
        qa_items = qa_items[:limit]

    click.echo(f"开始评估 {len(qa_items)} 条问答... (模型: {eval_settings.llm_provider}/{eval_settings.llm_model})")

    eval_results = []
    for idx, item in enumerate(qa_items, 1):
        question = item.get("question", "")
        answer = _extract_answer(item.get("output", "") or "")
        prompt = _build_prompt(question, answer)

        try:
            raw = llm.generate(prompt)
        except Exception as e:
            click.echo(f"[{idx}] 评估失败: {e}", err=True)
            raw = ""

        parsed = _parse_json(raw)
        eval_results.append(
            {
                "question_id": item.get("question_id"),
                "question": question,
                "answer_excerpt": answer[:200],
                "judge_raw": raw,
                "judge_parsed": parsed,
            }
        )
        click.echo(f"[{idx}/{len(qa_items)}] done -> {parsed.get('score') if parsed else 'N/A'}")

    # 汇总
    scores = [r["judge_parsed"]["score"] for r in eval_results if r.get("judge_parsed") and isinstance(r["judge_parsed"].get("score"), (int, float))]
    summary = {
        "total": len(eval_results),
        "scored": len(scores),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
    }

    output_dir = Path("tests/qa_test_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"qa_eval_{ts}.json"
    out_payload = {
        "meta": {
            "source_file": str(qa_result_path),
            "eval_model": f"{eval_settings.llm_provider}/{eval_settings.llm_model}",
            "temperature": temperature,
            "generated_at": datetime.now().isoformat(),
        },
        "summary": summary,
        "results": eval_results,
    }
    out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"\n评估完成，结果已保存: {out_path}")
    click.echo(f"汇总: {summary}")


if __name__ == "__main__":
    cli()
