"""Gradio Web UI for guided QA dialogue."""

from __future__ import annotations

import argparse
import sys
from typing import List, Tuple

try:
    import gradio as gr
except ImportError:  # pragma: no cover
    print("Gradio 未安装，请先运行: pip install gradio>=4.0.0", file=sys.stderr)
    sys.exit(1)

from src.config import Settings
from src.embeddings import M3EEmbedding
from src.prompts import get_guided_templates
from src.qa import QAEngine
from src.qa.dialogue_orchestrator import DialogueOrchestrator, DialogueState
from src.qa.qa_monitor import QAMonitor
from src.summarizer import LLMClient
from src.vectordb import ChromaStore


def _init_engine(settings: Settings) -> Tuple[QAEngine, DialogueOrchestrator]:
    embedding_model = M3EEmbedding(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
        cache_dir=settings.embedding_cache_dir,
    )
    store = ChromaStore(
        persist_dir=settings.vectordb_persist_dir,
        collection_name=settings.vectordb_collection_name,
        embedding_model=embedding_model,
    )
    llm_client = LLMClient(settings)
    monitor = QAMonitor(settings=settings, embedding_model=embedding_model)
    qa_engine = QAEngine(store=store, llm_client=llm_client, monitor=monitor)

    guided_cfg = getattr(settings.qa, "guided", None)
    templates_path = None
    gap_threshold = 0.5
    if guided_cfg:
        templates_path = getattr(guided_cfg, "templates_path", None)
        gap_threshold = getattr(guided_cfg, "gap_similarity_threshold", 0.5)
    templates = get_guided_templates(templates_path)
    orchestrator = DialogueOrchestrator(qa_engine=qa_engine, templates=templates, gap_threshold=gap_threshold)
    return qa_engine, orchestrator


def build_app(orchestrator: DialogueOrchestrator, default_project: str | None = None):
    state = gr.State(DialogueState())

    def format_sources(sources: List[dict]) -> str:
        if not sources:
            return ""
        head = []
        for src in sources[:3]:
            proj = src.get("project", "N/A")
            slide = src.get("slide_no", "N/A")
            head.append(f"{proj}:第{slide}页")
        return "来源: " + " | ".join(head)

    def chat_fn(message: str, chat_history: List[Tuple[str, str]], project: str, st: DialogueState):
        st = st or DialogueState()
        if project:
            st.slots["project_name"] = project

        result = orchestrator.answer_with_guidance(message, st)
        answer = result.get("answer", "")
        sources_str = format_sources(result.get("sources", []))
        if sources_str:
            answer = f"{answer}\n\n_{sources_str}_"

        suggestions = result.get("suggestions", [])
        chat_history = chat_history + [(message, answer)]
        return chat_history, gr.update(choices=suggestions, value=None), st

    def use_suggestion(suggestion: str):
        return gr.update(value=suggestion)

    with gr.Blocks(title="Guided QA") as demo:
        gr.Markdown("### 引导式 QA（Gradio）")
        with gr.Row():
            project_dd = gr.Textbox(label="项目过滤（可选）", placeholder="请输入项目名称", value=default_project or "")
        chatbot = gr.Chatbot(label="对话", height=400)
        suggestions = gr.Radio(label="下一步追问", choices=[], interactive=True)
        msg = gr.Textbox(label="问题", placeholder="请输入问题")
        send = gr.Button("发送", variant="primary")
        clear = gr.Button("清空对话")

        send.click(
            chat_fn,
            inputs=[msg, chatbot, project_dd, state],
            outputs=[chatbot, suggestions, state],
        ).then(lambda: gr.update(value=""), None, [msg])

        suggestions.change(use_suggestion, inputs=[suggestions], outputs=[msg])
        clear.click(
            lambda: ([], gr.update(choices=[], value=None), DialogueState()),
            outputs=[chatbot, suggestions, state],
        )

    return demo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gradio UI for guided QA dialogue")
    parser.add_argument("--config", default="config/settings.yaml", help="配置文件路径")
    parser.add_argument("--host", default="0.0.0.0", help="Gradio host")
    parser.add_argument("--port", type=int, default=7860, help="Gradio port")
    parser.add_argument("--project", default=None, help="默认项目过滤（可选）")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        settings = Settings.from_yaml(args.config)
    except FileNotFoundError as e:  # pragma: no cover
        print(f"配置文件不存在: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # pragma: no cover
        print(f"加载配置失败: {e}", file=sys.stderr)
        sys.exit(1)

    _, orchestrator = _init_engine(settings)
    demo = build_app(orchestrator, default_project=args.project)
    demo.launch(server_name=args.host, server_port=args.port, share=False)


if __name__ == "__main__":
    main()
