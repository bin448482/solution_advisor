"""
Streamlit UI for QA System
MVP implementation with synchronous mode
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st

# Import QA components
from src.qa.qa_engine import QAEngine
from src.qa.dialogue_orchestrator import DialogueOrchestrator, DialogueState
from src.qa.qa_monitor import QAMonitor
from src.config import Settings
from src.embeddings import M3EEmbedding
from src.vectordb import ChromaStore
from src.summarizer import LLMClient
from src.prompts import get_guided_templates


# Page config
st.set_page_config(
    page_title="项目AI助手",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)


def init_session_state():
    """Initialize Streamlit session state"""
    if "dialogue_state" not in st.session_state:
        st.session_state.dialogue_state = DialogueState()

    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []

    if "current_project" not in st.session_state:
        st.session_state.current_project = None

    if "qa_params" not in st.session_state:
        st.session_state.qa_params = {"top_k": 8, "top_n": 5, "tau": 0.5}

    if "use_orchestrator" not in st.session_state:
        st.session_state.use_orchestrator = False

    if "qa_engine" not in st.session_state:
        settings = Settings.from_yaml()

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
        monitor = QAMonitor(settings=settings)

        st.session_state.qa_engine = QAEngine(
            store=store,
            llm_client=llm_client,
            monitor=monitor,
        )
        st.session_state.settings = settings
        st.session_state.llm_client = llm_client

    if "orchestrator" not in st.session_state:
        # Templates are optional; fall back to defaults if missing
        templates = get_guided_templates(getattr(st.session_state.settings.qa.guided, "templates_path", None))
        st.session_state.orchestrator = DialogueOrchestrator(
            qa_engine=st.session_state.qa_engine,
            templates=templates,
            llm_client=st.session_state.llm_client,
            gap_threshold=getattr(st.session_state.settings.qa.guided, "gap_similarity_threshold", 0.5),
        )


def get_available_projects() -> List[str]:
    """Get list of available projects from ppt_outputs directory"""
    ppt_outputs_dir = Path("ppt_outputs")

    if not ppt_outputs_dir.exists():
        return []

    projects = []
    for item in ppt_outputs_dir.iterdir():
        if item.is_dir():
            # Check if embeddings exist
            embeddings_file = item / "embeddings" / "rag_documents.json"
            if embeddings_file.exists():
                projects.append(item.name)

    return sorted(projects)


def save_feedback(question: str, answer: str, project: str, rating: int, comment: str = ""):
    """Save user feedback to JSONL file"""
    logs_dir = Path("logs/qa_sessions")
    logs_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    feedback_file = logs_dir / f"feedback_{today}.jsonl"

    feedback_entry = {
        "ts": datetime.now().isoformat(),
        "user_id": "streamlit_user",
        "project": project,
        "question": question,
        "answer_id": f"{datetime.now().timestamp()}",
        "rating": rating,
        "comment": comment
    }

    with open(feedback_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(feedback_entry, ensure_ascii=False) + "\n")


def render_sidebar():
    """Render sidebar with project selection and parameters"""
    st.sidebar.title("⚙️ 配置")

    # Project selection
    st.sidebar.subheader("项目选择")
    projects = get_available_projects()

    if not projects:
        st.sidebar.warning("未找到任何项目，请先运行 PPT 解析流程")
        return None

    selected_project = st.sidebar.selectbox(
        "选择项目",
        options=["全部项目"] + projects,
        index=0 if st.session_state.current_project is None else
              (projects.index(st.session_state.current_project) + 1
               if st.session_state.current_project in projects else 0)
    )

    if selected_project == "全部项目":
        st.session_state.current_project = None
    else:
        st.session_state.current_project = selected_project

    # Parameters
    st.sidebar.subheader("检索参数")

    top_k = st.sidebar.slider(
        "Top-K (召回数量)",
        min_value=3,
        max_value=20,
        value=st.session_state.qa_params["top_k"],
        help="向量检索召回的文档数量"
    )

    top_n = st.sidebar.slider(
        "Top-N (重排后数量)",
        min_value=1,
        max_value=10,
        value=st.session_state.qa_params["top_n"],
        help="重排后保留的文档数量"
    )

    tau = st.sidebar.slider(
        "相似度阈值 (τ)",
        min_value=0.0,
        max_value=1.0,
        value=st.session_state.qa_params["tau"],
        step=0.05,
        help="最低相似度阈值，低于此值的结果会被过滤"
    )

    st.session_state.qa_params = {"top_k": top_k, "top_n": top_n, "tau": tau}

    # Dialogue orchestrator toggle
    st.sidebar.subheader("对话模式")
    use_orchestrator = st.sidebar.checkbox(
        "启用对话引导",
        value=st.session_state.use_orchestrator,
        help="启用后会提供澄清问题和追问建议"
    )
    st.session_state.use_orchestrator = use_orchestrator

    # Display options
    st.sidebar.subheader("显示选项")
    show_sources = st.sidebar.checkbox(
        "显示引用来源",
        value=False,
        help="显示答案的来源页码和相似度（调试用）"
    )
    st.session_state.show_sources = show_sources

    # Clear session button
    st.sidebar.subheader("会话管理")
    if st.sidebar.button("🗑️ 清空会话", use_container_width=True):
        st.session_state.dialogue_state = DialogueState()
        st.session_state.conversation_history = []
        st.rerun()

    return selected_project


def render_sources(sources: List[Dict[str, Any]]):
    """Render source citations"""
    if not sources:
        return

    st.markdown("### 📚 引用来源")

    for idx, source in enumerate(sources, 1):
        with st.expander(f"来源 {idx}: {source.get('project', 'Unknown')} - 第 {source.get('slide_no', '?')} 页"):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**项目**: {source.get('project', 'N/A')}")
                st.markdown(f"**页码**: {source.get('slide_no', 'N/A')}")
                st.markdown(f"**类型**: {', '.join(source.get('page_type', []))}")
                st.markdown(f"**层级**: {source.get('level', 'N/A')}")

            with col2:
                similarity = source.get('similarity', 0)
                st.metric("相似度", f"{similarity:.2%}")


def render_feedback_buttons(question: str, answer: str, project: str, msg_idx: int):
    """Render feedback buttons for a Q&A pair"""
    col1, col2, col3 = st.columns([1, 1, 8])

    with col1:
        if st.button("👍", key=f"thumbs_up_{msg_idx}"):
            save_feedback(question, answer, project or "全部", 1)
            st.success("感谢反馈！")

    with col2:
        if st.button("👎", key=f"thumbs_down_{msg_idx}"):
            save_feedback(question, answer, project or "全部", -1)
            st.warning("已记录，我们会改进")

    # Optional comment
    with st.expander("💬 添加评论"):
        comment = st.text_area(
            "详细反馈",
            key=f"comment_{msg_idx}",
            placeholder="请描述问题或建议..."
        )
        if st.button("提交评论", key=f"submit_comment_{msg_idx}"):
            if comment.strip():
                save_feedback(question, answer, project or "全部", 0, comment)
                st.success("评论已提交！")


def render_suggestions(suggestions: List[str]):
    """Render follow-up suggestions as clickable chips"""
    if not suggestions:
        return

    st.markdown("### 💡 相关建议")

    cols = st.columns(min(len(suggestions), 3))
    for idx, suggestion in enumerate(suggestions):
        with cols[idx % 3]:
            if st.button(suggestion, key=f"suggestion_{idx}", use_container_width=True):
                st.session_state.next_question = suggestion
                st.rerun()


def render_clarification(slot_candidates: Dict[str, List[str]]):
    """Render clarification interface for slot filling"""
    st.info("🤔 需要澄清以下信息：")

    for slot_name, candidates in slot_candidates.items():
        st.markdown(f"**{slot_name}**:")
        cols = st.columns(min(len(candidates), 4))
        for idx, candidate in enumerate(candidates):
            with cols[idx % 4]:
                if st.button(candidate, key=f"slot_{slot_name}_{idx}", use_container_width=True):
                    # Fill the slot and rerun
                    st.session_state.dialogue_state.slots[slot_name] = candidate
                    st.rerun()


def main():
    """Main application"""
    init_session_state()

    # Header
    st.title("项目AI助手")
    st.markdown("基于 RAG 的智能问答系统")

    # Sidebar
    selected_project = render_sidebar()

    if not get_available_projects():
        st.error("❌ 未找到任何项目数据，请先运行 PPT 解析流程生成向量库")
        st.code("python -m src --input ppts/<file>.pptx --output ppt_outputs/<name>")
        return

    # Display conversation history
    for idx, msg in enumerate(st.session_state.conversation_history):
        # User question
        with st.chat_message("user"):
            st.markdown(msg["question"])

        # Assistant answer
        with st.chat_message("assistant"):
            st.markdown(msg["answer"])

            # Show cache status if available
            if msg.get("cache_status") == "hit":
                st.caption(f"⚡ 缓存命中 ({msg.get('cache_level', 'unknown')})")

            # Show sources (only if enabled)
            if msg.get("sources") and st.session_state.get("show_sources", False):
                render_sources(msg["sources"])

            # Show suggestions if available
            if msg.get("suggestions"):
                render_suggestions(msg["suggestions"])

            # Feedback buttons
            render_feedback_buttons(
                msg["question"],
                msg["answer"],
                msg.get("project", "全部"),
                idx
            )

    # Handle clarification mode
    if (st.session_state.use_orchestrator and
        st.session_state.conversation_history and
        st.session_state.conversation_history[-1].get("status") == "clarify"):

        last_msg = st.session_state.conversation_history[-1]
        if last_msg.get("slot_candidates"):
            render_clarification(last_msg["slot_candidates"])

    # Chat input
    if prompt := st.chat_input("请输入您的问题..."):
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get answer
        with st.chat_message("assistant"):
            with st.spinner("正在思考..."):
                try:
                    if st.session_state.use_orchestrator:
                        # Use DialogueOrchestrator
                        result = st.session_state.orchestrator.answer_with_guidance(
                            prompt,
                            state=st.session_state.dialogue_state
                        )
                    else:
                        # Use QAEngine directly
                        result = st.session_state.qa_engine.answer(
                            question=prompt,
                            project_name=st.session_state.current_project,
                            **st.session_state.qa_params
                        )

                    # Display answer
                    if result["status"] == "success":
                        st.markdown(result["answer"])

                        # Show cache status
                        if result.get("cache_status") == "hit":
                            st.caption(f"⚡ 缓存命中 ({result.get('cache_level', 'unknown')})")

                        # Show sources (only if enabled)
                        if result.get("sources") and st.session_state.get("show_sources", False):
                            render_sources(result["sources"])

                        # Show suggestions
                        if result.get("suggestions"):
                            render_suggestions(result["suggestions"])

                    elif result["status"] == "clarify":
                        st.info(result["answer"])
                        if result.get("slot_candidates"):
                            render_clarification(result["slot_candidates"])

                    elif result["status"] == "no_context":
                        st.warning("⚠️ 未找到相关内容，请尝试换个问法或选择其他项目")

                    else:  # error
                        st.error(f"❌ 出错了: {result.get('error', '未知错误')}")

                    # Save to conversation history
                    history_entry = {
                        "question": prompt,
                        "answer": result["answer"],
                        "sources": result.get("sources", []),
                        "status": result["status"],
                        "cache_status": result.get("cache_status"),
                        "cache_level": result.get("cache_level"),
                        "suggestions": result.get("suggestions", []),
                        "slot_candidates": result.get("slot_candidates", {}),
                        "project": st.session_state.current_project,
                        "timestamp": datetime.now().isoformat()
                    }
                    st.session_state.conversation_history.append(history_entry)

                except Exception as e:
                    st.error(f"❌ 系统错误: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
