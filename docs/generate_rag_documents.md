# 用于生成 rag_documents.json 的提示词（给 Claude Code / Codex）

## 你的角色
你是一个**RAG 知识预处理流水线的实现者**。你的任务不是写业务代码，而是**读取已有 JSON 输入，按照既定规范，生成一个新的聚合型知识文件 `rag_documents.json`**，用于后续向量化与检索。

---

## 项目背景
- **项目名称**：`ChatBI产品介绍_2025`
- **输入来源目录**：
  ```
  ppt_outputs/ChatBI产品介绍_2025/page_summaries/
  ```
- 该目录下包含多个 `*.json` 文件
- **每个 JSON 文件 = PPT 中 1 个 slide 的文字级总结**（已完成抽取与理解）

你的目标是：
> **读取该目录下所有 slide 级 JSON，总结、聚合、重组，生成一个标准化的 `rag_documents.json` 文件**。

---

## 你要生成的最终文件

### 输出路径
```
ppt_outputs/ChatBI产品介绍_2025/embeddings/rag_documents.json
```

### 文件性质
- 这是一个 **数组 JSON**
- 每个元素称为一个 **ChunkDocument**
- 每个 chunk 是未来 RAG 检索的最小知识单元

---

## Chunk 类型总览（重点）

你需要生成以下类型的 chunk，其中 **`category_summary` 是主力、必须实现的类型**：

| chunk_type | 是否必须 | 粒度 | 说明 |
|---------|---------|------|------|
| category_summary | ✅ 必须 | Category | 同类 slide 的权威聚合摘要 + QA |
| qa_pair | 可选 | Slide | 单页问答（可保留已有逻辑） |
| metrics | 可选 | Slide | 指标类内容 |
| overview | 可选 | Project | 项目整体画像 |

> ⚠️ 如果资源有限，可以 **只生成 category_summary + overview**，这是可接受的最小实现。

---

## 核心任务：生成 category_summary（重点）

### Step 1：读取 page_summaries
- 遍历 `page_summaries/*.json`
- 每个文件通常包含：
  - slide_no
  - title / one_liner
  - bullets / details
  - entities / signals / category hints（如果有）

---

### Step 2：按 Category 对 slide 分桶

你需要把所有 slide summaries **聚合到有限个 Category 中**（推荐 6–10 个）。

#### 分类方式
- **优先规则法**（关键词 / signals / title）
- 如果规则无法判断，可使用 LLM 判断

示例 Category（示意）：
- product_overview
- architecture
- core_features
- analytics_capability
- security_and_governance
- use_cases
- roadmap_or_future

> Category 是实现细节，不要求与 PPT 页一一对应，而是“知识上的同类聚合”。

---

### Step 3：为每个 Category 生成一个聚合 Chunk

对于 **每一个有 slide 命中的 Category**，生成 **且仅生成 1 条** `category_summary` chunk。

#### 你需要做的事
对该 Category 下的所有 slide summaries：
1. **整体阅读、消化**
2. 抽象出一个**权威、稳定、不依赖单页的总结**
3. 生成高质量问答，用于真实用户提问场景

---

## category_summary 的内容要求

### 1️⃣ summary（必须）
- 字数：**200–300 中文字**
- 内容必须覆盖：
  - 能力说明
  - 适用场景
  - 核心价值
  - 限制 / 边界（如果原文提到）
- **禁止编造 PPT 未提及的能力**

---

### 2️⃣ qa_examples（必须）

- 数量：**3–5 条**
- 每条包含：
  ```json
  {
    "question": "",
    "answer": "",
    "source_slide_refs": [1, 3, 7]
  }
  ```
- answer：
  - ≤ 200 字
  - 必须完全基于该 Category 的 slide summaries
- source_slide_refs：
  - 来自 page_summaries 的 slide_no
  - 去重、排序

---

## category_summary Chunk 的标准结构

```json
{
  "id": "ChatBI产品介绍_2025_category_<category_id>",
  "text": "<summary + QA 的可读拼接文本>",
  "metadata": {
    "project_name": "ChatBI产品介绍_2025",
    "chunk_type": "category_summary",
    "level": "category",
    "category_id": "<category_id>",
    "category_name": "<可读名称>",
    "summary": "<200–300 字摘要>",
    "qa_examples": [ ... ],
    "source_slide_refs": [1, 2, 5],
    "source_files": [
      "page_summaries/slide_001.json",
      "page_summaries/slide_002.json"
    ]
  },
  "original_json": {
    "source_files": ["..."],
    "qa_count": 4
  }
}
```

---

## text 字段拼接规范

`text` 用于向量化，应为**可自然阅读的文本**，建议结构：

```
【Category】XXX
【Summary】
<summary>

【Representative Q&A】
Q1: ...
A1: ...
Q2: ...
A2: ...
```

---

## 重要约束（非常重要）

1. ❌ **禁止编造 PPT 中未出现的信息**
2. ❌ 不要复制单页原文堆砌
3. ✅ 必须体现“跨 slide 的抽象能力”
4. ✅ `source_slide_refs` 和 `source_files` 必须可追溯
5. ⚠️ 一个 Category **只能有一个 category_summary chunk**

---

## 最终输出检查清单

在写出 `rag_documents.json` 前，请确保：

- [ ] JSON 是合法数组
- [ ] 每个 category 至少有 1 个 slide 来源
- [ ] 每个 category_summary 都有 summary + qa_examples
- [ ] 所有 slide_no 均真实存在
- [ ] 字段命名严格一致

---

## 你现在要做的事

1. 读取 `ppt_outputs/ChatBI产品介绍_2025/page_summaries/*.json`
2. 完成分类 → 聚合 → 总结 → QA 生成
3. 输出 `ppt_outputs/ChatBI产品介绍_2025/embeddings/rag_documents.json`

**不要输出解释性文字，只生成结果文件。**

---

> 这是一个“知识工程任务”，而不是简单的格式转换任务。请以“长期可复用的 RAG 知识资产”为目标进行处理。

