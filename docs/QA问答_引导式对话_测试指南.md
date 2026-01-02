# 引导式对话测试指南（阶段 1 模板版）

## 当前实施状态

✅ **已完成（阶段 1）**：
- DialogueOrchestrator 模板版实现
- Gradio Web UI 集成
- 模板文件（guided_templates.yaml）
- 配置支持（settings.example.yaml）

❌ **未完成（阶段 2/3）**：
- LLM 动态生成追问
- 槽位澄清与去重冷却
- QA CLI 多轮模式

## 测试前准备

### 1. 确认配置文件

确保 `config/settings.yaml` 包含引导式对话配置：

```yaml
qa:
  monitor:
    monitor_enabled: true
    monitor_sample_rate: 1.0
    log_dir: logs/qa_sessions
  cache:
    cache_enabled: true
    cache_sample_rate: 1.0
    cache_ttl_days: 7
    cache_backend: jsonl
    cache_semantic_enabled: true
    cache_semantic_threshold: 0.85
    cache_collection: qa_cache
    cache_persist_dir: ./chroma_db
    vectordb_version: v1
  guided:
    enabled: true
    engine: langgraph
    suggestion_count: 3
    templates_path: src/prompts/guided_templates.yaml
    gap_similarity_threshold: 0.5
```

如果没有，从示例文件复制：
```bash
cp config/settings.example.yaml config/settings.yaml
# 然后编辑 config/settings.yaml，填入真实的 API keys
```

### 2. 确认向量库已导入

引导式对话依赖向量库检索，确保已导入项目数据：

```bash
# 查看已导入的项目
python -m src.scripts.vectordb_cli stats

# 如果为空，导入项目数据
python -m src.scripts.vectordb_cli batch-import --input-dir ppt_outputs
```

### 3. 安装 Gradio（如未安装）

```bash
pip install gradio>=4.0.0
```

### 4. 可选：安装 LangGraph（推荐）

```bash
pip install langgraph>=0.0.20
```

如果不安装，系统会自动降级到简单模式（无状态图编排）。

## 测试方法

### 方法 1：Gradio Web UI（推荐）

这是阶段 1 的主要测试入口。

#### 启动 Web UI

```bash
python -m src.scripts.qa_gradio --config config/settings.yaml
```

可选参数：
- `--host`: 监听地址（默认：127.0.0.1）
- `--port`: 端口号（默认：7860）
- `--project`: 默认项目名（可选）

示例：
```bash
# 基本启动
python -m src.scripts.qa_gradio

# 指定项目
python -m src.scripts.qa_gradio --project ChatBI

# 自定义端口
python -m src.scripts.qa_gradio --port 8080
```

#### 访问界面

启动后，浏览器访问：`http://127.0.0.1:7860`

#### 测试场景

**场景 1：模糊问题触发 gap_prompt**

1. 在输入框输入模糊问题：`核心功能是什么`
2. 观察：
   - 系统应返回答案（如果检索到相关内容）
   - 下方按钮区显示建议追问（gap_prompts），例如：
     - "您可以补充项目名称，例如：ChatBI 的 XXX"
     - "您想了解哪个阶段？立项 / 实施 / 收尾"
     - "您关注哪个方面？功能 / 架构 / 部署 / 案例"

**场景 2：点击建议追问**

1. 点击任一建议按钮（例如："您可以补充项目名称..."）
2. 观察：
   - 建议文本自动填入输入框
   - 可以修改后发送，或直接发送

**场景 3：明确问题触发 follow_up**

1. 输入明确问题：`ChatBI 的架构设计`
2. 观察：
   - 系统返回详细答案
   - 下方按钮区显示相关追问（follow_ups），例如：
     - "想了解部署方式吗？"
     - "需要查看技术栈详情吗？"

**场景 4：指定项目过滤**

1. 在"项目名称（可选）"输入框填入：`ChatBI`
2. 输入问题：`核心功能`
3. 观察：
   - 答案仅来自 ChatBI 项目
   - 来源显示：`ChatBI:第X页`

**场景 5：多轮对话**

1. 第一轮：`ChatBI 的核心功能`
2. 点击建议："想看具体的功能演示吗？"
3. 第二轮：`功能演示`
4. 观察：
   - 对话历史保持在界面上
   - 每轮都有新的建议追问

### 方法 2：直接调用 DialogueOrchestrator（开发调试）

创建测试脚本 `test_orchestrator.py`：

```python
from src.config import Settings
from src.embeddings import M3EEmbedding
from src.vectordb import ChromaStore
from src.summarizer import LLMClient
from src.qa import QAEngine
from src.qa.qa_monitor import QAMonitor
from src.qa.dialogue_orchestrator import DialogueOrchestrator, DialogueState
from src.prompts import get_guided_templates

# 初始化
settings = Settings.from_yaml("config/settings.yaml")
embedding_model = M3EEmbedding(
    model_name=settings.embedding_model,
    device=settings.embedding_device,
    cache_dir=settings.embedding_cache_dir,
)
store = ChromaStore(
    persist_dir=settings.vectordb_persist_dir,
    collection_name=settings.vectordb_collection_name,
    embedding_model=embedding_model,
)
llm_client = LLMClient(settings)
monitor = QAMonitor(settings=settings, embedding_model=embedding_model)
qa_engine = QAEngine(store=store, llm_client=llm_client, monitor=monitor)

templates = get_guided_templates("src/prompts/guided_templates.yaml")
orchestrator = DialogueOrchestrator(
    qa_engine=qa_engine,
    templates=templates,
    gap_threshold=0.5
)

# 测试单轮对话
state = DialogueState()
result = orchestrator.answer_with_guidance("ChatBI 的核心功能", state)

print("Answer:", result["answer"])
print("Sources:", result["sources"])
print("Suggestions:", result["suggestions"])
print("State:", state)
```

运行：
```bash
python test_orchestrator.py
```

### 方法 3：查看日志（验证监控与缓存）

引导式对话会记录日志到 `logs/qa_sessions/`：

```bash
# 查看最新日志
tail -f logs/qa_sessions/qa_logs_$(date +%Y%m%d).jsonl

# 查看缓存
cat logs/qa_sessions/qa_cache.jsonl | jq .
```

日志字段：
- `question`: 原始问题
- `answer`: 生成的答案
- `sources`: 检索来源
- `suggestions`: 建议追问
- `cache_status`: 缓存命中状态（hit/miss）
- `timestamp`: 时间戳

## 预期行为

### Gap Prompt 触发条件

当满足以下任一条件时，返回 gap_prompts：
1. 检索结果为空（无相关文档）
2. Top-1 相似度 < gap_threshold（默认 0.5）
3. 问题过于模糊（少于 3 个字）

### Follow-up 生成逻辑

当检索成功且相似度 >= gap_threshold 时：
1. 根据检索结果的 `page_type` 匹配模板
2. 从 `follow_ups_by_module` 中选择对应建议
3. 如果没有匹配，使用 `default` 建议
4. 返回前 N 条（由 `suggestion_count` 控制，默认 3）

### 状态保持

`DialogueState` 在 Gradio 会话中保持：
- `slots`: 提取的槽位（project_name, phase, module）
- `history`: 对话历史（问答对）
- `recent_suggestions`: 最近的建议（用于去重，阶段 2 功能）

## 常见问题

### Q1: 启动 Gradio 报错 "Gradio 未安装"

**解决**：
```bash
pip install gradio>=4.0.0
```

### Q2: 没有建议追问显示

**可能原因**：
1. `guided.enabled: false` - 检查配置文件
2. `templates_path` 路径错误 - 确认文件存在
3. LangGraph 未安装且降级失败 - 安装 `pip install langgraph`

**调试**：
```python
from src.prompts import get_guided_templates
templates = get_guided_templates("src/prompts/guided_templates.yaml")
print(templates)  # 应显示 gap_prompts 和 follow_ups_by_module
```

### Q3: 建议追问总是相同

**原因**：阶段 1 使用静态模板，不会根据上下文动态生成。

**解决**：等待阶段 2/3 实施（LLM 动态生成）。

### Q4: 检索结果为空

**可能原因**：
1. 向量库未导入数据
2. 项目名称拼写错误
3. 问题与文档内容不相关

**调试**：
```bash
# 检查向量库
python -m src.scripts.vectordb_cli stats

# 测试检索
python -m src.scripts.vectordb_cli query --text "核心功能" --project ChatBI
```

### Q5: LangGraph 相关警告

**警告示例**：
```
LangGraph not available, falling back to simple mode
```

**影响**：功能正常，但无状态图编排（性能略低）。

**解决**（可选）：
```bash
pip install langgraph>=0.0.20
```

## 验收标准

阶段 1 功能验收清单：

- [ ] Gradio UI 正常启动
- [ ] 输入模糊问题，显示 gap_prompts 建议
- [ ] 输入明确问题，显示 follow_up 建议
- [ ] 点击建议按钮，文本自动填入输入框
- [ ] 指定项目名称，检索结果正确过滤
- [ ] 多轮对话，历史记录正常显示
- [ ] 来源信息正确显示（项目名:第X页）
- [ ] 日志文件正常写入 `logs/qa_sessions/`

## 下一步

阶段 1 测试通过后，可以开始实施：

**阶段 2**：槽位澄清与去重冷却
- 实现 `src/qa/dialogue_state.py`（槽位提取与管理）
- 增强 `DialogueOrchestrator`（去重冷却逻辑）
- 添加测试 `tests/test_dialogue_orchestrator.py`

**阶段 3**：LLM 动态生成追问
- 创建 `src/prompts/guided_llm.txt`（LLM 提示词）
- 实现 LLM 生成逻辑（替换静态模板）
- 添加 QA CLI 多轮模式（`--guided` 选项）

## 反馈与改进

测试过程中发现的问题，请记录到：
- Bug：创建 GitHub Issue
- 改进建议：更新 `docs/QA问答_引导式对话_分阶段实施计划.md`
- 模板优化：直接编辑 `src/prompts/guided_templates.yaml`
