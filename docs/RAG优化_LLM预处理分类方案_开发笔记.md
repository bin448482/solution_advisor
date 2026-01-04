# 开发笔记：LLM 预处理分类与类别摘要（重写版）

**日期**：2026-01-03  
**目标**：按 Category 聚合 `page_summaries`，用 LLM 生成权威摘要 + 代表问答，减少对纯向量相似度的依赖。

---

## 1) 方案概要
```
PPT → slides + page_summaries
          ↓
   分桶到 8 类 Category（规则/LLM）
          ↓
[Category Summarizer]
  - 聚合该类相关的 page_summaries
  - 生成 summary + qa_examples
  - 输出 category_summary chunk (level=category)
          ↓
可选：qa_pair / metrics / overview
          ↓
rag_documents.json → Chroma
```

## 2) 设计要点
- **主力块 = category_summary**：每类 1 条，内容包含
  - `summary`（200~300 字权威描述）
  - `qa_examples`（3~5 条问答，含来源 slide_no）
  - 追溯：`source_files` & `source_slide_refs`
- **QA 生成降级为补充**：保留单页 QA 但检索优先 `category_summary`。
- **元数据扩展**：`metadata.summary`、`metadata.qa_examples` 仅在 `category_summary` 中出现；`original_json` 精简为来源信息。
- **分类策略**：
  - 默认规则分桶：基于 `title/one_liner/entities/signals` 关键词映射 8 类。
  - 开关 `enable_llm_classify` 后，用 LLM 对 page_summary 做多标签分类，再聚合。
- **成本控制**：每类一次 LLM 调用，最多 8 次；比逐页分类低。

## 3) 生成流程（伪代码）
```python
summaries = load_page_summaries()
category_map = bucket_by_category(summaries)   # 规则或 LLM

category_chunks = []
for cat, slides in category_map.items():
    prompt = render_prompt(cat, slides)        # 包含标题/要点/细节，限制总字数
    resp = llm.generate(prompt)
    data = parse(resp)  # summary + qa_examples
    chunk = ChunkDocument(
        id=f"{project}_category_{cat}",
        text=compose_text(data),
        metadata={
            "project_name": project,
            "chunk_type": "category_summary",
            "level": "category",
            "category_id": cat,
            "category_name": get_category_name(cat),
            "summary": data["summary"],
            "qa_examples": data["qa_examples"],
            "source_slide_refs": slide_nos(slides),
            "source_files": source_files(slides),
        },
        original_json=json.dumps({
            "source_files": source_files(slides),
            "qa_count": len(data["qa_examples"]),
        }, ensure_ascii=False)
    )
    category_chunks.append(chunk)
```

## 4) Prompt 草案（摘要 + QA）
```
你是资深技术文档整理专家，请基于给定的幻灯片摘要，为指定类别生成权威说明。

【类别】{category_id} - {category_name}
【项目】{project_name}
【相关幻灯片摘要】(最多 8 条，已截断)
1) 标题: ... ; 要点: ... ; 细节: ...
...

要求：
1. 写出 200~300 字“类别摘要”，覆盖能力/场景/价值/限制（如有）。
2. 给出 3~5 条代表性问答，格式：
   - question: ...
   - answer: ... (≤200 字，基于以上内容，不要编造)
   - source_slide_refs: [3,5]  # 使用提供的 slide 编号
3. 输出 JSON：
{
  "summary": "...",
  "qa_examples": [
    {"question": "...", "answer": "...", "source_slide_refs": [3]}
  ]
}
```

## 5) 追溯与字段规范
- `metadata.summary`：类别摘要正文（与 text 同步，便于元数据消费）。
- `metadata.qa_examples`：数组，元素含 `question/answer/source_slide_refs`。
- `source_slide_refs`: 去重排序；`source_files`: `page_summaries/xxx.json` 列表。
- `original_json`: 只存来源信息 `{source_files, qa_count}`。

## 6) 错误与降级
- LLM 失败：记录 errors，跳过该类；可回落到拼接式摘要（简易 fallback）。
- 分桶为空：类别无相关 slide 时不生成 chunk。
- 输出校验：缺字段或超长时重试一次；再失败则降级。

## 7) 检索侧建议
- 默认优先返回 `category_summary`，再补充同类的 `qa_pair`（可按 `category_id` 过滤）。
- `query_with_qa_ranking` 可增加一条规则：`chunk_type=category_summary` 给予 1.3x 乘子。

## 8) 开发任务清单
1. **ChunkMetadata**：已支持 `summary/qa_examples/source_files`（确认字段落盘）。  
2. **新增 CategorySummarizer**：输入 `Dict[Category, List[PageSummary]]` 输出 `ChunkDocument` 列表。  
3. **Pipeline**：在 RAGPrep / refine 插入“聚合+摘要”步骤，替换当前拼接式生成。  
4. **Config**：`enable_category_summary_chunks` 控制；新增 `max_slide_per_category`、`qa_examples_per_cat`。  
5. **Tests**：单测 mock LLM，断言 `category_summary` 的 metadata/text 结构；E2E mock 流程至少生成 1 类。  
6. **Docs**：同步 AGENTS/README（待做）。  

## 9) 风险与缓解
- 摘要编造风险：提示中明确“仅基于提供摘要”，并限制长度；可比对 `source_slide_refs` 抽查。
- 成本：按类别调用，成本固定上限；可限制每类输入 slides ≤8，截断细节。
- 语义漂移：temperature=0.1；必要时加入少量原文引用（短句）防漂移。

## 10) 后续迭代
- 二级分类支持（如 architecture.backend / architecture.security）。
- 类别分布统计与质检报表。
- 缓存类别摘要（hash(page_summaries)）避免重复调用。
- 混合检索：BM25 + 向量 + 类别过滤。

---

**状态**：设计定稿，待开发与验证。***
