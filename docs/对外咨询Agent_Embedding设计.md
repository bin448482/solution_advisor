# 对外咨询 Agent Embedding 设计方案

本文档描述了基于现有 PPT 解析流水线输出的 `PageSummary` 和 `ProjectProfile` 数据结构，构建售前咨询知识库的 Embedding 与检索策略。

## 核心策略：多粒度索引 (Multi-Granularity Indexing)

售前咨询场景的问题跨度极大（从宏观价值到微观参数），因此采用双层索引结构。

### 1. 索引层级划分

| 索引层级 | 对应数据源 | 目标问题类型 | 检索单元 |
| :--- | :--- | :--- | :--- |
| **Level 1: 页面级 (Detail Index)** | `PageSummary` | 具体功能、技术参数、架构细节、特定图表 | 单页 PPT |
| **Level 2: 项目级 (Project Index)** | `ProjectProfile` | 整体定位、核心价值、竞品对比、成功案例 | 整个项目 |

---

## 2. 向量化文本构建 (Text to Embed)

为了提升向量检索的准确性，需将结构化 JSON “拍平”为自然语言文本，并注入上下文信息。

### A. 页面级索引 (`PageSummary`)

**构建策略：** 上下文 + 核心结论 + 详细要点。

**文本模版：**
```text
项目名称: {Project Name}
页面类型: {signals 字段用逗号拼接}
标题: {title}
一句话总结: {one_liner}
详细内容:
- {bullet 1}
- {bullet 2}
...
补充细节: {details}
关键词: {entities 字段用逗号拼接}
```

**设计要点：**
*   **上下文注入**：必须包含 `项目名称`，防止不同项目的通用页面（如“系统架构”）混淆。
*   **权重优化**：`one_liner` 和 `title` 置前，利用 Embedding 模型的位置权重偏好。

### B. 项目级索引 (`ProjectProfile`)

**构建策略：** 提取项目核心要素，形成综述。

**文本模版：**
```text
项目: {project_name}
定位: {positioning}
目标用户: {target_users 拼接}
核心价值: {core_value}
核心能力: {core_capabilities 拼接}
差异化优势: {differentiators 拼接}
风险与限制: {risks_and_limits 拼接}
```

---

## 3. 元数据设计 (Metadata Schema)

元数据用于 **混合检索 (Hybrid Search)** 中的过滤阶段，其重要性不亚于向量本身。

| 字段名 | 来源字段 | 数据类型 | 用途示例 |
| :--- | :--- | :--- | :--- |
| `project_id` | 文件名/Hash | String | `filter={project_id: "chatbi_2025"}` (限定检索范围) |
| `slide_no` | `slide_no` | Int | `slide_no` 用于溯源引用 |
| `page_type` | `signals` | List[String] | `filter={page_type: "architecture"}` (查找架构图) |
| `entities` | `entities` | List[String] | `filter={entities: "Oracle"}` (查找特定技术栈) |
| `confidence` | `confidence` | Float | `filter={confidence: {gt: 0.8}}` (过滤低置信度内容) |
| `has_details` | (逻辑判断) | Bool | `filter={has_details: true}` (仅查找有详细描述的页面) |

---

## 4. 检索与增强流程 (RAG Workflow)

采用 **“父文档检索 (Parent Document Retrieval)”** 模式：

1.  **检索 (Search)**：使用构建好的“语义文本”进行向量匹配。
2.  **召回 (Retrieve)**：返回对应的 **原始 JSON** 对象（包含完整的结构化数据）。
3.  **生成 (Generate)**：
    *   将 JSON 中的 `details` (详细描述) 作为主要上下文。
    *   将 `bullets` (要点) 作为辅助信息。
    *   将 `evidence_map` (证据映射) 用于生成精确的引用标注。

---

## 5. 代码实现示例

```python
from src.models import PageSummary

def prepare_slide_embedding(project_name: str, summary: PageSummary) -> dict:
    """
    将 PageSummary 转换为向量数据库所需的文档格式。
    """
    # 1. 构建语义文本 (用于向量化)
    text_content = f"项目: {project_name}\n"
    text_content += f"页面标题: {summary.title}\n"
    text_content += f"核心总结: {summary.one_liner}\n"
    
    if summary.signals:
        text_content += f"类型: {', '.join(summary.signals)}\n"
        
    text_content += "关键点:\n"
    for bullet in summary.bullets:
        text_content += f"- {bullet}\n"
        
    if summary.details:
        text_content += f"详情: {summary.details}\n"
    
    # 关键词也加入文本，增加相关性
    if summary.entities:
        text_content += f"关键词: {', '.join(summary.entities)}\n"

    # 2. 构建元数据 (用于过滤)
    metadata = {
        "source": project_name,
        "slide_no": summary.slide_no,
        "type": summary.signals,  # 注意：需确认向量库是否支持列表类型
        "entities": summary.entities,
        "confidence": summary.confidence
    }

    # 3. 返回完整记录
    return {
        "id": f"{project_name}_{summary.slide_no}",
        "text": text_content,      # 向量化目标
        "metadata": metadata,      # 过滤目标
        "original_json": summary.model_dump_json() # 负载数据
    }
```