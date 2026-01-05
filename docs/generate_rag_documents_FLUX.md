# 用于生成 rag_documents.json 的提示词（给 Claude Code / Codex）

## 你的角色
你是一个**RAG 知识预处理流水线的实现者**。你的任务不是写业务代码,而是**读取已有 JSON 输入,按照既定规范,生成一个新的聚合型知识文件 `rag_documents.json`**,用于后续向量化与检索。

---

## 项目背景
- **项目名称**:`FLUX富勒公司及产品介绍`
- **输入来源目录**:
  ```
  ppt_outputs/FLUX富勒公司及产品介绍/page_summaries/
  ```
- 该目录下包含多个 `*.json` 文件
- **每个 JSON 文件 = PPT 中 1 个 slide 的文字级总结**(已完成抽取与理解)

你的目标是:
> **读取该目录下所有 slide 级 JSON,总结、聚合、重组,生成一个标准化的 `rag_documents.json` 文件**。

---

## ⚠️ 特别注意:内容筛选原则

**本 PPT 包含公司介绍和产品介绍两部分内容,你需要:**

1. **聚焦产品介绍部分**:主要提取和沉淀 FLUX 产品相关的知识(如 FLUX WMS、FLUX Datahub 等产品的功能、架构、优势、案例等)
2. **忽略纯公司介绍内容**:如公司历史、团队介绍、企业文化、资质荣誉等与产品无关的内容
3. **保留产品相关的客户案例**:如果案例展示了产品的实际应用场景和价值,应当保留
4. **禁止编造信息**:如果某个 Category 下没有足够的产品相关内容,不要强行生成,可以跳过该 Category

**判断标准**:
- ✅ 保留:产品功能、技术架构、应用场景、客户案例、产品优势、集成能力等
- ❌ 忽略:公司发展历程、团队规模、企业愿景、办公环境、资质证书等

---

## 你要生成的最终文件

### 输出路径
```
ppt_outputs/FLUX富勒公司及产品介绍/embeddings/rag_documents.json
```

### 文件性质
- 这是一个 **数组 JSON**
- 每个元素称为一个 **ChunkDocument**
- 每个 chunk 是未来 RAG 检索的最小知识单元

---

## Chunk 类型总览(重点)

你需要生成以下类型的 chunk,其中 **`category_summary` 是主力、必须实现的类型**:

| chunk_type | 是否必须 | 粒度 | 说明 |
|---------|---------|------|------|
| category_summary | ✅ 必须 | Category | 同类 slide 的权威聚合摘要 + QA |
| qa_pair | 可选 | Slide | 单页问答(可保留已有逻辑) |
| metrics | 可选 | Slide | 指标类内容 |
| overview | 可选 | Project | 项目整体画像 |

> ⚠️ 如果资源有限,可以 **只生成 category_summary + overview**,这是可接受的最小实现。

---

## 核心任务:生成 category_summary(重点)

### Step 1:读取 page_summaries
- 遍历 `page_summaries/*.json`
- 每个文件通常包含:
  - slide_no
  - title / one_liner
  - bullets / details
  - entities / signals / category hints(如果有)

---

### Step 2:按 Category 对 slide 分桶

你需要把所有 slide summaries **聚合到有限个 Category 中**(推荐 6–10 个)。

#### 分类方式
- **优先规则法**(关键词 / signals / title)
- 如果规则无法判断,可使用 LLM 判断

示例 Category(示意,需根据实际内容调整):
- product_wms (FLUX WMS 仓储管理系统)
- product_datahub (FLUX Datahub 数据交换平台)
- product_other (其他产品,如有)
- architecture (技术架构与集成能力)
- deployment (部署方案与云化能力)
- use_cases (客户案例与应用场景)
- features_and_advantages (产品功能与竞争优势)

> Category 是实现细节,不要求与 PPT 页一一对应,而是"知识上的同类聚合"。
> **重要**:如果某个 Category 下只有公司介绍内容而无产品内容,应跳过该 Category。

---

### Step 3:为每个 Category 生成一个聚合 Chunk

对于 **每一个有产品相关 slide 命中的 Category**,生成 **且仅生成 1 条** `category_summary` chunk。

#### 你需要做的事
对该 Category 下的所有产品相关 slide summaries:
1. **整体阅读、消化**
2. 抽象出一个**权威、稳定、不依赖单页的总结**
3. 生成高质量问答,用于真实用户提问场景

---

## category_summary 的内容要求

### 1️⃣ summary(必须)
- 字数:**200–300 中文字**
- 内容必须覆盖:
  - 能力说明
  - 适用场景
  - 核心价值
  - 限制 / 边界(如果原文提到)
- **禁止编造 PPT 未提及的能力**
- **只总结产品相关内容,不包含公司背景信息**

---

### 2️⃣ qa_examples(必须)

- 数量:**3–5 条**
- 每条包含:
  ```json
  {
    "question": "",
    "answer": "",
    "source_slide_refs": [1, 3, 7]
  }
  ```
- answer:
  - ≤ 200 字
  - 必须完全基于该 Category 的 slide summaries
  - 聚焦产品功能、特性、应用场景等
- source_slide_refs:
  - 来自 page_summaries 的 slide_no
  - 去重、排序

---

## category_summary Chunk 的标准结构

```json
{
  "id": "FLUX富勒公司及产品介绍_category_<category_id>",
  "text": "<summary + QA 的可读拼接文本>",
  "metadata": {
    "project_name": "FLUX富勒公司及产品介绍",
    "chunk_type": "category_summary",
    "level": "category",
    "category_id": "<category_id>",
    "category_name": "<可读名称>",
    "summary": "<200–300 字摘要>",
    "qa_examples": [ ... ],
    "source_slide_refs": [1, 2, 5],
    "source_files": [
      "page_summaries/001.json",
      "page_summaries/002.json"
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

`text` 用于向量化,应为**可自然阅读的文本**,建议结构:

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

## 重要约束(非常重要)

1. ❌ **禁止编造 PPT 中未出现的信息**
2. ❌ 不要复制单页原文堆砌
3. ❌ **不要包含纯公司介绍内容**(如公司历史、团队、资质等)
4. ✅ 必须体现"跨 slide 的抽象能力"
5. ✅ `source_slide_refs` 和 `source_files` 必须可追溯
6. ✅ **聚焦产品知识沉淀**,确保生成的内容对产品咨询有实际价值
7. ⚠️ 一个 Category **只能有一个 category_summary chunk**

---

## 最终输出检查清单

在写出 `rag_documents.json` 前,请确保:

- [ ] JSON 是合法数组
- [ ] 每个 category 至少有 1 个产品相关 slide 来源
- [ ] 每个 category_summary 都有 summary + qa_examples
- [ ] 所有 slide_no 均真实存在
- [ ] 字段命名严格一致
- [ ] **内容聚焦产品,不包含纯公司介绍**
- [ ] **没有编造 PPT 中不存在的产品功能或特性**

---

## 你现在要做的事

1. 读取 `ppt_outputs/FLUX富勒公司及产品介绍/page_summaries/*.json`
2. **筛选出产品相关的 slide**,忽略纯公司介绍内容
3. 完成分类 → 聚合 → 总结 → QA 生成
4. 输出 `ppt_outputs/FLUX富勒公司及产品介绍/embeddings/rag_documents.json`

**不要输出解释性文字,只生成结果文件。**

---

> 这是一个"知识工程任务",而不是简单的格式转换任务。请以"长期可复用的 RAG 知识资产"为目标进行处理,确保沉淀的是**产品知识**而非公司宣传内容。
