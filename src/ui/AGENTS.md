# UI Module (Streamlit)

## 职责
提供基于 Streamlit 的 Web UI，用于与 QA 引擎交互，支持：
- 项目选择与参数配置
- 问答对话（同步模式）
- 引用来源展示
- 用户反馈收集
- 对话引导模式（可选）

## 入口脚本
- `streamlit_app.py`：主应用入口

## 运行方式

### 基础运行
```bash
streamlit run src/ui/streamlit_app.py
```

### 指定端口
```bash
streamlit run src/ui/streamlit_app.py --server.port 8501
```

### 环境变量配置
```bash
export DEFAULT_PROJECT=ChatBI
streamlit run src/ui/streamlit_app.py
```

## 核心功能

### 1. 项目选择
- 自动扫描 `ppt_outputs/` 目录
- 仅显示包含 `embeddings/rag_documents.json` 的项目
- 支持"全部项目"模式（跨项目检索）

### 2. 会话状态管理
使用 `st.session_state` 维护：
- `dialogue_state`: DialogueOrchestrator 状态对象
- `conversation_history`: 对话历史列表
- `current_project`: 当前选中项目
- `qa_params`: 检索参数 (top_k, top_n, tau)
- `use_orchestrator`: 是否启用对话引导

### 3. 问答模式
- **基础模式**: 直接调用 `QAEngine.answer()`
- **引导模式**: 调用 `DialogueOrchestrator.answer_with_guidance()`
  - 支持澄清问题（slot filling）
  - 显示追问建议
  - 维护多轮对话状态

### 4. 反馈收集
写入 `logs/qa_sessions/feedback_YYYYMMDD.jsonl`，字段：
- `ts`: 时间戳
- `user_id`: 用户标识（默认 "streamlit_user"）
- `project`: 项目名称
- `question`: 问题
- `answer_id`: 答案唯一标识
- `rating`: 评分 (1=赞, -1=踩, 0=仅评论)
- `comment`: 文本评论

## 依赖
- `streamlit>=1.30.0`
- `src.qa.qa_engine.QAEngine`
- `src.qa.dialogue_orchestrator.DialogueOrchestrator`
- `src.config.Settings`

## 技术约束

### MVP 阶段（当前实现）
- ✅ 同步调用，UI 会在 LLM 生成期间冻结 2-10 秒
- ✅ 使用 `st.spinner()` 显示加载状态
- ⚠️ 无流式输出
- ⚠️ 无"停止生成"功能
- ⚠️ 仅支持单用户部署（反馈写入无文件锁）

### 未来扩展（Phase 2）
- 流式输出（需后端 `LLMClient.generate_stream()` 支持）
- 停止生成按钮
- 多用户并发支持

## 错误处理
- 项目目录不存在：显示警告，提示运行 PPT 解析
- 无检索结果：显示"未找到相关内容"提示
- LLM 错误：捕获异常，显示错误信息和堆栈
- 缓存命中：显示 ⚡ 标识和缓存层级

## 测试方式

### 手工测试
1. 确保至少有一个项目在 `ppt_outputs/` 下
2. 运行 `streamlit run src/ui/streamlit_app.py`
3. 选择项目，提问 3 条
4. 验证：引用来源、缓存状态、反馈写入

### 边界场景
- 未选择项目（全部项目模式）
- 空问题 / 超长问题
- 无检索结果（相似度低于阈值）
- LLM 超时 / 网络错误
- 对话引导模式（澄清界面）

## 安全注意事项
- 默认仅监听 localhost（内网访问）
- 不在日志中记录 API Key
- 反馈文件仅包含用户输入和系统输出，不含敏感配置
- 如需外部暴露，建议添加鉴权或反向代理
