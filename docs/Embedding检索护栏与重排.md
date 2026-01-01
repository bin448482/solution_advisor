# Embedding 检索护栏与重排（落地说明）

更新时间：2025-12-31

## 目标
- 防止低相关回答：Top-1 相似度 < 0.5 时直接返回空。
- 提升细节页曝光：在排序中为数据源/部署/API/性能/技术栈等细节页加权。
- 保持易用：提供统一包装函数，API 层可直接调用。

## 实施位置
- 代码：`src/vectordb/chroma_store.py` 新增 `query_with_guardrails(...)`。
- 测试：`tmp_run_tests.py` 已改为调用同一逻辑，生成 `tmp_embedding_test_round1.json`。

## 默认行为
- **项目过滤**：若未显式传 `where`，自动用单一项目的 `project_name` 过滤；多项目时不强制过滤，可传参指定。
- **召回与重排**：`top_k=8` 召回 → 相似度 + 细节页/slide 加分重排 → 取 `top_n=5`。
- **阈值护栏**：Top-1 `similarity < 0.5` 时返回空列表（由上层决定文案）。
- **page_type 规范化**：将原始 `page_type` 归一到 `data_sources/deployment/api/performance/tech_stack/architecture`，供加分与前端展示。

## 使用示例
```python
from src.vectordb import ChromaStore

results = store.query_with_guardrails(
    "ChatBI的部署方式有哪些？",
    project_name="ChatBI / Chat BI（AI for BI 智能数据分析产品）",
    top_k=8,
    top_n=5,
    tau=0.5,
)
if not results:
    return "未找到相关内容"
```

自定义过滤：
```python
results = store.query_with_guardrails(
    "对比不同项目的技术栈",
    where={"project_name": {"$in": ["ProjA", "ProjB"]}},
)
```

## page_type 归一化策略
- 按关键词模糊匹配到小集合：`data_sources`, `deployment`, `api`, `performance`, `tech_stack`, `architecture`。
- 若无法命中，保留原字符串，避免信息丢失。
- 加分依据：出现上述细节类或文本命中细节关键词。

## 影响面
- 无破坏性变更：原 `query()` 行为不变。
- 上层调用可渐进替换为 `query_with_guardrails()` 以获得一致的护栏与排序。

## 后续迭代建议
1. 扩充 page_type 关键词表，覆盖“安全/合规/成本”等更多细粒度标签。
2. 在导入阶段（rag_documents 生成）直接写入规范化的 page_type，减少运行时开销。
3. 增加集成测试：跨项目对比与边界问句触发空结果的用例。
