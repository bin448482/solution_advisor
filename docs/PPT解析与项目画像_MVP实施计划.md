# PPT解析与项目画像系统 - 实施计划 (v2: RAG准备集成版)

## 项目概述

实现一个自动化流水线，将项目介绍类PPT转换为结构化的项目画像，并自动生成用于售前咨询RAG（检索增强生成）的向量化数据。

- **输入**：PPTX文件（如 `ppts/ChatBI产品介绍_2025.pptx`）
- **输出**：
  1. **可视化**：逐页图片 (PNG)
  2. **结构化数据**：单页总结 (JSON) + 项目画像 (JSON)
  3. **RAG数据**：向量数据库导入文件 (JSONL/JSON)，包含“语义文本”与“元数据”
- **目标**：可追溯、可批处理、可运营、**即刻可搜**

## 技术选型

- **语言**：Python 3.9+
- **PPT渲染**：LibreOffice headless + Poppler
- **文本提取**：python-pptx
- **LLM框架**：LangChain（支持多种LLM提供商）
- **数据验证**：Pydantic 2.0+
- **CLI框架**：Click

## 系统架构 (更新)

```
PPTX输入
  ↓
[Renderer] → slides/*.png
  ↓
[Extractor] → 原始文本
  ↓
[PageSummarizer] → page_summaries/*.json (并行)
  ↓
[ProfileGenerator] → doc_summary/project_profile.json
  ↓
[RAGPreparer] (新增) → embeddings/rag_documents.json
  ↓
[Pipeline] → manifest.json
```

## 目录结构 (更新)

```
src/
├── __init__.py
├── __main__.py                 # CLI入口
├── config.py                   # 配置管理
├── models.py                   # Pydantic数据模型 (含Manifest更新)
├── rag.py                      # (新增) Embedding数据准备逻辑
├── pipeline.py                 # (更新) 集成RAG准备步骤
├── renderer/
│   └── libreoffice.py          # LibreOffice实现
├── extractor/
│   └── ppt_extractor.py        # PPT文本提取
├── summarizer/
│   ├── llm_client.py           # LLM API封装
│   ├── page_summarizer.py      # 单页总结
│   └── profile_generator.py    # 项目画像生成
└── utils.py                    # 工具函数
```

## 核心组件设计

### 1. 数据模型 (src/models.py)

**新增**：
- **Manifest**: 增加 `rag_documents: int` 字段，记录生成文档数量。

### 2. 渲染与提取 (src/renderer/, src/extractor/)
*保持原有设计：LibreOffice 渲染 + python-pptx 提取*

### 3. LLM 总结模块 (src/summarizer/)
*保持原有设计：PageSummarizer 生成单页 JSON，ProfileGenerator 生成项目画像*

### 4. RAG准备器 (src/rag.py) - 新增核心模块

**功能**：将结构化数据转换为适合向量检索的文档格式（多粒度索引）。

**核心逻辑 (基于 Embedding设计文档)**：
1.  **Slide Level (Detail Index)**：
    - 读取 `PageSummary`
    - 构建语义文本：`项目名 + 标题 + 核心总结 + 要点 + 详情`
    - 注入元数据：`slide_no`, `page_type`, `entities`
2.  **Project Level (Project Index)**：
    - 读取 `ProjectProfile`
    - 构建综述文本：`定位 + 价值 + 能力 + 差异化`
    - 注入元数据：`level="project"`
3.  **输出**：生成 `rag_documents.json`，列表包含所有待 Embedding 的对象。

### 5. 噪声处理与健壮性（新增）

- **解析容错**：`PageSummarizer._parse_json` 需兼容 LLM 返回的 `list`，当首元素为 `dict` 时取首元素再走 `_fill_defaults`，避免原始字符串落入 `details/bullets`。
- **数据清洗钩子**：在生成 `rag_documents` 前，对疑似“嵌套 JSON 字符串”的 `details` 做解包，规则示例：
  - 判定：`details` 以 `[` 或 `{` 开头，且包含常见键（如 `"slide_no"`, `"title"`, `"one_liner"`, `"bullets"` 等）时，尝试 `json.loads`。
  - 解析：若结果为 `list[dict]` 取首元素；为 `dict` 则直接用；提取其中的 `details` 与 `bullets` 覆盖当前值。
  - 失败回退：解包失败保持原文本，避免数据丢失。
- **双通道信息源（可选增强）**：在单页摘要中新增 `image_caption` 字段存放纯视觉描述；RAG 文档优先使用 `image_caption + one_liner + bullets`，`details` 为补充，降低结构化失败噪声。
- **验证**：`manifest` 持续记录 `page_summaries`、`rag_documents` 计数；若检测到回退（如 bullets 含 `[`、`"slide_no"`），将错误写入 `errors`，便于重跑或清洗。

### 6. 流程编排 (src/pipeline.py)

**PPTPipeline 类更新**：
- 在 `ProjectProfile` 生成后，调用 `src.rag` 模块。
- 生成 RAG 文档并保存至 `embeddings/` 目录。
- 统计生成数量并写入 `manifest.json`。

## 实施步骤 (更新后)

### Phase 1: 基础流水线 (已完成)
- [x] Day 1: 项目基础 (`models.py`, `config.py`)
- [x] Day 2: 渲染模块 (`renderer/`)
- [x] Day 3: 文本提取 (`extractor/`)
- [x] Day 4: LLM客户端 (`llm_client.py`)
- [x] Day 5: 单页总结 (`page_summarizer.py`)
- [x] Day 6: 项目画像 (`profile_generator.py`)

### Phase 2: RAG数据集成 (当前阶段)
- [x] **Day 7.1: RAG模块实现**
    - 创建 `src/rag.py`
    - 实现 `prepare_slide_embedding` (单页转向量文档)
    - 实现 `prepare_project_embedding` (画像转向量文档)
- [x] **Day 7.2: 流水线集成**
    - 修改 `src/models.py` 增加 Manifest 字段
    - 修改 `src/pipeline.py` 集成 RAG 模块
    - 验证输出 `ppt_outputs/<name>/embeddings/rag_documents.json`

### Phase 3: 交付与运维
- [ ] **Day 8: 端到端测试与文档**
    - 运行完整流程，检查 RAG 数据格式
    - 编写使用文档，说明如何将 JSON 导入向量库 (Milvus/Chroma/ES)

## 输出文件规范

**embeddings/rag_documents.json** 示例：
```json
[
  {
    "id": "ChatBI_2025_slide_001",
    "text": "项目: ChatBI...\n页面标题: 架构...\n关键点: ...",
    "metadata": {
      "source": "ChatBI_2025",
      "slide_no": 1,
      "page_type": ["architecture"],
      "entities": ["LLM", "Python"],
      "level": "slide"
    },
    "original_json": "{...}"
  },
  {
    "id": "ChatBI_2025_overview",
    "text": "项目综述: ChatBI...\n定位: ...",
    "metadata": {
      "level": "project"
    },
    "original_json": "{...}"
  }
]
```

## 验收标准

1. ✅ `ppt_outputs` 下生成 `embeddings/rag_documents.json`。
2. ✅ JSON 内容符合多粒度设计（包含 Slide 和 Project 两类文档）。
3. ✅ 文本内容是自然的描述性语言，而非原始 JSON 字符串。
4. ✅ 元数据包含用于过滤的关键字段（type, entities）。
5. ✅ `manifest.json` 正确记录 `rag_documents` 数量。
