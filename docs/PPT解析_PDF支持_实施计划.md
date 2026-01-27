# PPT解析_PDF支持_实施计划

## 1. 范围与目标
- 目标：在现有 **Stage 1 渲染（Capture）** 与 **Stage 2 解析（Interpret）** 中支持 PDF 输入，且 **PDF 场景不做文本抽取**，直接由 LLM 解析图片。
- 输入范围：`*.pdf`（优先从 `pdfs/` 目录加载）。
- 输出一致性：仍输出到 `ppt_outputs/<name>/`，包含 `slides/`、`page_summaries/`、`manifest.json` 等。
- 非目标：不新增 OCR；PDF 的文字内容不进行结构化抽取。

## 2. 现状与验证结论
- Stage 1 现状：`renderer/libreoffice.py` 负责 **PPTX → PDF → PNG**（LibreOffice + Poppler `pdftoppm`）。
- Stage 2 现状：`PageSummarizer.summarize(SlideText, image_path)` 强依赖 `SlideText`。
- **PDF → PNG 渲染可复用**：已用 `pdftoppm` 对 `pdfs/AI驱动的新一代智能软件测试最新版-智穹云启-202508-精简版.pdf` 全量渲染，生成 `page-01.png … page-27.png`，输出正常（仅字体类型不匹配警告）。

## 3. 重构方案（按你选择的策略）
### 3.1 输入类型识别（统一入口）
- 在 pipeline 入口统一识别输入后缀（`.pptx` / `.pdf`）。
- 新增 `input_type` 分支，只在入口做判断，后续 Stage 复用。

### 3.2 Stage 1 渲染（PDF 复用链路）
- **原则**：直接复用 `pdftoppm` 渲染链路，跳过“PPTX → PDF”步骤。
- **落地方式**：
  - 输入为 PDF 时，调用 `pdftoppm` 生成 `slides/001.png`…（与 PPTX 输出命名保持一致）
  - 渲染仍由 `renderer` 层负责
- **依赖**：仅需 Poppler（已有），不新增渲染依赖。

### 3.3 Stage 2 解析（PDF 走纯图片模式）
- **核心要求**：`PageSummarizer` 支持 `slide_text=None`，并自动切换到 **纯图片 prompt**。
- **做法**：
  - 扩展 `PageSummarizer.summarize(...)`：允许 `slide_text` 为空；
  - 当 `slide_text is None` 时，构造“image-only” prompt（禁用文本输入、强调视觉内容）；
  - 复用现有的 JSON 解析与默认填充逻辑，避免结构回归。
- **兼容性**：PPTX 流程仍使用 `SlideText` + 图片，逻辑不变。

### 3.4 Pipeline 兼容与复用
- `pipeline.py` 入口分支：
  - `.pptx`：走现有 `extract` → `interpret`
  - `.pdf`：跳过 `extract`，直接生成“空 SlideText 占位”或将 `None` 传递给 `PageSummarizer`（推荐直接 `None`）
- `interpret` 阶段对 `slide_texts` 的强依赖需解除：
  - 若为 PDF，改为使用渲染出来的 `image_map` 作为分页来源；
  - 保持 `page_summaries/*.json` 输出结构一致。

### 3.5 产物与目录
- PDF 仍写入 `ppt_outputs/<name>/`：
  - `slides/` PNG
  - `page_summaries/`（单页总结 JSON）
  - `manifest.json`
- `slide_texts.jsonl` 可不生成或置空（需在 manifest 记录“PDF-ImageOnly 模式”）。

## 4. 里程碑与任务拆解
### M1：入口识别与渲染复用（0.5 天）
- [ ] 在 `pipeline.py` 统一识别 `.pdf` / `.pptx`
- [ ] PDF 直接走 `pdftoppm` 渲染，产物命名对齐

### M2：PageSummarizer 兼容（1 天）
- [ ] `PageSummarizer` 支持 `slide_text=None`
- [ ] 新增“image-only prompt”分支
- [ ] JSON 解析/默认填充逻辑保持兼容

### M3：Pipeline 适配（0.5 天）
- [ ] PDF 跳过 `extract`，`interpret` 基于图片分页运行
- [ ] 产物与 manifest 记录一致

### M4：测试与文档（0.5 天）
- [ ] 使用 `pdfs/` 样例跑通 Stage1+2
- [ ] PPTX 样例回归（确保原逻辑不回归）
- [ ] 更新 `README_CN.md` 与模块 `AGENTS.md`

## 5. 依赖与配置
- **无新增依赖**（PDF 场景不做文本抽取）。
- 现有依赖复用：`pdftoppm`（Poppler）用于渲染。

## 6. 风险与对策
- **纯图片理解不稳定**：无文本辅助，LLM 质量波动 → 建议在 prompt 中强化“仅基于可见内容”与“低置信标注”。
- **页数/命名不一致**：依赖渲染页数 → 以 PNG 页数作为分页基准。
- **回归风险**：PPTX 仍需文本+图片 → 保持原逻辑路径不变，增加回归测试。

## 7. 验收标准
- 支持 `python -m src --input pdfs/<file>.pdf --output ppt_outputs/<name>` 跑通 Stage1+2。
- 生成 `slides/*.png` 与 `page_summaries/*.json`，页数对齐。
- PPTX 流程不回归（可跑 `ppts/` 样例）。
- `manifest.json` 记录“PDF-ImageOnly 模式”与错误信息。

## 8. 上线与回滚
- 上线：合并代码 + 更新文档说明。
- 回滚：关闭 PDF 分支（仅保留 PPTX 路径），保留新增逻辑以便后续恢复。
