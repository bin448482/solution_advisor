# QA 问答 UI（Streamlit）实施方案

编写时间：2026-01-04  
适用范围：在现有 RAG/QA 引擎基础上快速落地一个可交互的 Web UI，便于提问、查看来源、提交反馈。

## 目标与范围
- 以最小改动复用现有 `QAEngine`/`dialogue_orchestrator`，实现单页对话界面（问题输入、答案展示、引用、反馈）。
- 形成可内网部署的 MVP，后续可替换为正式前端（Next.js 等）。
- 保持对 `logs/qa_sessions` 的监控/缓存写入逻辑，便于运营和调优。
- **MVP 阶段采用同步模式**（无流式输出），Phase 2 可扩展流式支持。

## 体系架构
- **前端**：Streamlit 单页应用，组件包含项目选择、参数面板（`top_k/top_n/tau`）、对话窗口、反馈区。
- **后端调用**：直接在同进程中调用 `QAEngine.answer`（可选 `dialogue_orchestrator` 用于澄清/追问）。
- **数据来源**：`ppt_outputs/<ppt_name>/embeddings/` 下的向量与 RAG 文档；`QAEngine` 按 `project_name` 检索。
- **状态与日志**：沿用 `qa_monitor` 精确缓存与 `logs/qa_sessions/*.jsonl`；前端提交的点赞/纠错写入同目录。

## 依赖与环境
- Python >= 3.10，已满足现有项目需求。
- 追加依赖：`streamlit`（UI），`websockets` 非必需（Streamlit 内置），若需反向代理可加 `uvicorn`。
- 外部依赖保持：`soffice`、`pdftoppm`（非 UI 必需，但用于离线生成资源）。

安装建议：
```bash
pip install streamlit>=1.30.0
# 如需分离依赖，可追加到 requirements-dev.txt；正式纳入请更新 requirements.txt。
```

## 文件组织（建议）
- `src/ui/streamlit_app.py`：入口脚本。
- `src/ui/components.py`：可复用的 UI 片段（可选）。
- 运行命令示例：`streamlit run src/ui/streamlit_app.py --server.port 8501`

## API 契约（内部调用约定）
- 请求字段：`question: str`，`project_name: str | None`，`top_k: int`（默认 8），`top_n: int`（默认 5），`tau: float`（默认 0.5），`user_id: str | None`。
- 响应字段沿用 `QAEngine.answer`：`answer, sources, status, cache_status, cache_level, stats(optional)`；前端还需保存 `question` 与时间戳。

## UI 交互设计（MVP）
- 顶部选择：项目下拉（从 `ppt_outputs` 目录列出，需处理目录不存在/为空情况），参数滑条 `top_k/top_n/tau`，LLM 模式状态标签。
- 中部：对话气泡，答案分为"最终回答"和"引用来源"列表，来源点击可在新页打开（使用 `st.expander`/`st.link_button`）。
- 底部：输入框支持 `Enter` 发送、`Shift+Enter` 换行；旁侧按钮"清空会话"（MVP 阶段移除"停止生成"按钮，因同步调用无法中断）。
- 反馈：每条回答下方 👍/👎 + 纠错文本框，写入 `logs/qa_sessions/feedback_YYYYMMDD.jsonl`。
- 错误提示：Toast 或警告条，展示超时/网络错误/未找到项目等。
- 加载状态：使用 `st.spinner("正在思考...")` 显示 LLM 生成进度（MVP 阶段 UI 会冻结 2-10 秒，可接受）。

### 对话引导模式（可选）
- 侧边栏开关："启用对话引导"（切换 `QAEngine` / `DialogueOrchestrator`）。
- 澄清界面：当 `status == "clarify"` 时，展示 `slot_candidates` 为按钮网格供用户选择。
- 建议展示：在答案下方显示 `suggestions` 为可点击的 chip 按钮，点击自动填入输入框。
- 对话阶段标签：根据 `dialogue_phase` 显示当前阶段（澄清/补充提示/追问）。

## 日志与缓存策略
- 复用 `qa_monitor`：调用前后记录 `dialogue_phase/graph_node/cache_status`。
- 反馈 JSONL 字段示例：`{"ts": "...", "user_id": "...", "project": "...", "question": "...", "answer_id": "...", "rating": 1 | -1, "comment": "..."}`。
- 若启用 `dialogue_orchestrator`，在界面显示其澄清问题与系统提示。
- **并发写入限制**：MVP 阶段仅支持单用户部署，多用户场景需添加文件锁或队列写入机制。

## 会话状态管理
Streamlit 使用 `st.session_state` 在页面重载间保持状态，需初始化以下变量：

```python
# 初始化会话状态
if "dialogue_state" not in st.session_state:
    from src.qa.dialogue_orchestrator import DialogueState
    st.session_state.dialogue_state = DialogueState()

if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []  # List[Dict[str, str]]

if "current_project" not in st.session_state:
    st.session_state.current_project = None

if "qa_params" not in st.session_state:
    st.session_state.qa_params = {"top_k": 8, "top_n": 5, "tau": 0.5}
```

**清空会话逻辑**：
```python
if st.button("清空会话"):
    st.session_state.dialogue_state = DialogueState()
    st.session_state.conversation_history = []
    st.rerun()
```

**状态传递**：
- `QAEngine.answer()` 无状态，每次独立调用
- `DialogueOrchestrator.answer_with_guidance()` 需传入 `st.session_state.dialogue_state`，方法内部会更新状态

## 开发步骤（建议顺序）

### MVP Phase（同步模式）
1) 新建 `src/ui/streamlit_app.py`，最小功能：
   - 项目选择下拉（处理 `ppt_outputs` 不存在/为空情况）
   - 问答输入框 + 同步调用 `QAEngine.answer()`
   - 使用 `st.spinner("正在思考...")` 显示加载状态
   - 引用来源展示（`st.expander` 显示 sources）
2) 添加会话状态管理：
   - 初始化 `st.session_state`（dialogue_state, conversation_history 等）
   - 实现"清空会话"按钮
   - 对话历史展示（`st.chat_message`）
3) 接入反馈写入 `logs/qa_sessions`，并在 UI 中显示提交状态。
4) 增加参数面板（`top_k/top_n/tau`）和缓存/状态徽标；验证对 `QAEngine` 的传参。
5) （可选）加入 `dialogue_orchestrator` 作为澄清模式开关：
   - 侧边栏 checkbox "启用对话引导"
   - 根据 `status` 和 `dialogue_phase` 条件渲染澄清界面/建议
6) 补充 README/AGENTS：在根 `AGENTS.md` 记录新 UI 入口，在 `src/ui/AGENTS.md` 说明职责与运行方式。

### Phase 2（流式输出，可选）
1) 扩展 `LLMClient` 添加 `generate_stream()` 方法（使用 LangChain `.stream()` API）
2) 扩展 `QAEngine` 添加 `answer_stream()` 方法（返回 generator）
3) 在 Streamlit 中使用 `st.write_stream()` 或手动更新 placeholder 实现流式显示
4) 添加"停止生成"按钮（基于 generator 中断）

## 运行示例
```bash
# MVP 推荐：所有参数通过界面选择
streamlit run src/ui/streamlit_app.py

# 可选：通过环境变量预设配置
export DEFAULT_PROJECT=DemoPPT_2025
streamlit run src/ui/streamlit_app.py
```
说明：避免使用 `--` 传递自定义参数（易混淆），改为界面内选择或环境变量。

## 测试与验收
- 手工烟测：选择已存在的 `ppt_outputs/<ppt>`，提问 3 条，验证引用数量、缓存命中提示、反馈写入。
- 边界场景：
  - 未选择项目 / `ppt_outputs` 目录不存在或为空
  - 空问题 / 超长问题
  - 无检索结果（相似度低于阈值）
  - LLM 超时 / 网络错误
  - 缓存命中返回（验证 cache_status 显示）
  - DialogueOrchestrator 澄清模式（验证 slot_candidates 渲染）
- 后续可在 `tests/` 增加轻量 E2E，利用 `LLM_PROVIDER=mock` 和小型向量库。

## 安全与发布
- 默认仅内网访问；如需外部暴露，建议加上简单鉴权或通过反向代理限制。
- 鉴权示例（可选）：
  ```python
  # 在 streamlit_app.py 顶部
  import streamlit as st

  def check_auth():
      if "authenticated" not in st.session_state:
          token = st.text_input("请输入访问令牌", type="password")
          if st.button("登录"):
              if token == os.getenv("UI_ACCESS_TOKEN"):
                  st.session_state.authenticated = True
                  st.rerun()
              else:
                  st.error("令牌错误")
          st.stop()

  check_auth()
  ```
- 注意不要在日志里写入 API Key；Streamlit Secrets 仅存放 UI 级配置，LLM Key 仍从环境变量读取。
- MVP 阶段仅支持单用户部署（反馈写入无文件锁）。

## 下一步
- 实现 `src/ui/streamlit_app.py`，提交 MVP 最小可用版本（同步模式）。
- 更新根 `AGENTS.md` 和新建 `src/ui/AGENTS.md` 以记录 UI 职责与入口。
- （可选）Phase 2 扩展流式输出支持。

## 技术约束与已知限制

### MVP 阶段（同步模式）
- ✅ 可用：基础问答、引用展示、反馈收集、缓存状态显示
- ⚠️ 限制：
  - UI 会在 LLM 生成期间冻结 2-10 秒（可接受）
  - 无法中途停止生成（需 Phase 2 流式支持）
  - 仅支持单用户部署（反馈写入无并发控制）

### Phase 2（流式输出，可选）
- 需要后端改动：
  - `LLMClient.generate_stream()` 使用 LangChain `.stream()` API
  - `QAEngine.answer_stream()` 返回 generator
- 前端改动：
  - 使用 `st.write_stream()` 或手动更新 placeholder
  - 添加"停止生成"按钮（基于 generator 中断）

### 当前后端能力
- `QAEngine.answer()`: 同步调用，返回完整结果
- `DialogueOrchestrator.answer_with_guidance()`: 同步调用，支持多轮对话状态
- `LLMClient.generate()`: 使用 `.invoke()`，无流式支持
- 缓存：仅精确匹配（TTL 7天），语义缓存已下线
