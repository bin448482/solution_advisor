# coding: utf-8
import json
from textwrap import shorten
from typing import Any, Dict, List, Optional

from src.config import Settings
from src.embeddings import M3EEmbedding
from src.vectordb import ChromaStore

settings = Settings.from_yaml("config/settings.yaml")
settings = settings.with_overrides(vectordb_collection_name="project_slides")
embedding = M3EEmbedding(
    model_name=settings.embedding_model,
    device=settings.embedding_device,
    cache_dir=settings.embedding_cache_dir,
)
store = ChromaStore(
    persist_dir=settings.vectordb_persist_dir,
    collection_name=settings.vectordb_collection_name,
    embedding_model=embedding,
)

# ---- Retrieval knobs for this round ----
TOP_K = 8  # wider recall, rerank, then keep top 5
TOP_N_DISPLAY = 5
TAU = 0.5  # similarity threshold; below this we return “未找到相关内容”


def _default_project_filter(store: ChromaStore) -> Optional[Dict[str, Any]]:
    """Default to single-project filter to reduce noise; falls back to None."""
    projects = store.list_projects()
    if not projects:
        return None
    # Prefer the only project; if multiple, keep first for test consistency
    return {"project_name": projects[0]}

queries = [
    ("直接事实", "ChatBI的核心功能是什么？"),
    ("直接事实", "ChatBI支持哪些数据源？"),
    ("直接事实", "ChatBI的目标用户是谁？"),
    ("直接事实", "ChatBI的部署方式有哪些？"),
    ("概念性", "哪个项目可以帮助企业做数据分析？"),
    ("概念性", "有没有支持自然语言查询的产品？"),
    ("概念性", "哪些方案涉及到AI技术？"),
    ("概念性", "什么产品适合非技术人员使用？"),
    ("对比性", "ChatBI和其他BI产品的区别是什么？"),
    ("对比性", "哪些项目提到了云原生架构？"),
    ("对比性", "不同项目的技术栈对比"),
    ("细节", "ChatBI使用了哪些AI模型？"),
    ("细节", "系统的架构组件有哪些？"),
    ("细节", "有哪些集成接口？"),
    ("细节", "性能指标是多少？"),
    ("边界", "ChatBI的价格是多少？"),
    ("边界", "ChatBI支持区块链吗？"),
    ("边界", "ChatBI的创始人是谁？"),
    ("模糊", "数据可视化工具"),
    ("模糊", "智能问答系统"),
    ("模糊", "企业级应用"),
    ("模糊", "无代码开发"),
    ("多跳", "ChatBI适合什么规模的企业使用？"),
    ("多跳", "使用ChatBI需要什么技术背景？"),
]

report = []
project_filter = _default_project_filter(store)
for category, q in queries:
    guardrail_results = store.query_with_guardrails(
        q,
        top_k=TOP_K,
        top_n=TOP_N_DISPLAY,
        tau=TAU,
        where=project_filter,
    )

    entry = {"category": category, "query": q, "results": []}

    if not guardrail_results:
        entry["results"].append({"message": "未找到相关内容"})
        report.append(entry)
        continue

    for r in guardrail_results:
        entry["results"].append(
            {
                "id": r["id"],
                "project": r["metadata"].get("project_name"),
                "slide": r["metadata"].get("slide_no"),
                "level": r["metadata"].get("level"),
                "page_type": r["metadata"].get("page_type"),
                "similarity": round(r["similarity"], 4),
                "score": round(r["score"], 4),
                "text": shorten(r["document"].replace("\n", " "), width=200, placeholder="..."),
            }
        )
    report.append(entry)

with open("tmp_embedding_test_round1.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print("saved tmp_embedding_test_round1.json")
