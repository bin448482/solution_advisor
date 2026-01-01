# Embedding 检索优化实施方案（第 1 轮后）

更新时间：2025-12-31  
覆盖范围：现有 `ChatBI产品介绍_2025` 项目向量库（41 条文档，collection=`project_slides`）。

## 本次落地进展（2025-12-31）
- 生产侧封装：`ChromaStore.query_with_guardrails`（src/vectordb/chroma_store.py）提供默认项目过滤、Top-K=8 召回、细节页+slide 加分重排、0.5 相似度阈值护栏，供 API 直接复用。
- page_type 归一：查询阶段对 page_type 进行关键词标准化（data_sources/deployment/api/performance/tech_stack/architecture），保证加分稳定；后续可在导入阶段写入规范化值。
- 测试侧同步：`tests/tmp_run_tests.py` 改为调用同一包装函数，生成新版 `tests/tmp_embedding_test_round1.json` 以便与上一轮对比。

## 一、现状回顾
- 本轮测试脚本：`tests/tmp_run_tests.py`，输出：`tests/tmp_embedding_test_round1.json`。  
- Top-1 平均相似度（23 条查询）：直接事实 0.77、概念性 0.77、对比性 0.76、细节 0.73、模糊 0.76、多跳 0.79、边界 0.74。  
- 主要问题：
  - **结果集中**：大多数命中 overview / 对比页，细节页（数据源、部署、接口）曝光不足。
  - **边界查询失效**：价格/区块链/创始人类问题仍返回高分（未拒答）。
  - **跨项目对比不可测**：仅 1 个项目，无法验证对比类语义。
  - **排序缺少多样性**：无再排序/置信度约束，导致高频页占位。

## 二、优化目标
1) 直接事实 & 细节类 Top-1/Top-3 相关性显著提升（目标 Top-1 ≥0.82，细节类 ≥0.80）。  
2) 边界类查询在 Top-1 相似度 <0.5 时返回“无相关”，避免幻觉。  
3) 查询结果多样化：细节页（数据源/部署/接口/性能）在 Top-3 中至少出现 1 条。

## 三、落地策略
### 1. 查询侧（无需改数据）
- **添加相似度阈值与空结果返回**  
  - 应用层：若 `1 - distance < 0.5`，返回“未找到相关内容”。  
  - CLI 可在测试脚本中先行实现，后移植到服务层。
- **默认启用 project 过滤**  
  - 调用 `store.query(..., where={"project_name": "<项目名>"})`，减少跨项目噪声；对跨项目对比再去掉过滤。
- **提升细节页优先级**  
  - 在查询结果中按 `level=slide`、`page_type` 包含 `["tech_stack","data_sources","deployment","api"]` 的加权排序（轻量 rerank）。
- **Top-K 调整**  
  - 查询默认 `top_k=8`，重排后取 Top-5 展示，提高召回再控排序。

### 2. 数据侧（轻量改造）
- **补齐关键摘要字段**  
  - 确认 `rag_documents.json` 中“数据源/部署/接口/性能”页的 `summary`/`clean_summary_for_embedding` 具备关键词；必要时手动修订对应 `page_summaries/*`.
- **元数据规范**  
  - 确保 `metadata` 包含：`project_name`、`level`、`slide_no`、`page_type`（数组）且数组已 JSON 字符串化；缺失项需补。
- **负面示例标注**（可选）  
  - 为不存在的信息添加少量“拒答”模板文档，page_type=`guardrail`，用于把关相似度 <0.5 的情况。

### 3. 排序与护栏（代码层）
- **轻量 reranker**：在 `store.query` 结果后，按以下规则重排：  
  1) 相似度得分；2) page_type 命中关键类 +0.03；3) level=slide 优先于 project；4) guardrail 文档仅在阈值下触发拒答。  
- **阈值护栏**：统一在服务/CLI 层封装 `apply_threshold(results, tau=0.5)`，空结果返回标准文案。

## 四、实施步骤
1) **数据检查/修订（若需）**  
   - 打开 `ppt_outputs/ChatBI产品介绍_2025/page_summaries/*.json`，检查关键页摘要；必要时微调后重新生成 `rag_documents.json`。  
2) **重新导入向量库**  
   ```powershell
   Remove-Item -Recurse -Force chroma_db
   $env:HF_HUB_OFFLINE=1; python -m src.scripts.vectordb_cli batch-import --input-dir ppt_outputs
   $env:HF_HUB_OFFLINE=1; python -m src.scripts.vectordb_cli stats
   ```
3) **更新测试脚本（临时）**  
   - 在 `tests/tmp_run_tests.py` 中添加：`tau = 0.5`，过滤 `similarity < tau` 记为“无结果”；将 `top_k` 提升到 8 并做重排（按 page_type/level 规则）。  
4) **复测**  
   ```powershell
   $env:HF_HUB_OFFLINE=1; python tests/tmp_run_tests.py
   ```
   - 对比新的 `tests/tmp_embedding_test_round1.json` 与当前结果，重点关注细节类、边界类。  
5) **服务侧落地**（若测试通过）  
   - 把阈值、重排、默认 project 过滤封装进生产查询链路（例如 API 层或 `ChromaStore.query` 的包装器），并更新 README/使用说明。

## 五、验收标准
- 细节类 Top-1 平均相似度 ≥0.80；出现至少 2 个不同细节页。  
- 边界类：Top-1 相似度 <0.5 时返回“无相关”，不得返回业务页。  
- 直接事实与概念性：Top-1 ≥0.80，Top-3 命中正确页。  
- 结果多样性：同一查询 Top-3 不得全为 overview/对比页。

## 六、后续规划
- 引入轻量 reranker（如 bge-reranker-base）验证排序提升；  
- 扩充第二个项目以真实测试对比类问题；  
- 在 CI 增加快速烟囱测试：`python tests/tmp_run_tests.py`，自动计算各类 Top-1/Top-3 与阈值拒答率。
