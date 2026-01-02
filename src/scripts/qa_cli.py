"""命令行问答工具：调用向量检索 + LLM 回答问题。"""

import sys

import click

from src.config import Settings
from src.embeddings import M3EEmbedding
from src.qa import QAEngine
from src.qa.qa_monitor import QAMonitor
from src.summarizer import LLMClient
from src.vectordb import ChromaStore


@click.command()
@click.option("--question", "-q", required=True, help="要提问的问题")
@click.option("--project", "-p", default=None, help="按项目名称过滤（可选）")
@click.option("--config", default="config/settings.yaml", help="配置文件路径")
@click.option("--top-k", default=8, show_default=True, help="检索召回数量")
@click.option("--top-n", default=5, show_default=True, help="重排后保留的结果数")
@click.option("--tau", default=0.5, type=float, show_default=True, help="相似度阈值（低于此视为无相关内容）")
@click.option("--guided", is_flag=True, help="启用引导式多轮逻辑（开发/排障用）")
def cli(question: str, project: str | None, config: str, top_k: int, top_n: int, tau: float, guided: bool):
    """基于已嵌入的项目文档进行问答。"""

    try:
        settings = Settings.from_yaml(config)
    except FileNotFoundError as e:
        click.echo(f"配置文件不存在: {e}", err=True)
        sys.exit(1)
    except Exception as e:  # pragma: no cover - config load errors
        click.echo(f"加载配置失败: {e}", err=True)
        sys.exit(1)

    # 初始化依赖
    click.echo("初始化向量检索与 LLM...")
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
    monitor = QAMonitor(settings=settings)
    qa_engine = QAEngine(store=store, llm_client=llm_client, monitor=monitor)

    # 执行问答
    if guided:
        from src.prompts import get_guided_templates
        from src.qa.dialogue_orchestrator import DialogueOrchestrator, DialogueState

        templates = get_guided_templates(getattr(settings.qa.guided, "templates_path", None))
        orchestrator = DialogueOrchestrator(
            qa_engine=qa_engine,
            templates=templates,
            llm_client=llm_client,
            gap_threshold=getattr(settings.qa.guided, "gap_similarity_threshold", 0.5),
        )
        state = DialogueState()
        if project:
            state.slots["project_name"] = project
        result = orchestrator.answer_with_guidance(question=question, state=state)
    else:
        result = qa_engine.answer(
            question=question,
            project_name=project,
            top_k=top_k,
            top_n=top_n,
            tau=tau,
        )

    click.echo(f"\n问题: {question}\n")

    status = result.get("status", "unknown")
    if status == "clarify":
        slots = result.get("slot_candidates", {}).get("project_name", [])
        click.echo(result.get("answer", "请补充项目信息"))
        if slots:
            click.echo("候选项目：")
            for idx, name in enumerate(slots, 1):
                click.echo(f"{idx}. {name}")
        sys.exit(0)

    if status == "no_context":
        click.echo("未找到相关内容，无法回答该问题。")
        sys.exit(0)

    if status == "error":
        click.echo(f"错误: {result.get('answer')}")
        if result.get("error"):
            click.echo(f"详情: {result['error']}")
        sys.exit(1)

    cache_status = result.get("cache_status")
    cache_level = result.get("cache_level")
    cache_prefix = ""
    if cache_status == "hit":
        cache_prefix = f"[cache hit/{cache_level or 'exact'}] "

    click.echo("回答:\n")
    click.echo(f"{cache_prefix}{result.get('answer', '')}")

    sources = result.get("sources", [])
    if sources:
        click.echo("\n来源:")
        for src in sources:
            similarity = src.get("similarity")
            sim_str = f" (相似度: {similarity})" if similarity is not None else ""
            click.echo(
                f"  - {src.get('project', 'N/A')} 第{src.get('slide_no', 'N/A')}页"
                f" (级别: {src.get('level', 'N/A')}){sim_str}"
            )

    if result.get("suggestions"):
        click.echo("\n推荐追问：")
        for idx, sug in enumerate(result["suggestions"], 1):
            click.echo(f"{idx}. {sug}")

    click.echo(f"\n状态: {status}")


if __name__ == "__main__":
    cli()
