# PPT解析与项目画像：增量修复方案 (Refine Mode)

## 1. 背景与目标
在 PPT 解析过程中，由于 LLM 幻觉、输出格式错误或网络波动，部分幻灯片的总结可能质量不佳（置信度低）。全量重跑整个 PPT 解析流程（渲染 -> 提取 -> 总结 -> 画像 -> 向量化）耗时且昂贵。

**目标**：
1.  **精准定位**：自动识别置信度（Confidence）低于特定阈值（如 0.6）的页面。
2.  **增量更新**：仅重新处理低质量页面，保留高质量结果。
3.  **问题诊断**：在重试过程中尝试记录失败原因（如 JSON 解析失败、内容缺失等）。
4.  **数据一致性**：更新单页总结后，自动重新生成项目画像（Profile）并更新向量数据库。

## 2. 核心流程设计

### 2.1 扫描与诊断 (Scan & Diagnose)
系统将读取 `ppt_outputs/{project}/page_summaries/` 下的所有 JSON 文件。
*   **筛选条件**：`confidence < threshold` (默认 0.6)。
*   **诊断逻辑**：
    *   检查 JSON 完整性。
    *   (未来增强) 分析 `details` 字段，判断是否为 Fallback 文本。

### 2.2 执行修复 (Refine Execution)
对于筛选出的每一页：
1.  **上下文加载**：
    *   从原始 PPTX 中提取对应页的文本 (`SlideText`)。
    *   定位已存在的渲染图片 (`slides/{slide_no}.png`)，无需重新渲染。
2.  **LLM 重试**：
    *   调用 `PageSummarizer` 重新生成摘要。
    *   **改进点**：如果解析失败，记录具体的错误类型（如 `JSONDecodeError`），而不仅仅是静默 Fallback。
3.  **覆盖保存**：更新对应的 `{slide_no}.json` 文件。

### 2.3 全局聚合 (Re-aggregate)
单页修复完成后，全局数据必须刷新以保持一致性：
1.  **项目画像 (Profile)**：读取所有（包括已更新的）单页 JSON，重新生成 `project_profile.json`。
2.  **RAG/向量库**：
    *   重新生成 RAG 文档 (`rag_documents.json`)。
    *   **全量更新**：重新将所有文档插入向量数据库（覆盖或清空旧集合），确保检索数据的准确性。

## 3. 技术实现计划

### 3.1 命令行接口 (CLI)
修改 `src/__main__.py`，支持以下参数：
```bash
python -m src \
  --input ppts/example.pptx \
  --output ppt_outputs/example \
  --refine \
  --threshold 0.6
```

### 3.2 `PPTPipeline` 类扩展
在 `src/pipeline.py` 中新增 `refine` 方法：

```python
def refine(self, pptx_path: Path, output_dir: Path, threshold: float = 0.6) -> Dict:
    # 1. 扫描低置信度页面
    targets = self._scan_low_confidence(output_dir, threshold) 
    
    # 2. 如果有目标，进行重试
    if targets:
        self._reprocess_slides(pptx_path, output_dir, targets)
    
    # 3. 总是重新生成 Profile 和 VectorDB (只要进入 Refine 模式，通常意味着期望得到最新状态)
    self._regenerate_profile_and_rag(pptx_path, output_dir)
```

### 3.3 错误定位改进 (`PageSummarizer`)
修改 `src/summarizer/page_summarizer.py`：
*   在 `_parse_json` 失败时，不要立即填充默认值并设为 0.3。
*   在 `PageSummary` 模型中（或通过日志），透传原始错误信息。
*   例如：如果是 JSON 格式错误，尝试进行一次“自修复”提示（可选），或者明确标记为 `FormatError`。

## 4. 实施步骤
1.  **Refactor**: 修改 `PageSummarizer` 以支持更好的错误反馈。
2.  **Pipeline**: 实现 `refine` 逻辑。
3.  **CLI**: 暴露参数。
4.  **Test**: 构造一个包含低置信度页面的测试用例进行验证。

