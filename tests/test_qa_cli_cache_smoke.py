from click.testing import CliRunner

import src.scripts.qa_cli as qa_cli


class DummyQAEngine:
    def __init__(self, store=None, llm_client=None, monitor=None):
        self.called_with = {"store": store, "llm_client": llm_client, "monitor": monitor}

    def answer(self, **kwargs):
        return {
            "answer": "cached answer",
            "status": "success",
            "cache_status": "hit",
            "cache_level": "exact",
            "sources": [],
        }


def test_cli_prints_cache_hit(monkeypatch, tmp_path):
    config_path = tmp_path / "settings.yaml"
    config_path.write_text("llm_provider: mock\n", encoding="utf-8")

    monkeypatch.setattr(qa_cli, "M3EEmbedding", lambda *args, **kwargs: "embedding")
    monkeypatch.setattr(qa_cli, "ChromaStore", lambda *args, **kwargs: "store")
    monkeypatch.setattr(qa_cli, "LLMClient", lambda *args, **kwargs: "llm")
    monkeypatch.setattr(qa_cli, "QAMonitor", lambda *args, **kwargs: "monitor")
    monkeypatch.setattr(qa_cli, "QAEngine", DummyQAEngine)

    runner = CliRunner()
    result = runner.invoke(
        qa_cli.cli,
        ["-q", "test question", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert "[cache hit" in result.output
    assert "cached answer" in result.output
