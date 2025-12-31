# coding: utf-8
import json
from textwrap import shorten
from src.config import Settings
from src.embeddings import M3EEmbedding
from src.vectordb import ChromaStore

settings = Settings.from_yaml('config/settings.yaml')
settings = settings.with_overrides(vectordb_collection_name='project_slides')
embedding = M3EEmbedding(model_name=settings.embedding_model, device=settings.embedding_device, cache_dir=settings.embedding_cache_dir)
store = ChromaStore(persist_dir=settings.vectordb_persist_dir, collection_name=settings.vectordb_collection_name, embedding_model=embedding)

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
for category, q in queries:
    results = store.query(q, n_results=3, where=None)
    entry = {"category": category, "query": q, "results": []}
    for r in results:
        sim = 1 - r['distance'] if r.get('distance') is not None else None
        entry['results'].append({
            "id": r['id'],
            "project": r['metadata'].get('project_name'),
            "slide": r['metadata'].get('slide_no'),
            "level": r['metadata'].get('level'),
            "similarity": round(sim, 4) if sim is not None else None,
            "text": shorten(r['document'].replace('\n',' '), width=160, placeholder='...'),
        })
    report.append(entry)

with open('tmp_embedding_test_round1.json','w',encoding='utf-8') as f:
    json.dump(report,f,ensure_ascii=False,indent=2)
print('saved tmp_embedding_test_round1.json')
