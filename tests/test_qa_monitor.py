import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import QACacheSettings, QAMonitoringSettings, QASettings, Settings
from src.qa.qa_monitor import QAMonitor


def build_settings(tmp_path: Path) -> Settings:
    qa_settings = QASettings(
        monitor=QAMonitoringSettings(log_dir=str(tmp_path / "logs")),
        cache=QACacheSettings(
            cache_enabled=True,
            cache_sample_rate=1.0,
            cache_semantic_enabled=False,
            cache_persist_dir=str(tmp_path / "chroma"),
        ),
    )
    return Settings(qa=qa_settings)


def test_cache_hit_and_log_written(tmp_path):
    settings = build_settings(tmp_path)
    monitor = QAMonitor(settings, log_dir=tmp_path / "logs")

    question = " 你好，帮我看看部署要求？ "
    norm = monitor.normalize_question(question)
    qid = monitor.build_question_id(norm, project_name="demo")

    monitor.save_cache(
        {
            "question_id": qid,
            "question_norm": norm,
            "question_raw": question,
            "project_name": "demo",
            "answer": "demo answer",
            "sources": [{"slide_no": 1}],
            "status": "success",
        }
    )

    hit = monitor.get_cache(qid, question_norm=norm, project_name="demo")
    assert hit
    assert hit["answer"] == "demo answer"
    assert hit["cache_level"] == "exact"

    monitor.log_event({"question_id": qid, "status": "success"})
    log_files = list((tmp_path / "logs").glob("qa_logs_*.jsonl"))
    assert log_files, "log file should be created"
    content = log_files[0].read_text(encoding="utf-8").strip()
    assert content, "log file should not be empty"
    first_line = json.loads(content.splitlines()[0])
    assert first_line["status"] == "success"


def test_cache_expired(tmp_path):
    settings = build_settings(tmp_path)
    monitor = QAMonitor(settings, log_dir=tmp_path / "logs")

    norm = monitor.normalize_question("过期测试")
    qid = monitor.build_question_id(norm, project_name=None)
    monitor.cache_index[qid] = {
        "question_id": qid,
        "question_norm": norm,
        "answer": "old",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "vectordb_version": settings.qa.cache.vectordb_version,
    }

    assert monitor.get_cache(qid, question_norm=norm) is None
