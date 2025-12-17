from typing import TypedDict, Annotated, Dict, Any, List
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# --- IMPORT CÁC AGENT & MANAGER ---
from agents.project_agent import create_project_agent
from agents.task_agent import create_task_agent
from agents.general_agent import create_general_agent
from agents.analytics_agent import create_analytics_agent
from orchestrator.prompts import SUPERVISOR_SYSTEM_PROMPT
from utils.llm_factory import get_llm

# --- IMPORT MANAGER ĐỂ XOAY KEY (MỚI) ---
from utils.gemini_manager import analytics_engine
from utils.groq_manager import groq_engine  # <--- Manager Groq
from orchestrator.prompts.analytics import ANALYTICS_AGENT_SYSTEM_PROMPT


# =============================================================================
# 0. HELPER: HÀM CHẠY RETRY + ROTATE KEY (CORE LOGIC)
# =============================================================================
def run_with_retry(agent_factory_func, messages, manager, engine_name="Groq"):
    """
    Wrapper giúp chạy Agent với cơ chế tự động xoay key khi gặp lỗi Rate Limit.
    """
    # Lấy số lượng key tối đa để biết đường dừng lại
    max_retries = len(manager.keys) if hasattr(manager, "keys") else 3
    attempt = 0

    while attempt < max_retries:
        try:
            # 1. Tạo lại Agent/Model với Key hiện tại (Active Key)
            if engine_name == "Analytics":
                # Analytics (Gemini) bind tool trực tiếp
                llm = manager.get_llm()
                # Tạo tools mới nhất
                tools = create_analytics_agent()
                agent_runnable = llm.bind_tools(tools)
                # Gemini gọi invoke trực tiếp với list messages
                response = agent_runnable.invoke(messages)
            else:
                # Các agent khác (Groq): Gọi factory để lấy model mới nhất
                agent_runnable, _ = agent_factory_func()
                # Groq gọi invoke với dict {"messages": ...}
                response = agent_runnable.invoke({"messages": messages})

            return response

        except Exception as e:
            error_msg = str(e).lower()
            # Các lỗi liên quan đến Rate Limit / Key / Quota
            if any(x in error_msg for x in
                   ["429", "403", "quota", "resource_exhausted", "rate_limit", "api_key", "overloaded"]):
                print(f"⚠️ [{engine_name} Error] Key lỗi/hết hạn: {error_msg}")

                # 2. Xoay Key
                if hasattr(manager, "_rotate_key"):
                    manager._rotate_key()

                attempt += 1
                print(f"🔄 [{engine_name}] Đang thử lại lần {attempt} với Key mới...")
            else:
                # Lỗi logic (như 400 Tool Validation) -> Không xoay key, báo lỗi luôn
                print(f"❌ [{engine_name} Critical] Lỗi hệ thống: {str(e)}")
                return AIMessage(content=f"⚠️ Lỗi xử lý ({engine_name}): {str(e)}")

    return AIMessage(content=f"⚠️ Hệ thống {engine_name} đang quá tải (Hết toàn bộ Key). Vui lòng thử lại sau.")


# =============================================================================
# 1. ĐỊNH NGHĨA STATE
# =============================================================================
class AgentState(TypedDict):
    messages: Annotated[List[Any], add_messages]
    user_context: Dict[str, Any]
    next: str


# =============================================================================
# 2. KHỞI TẠO TOOLS (CHỈ LẤY TOOLS ĐỂ DỰNG GRAPH)
# =============================================================================
# Lưu ý: Model sẽ được tạo động trong Node thông qua run_with_retry
_, project_tools = create_project_agent()
_, task_tools = create_task_agent()
analytics_tools = create_analytics_agent()


# =============================================================================
# 3. HELPER: TẠO SYSTEM PROMPT CHỨA ID
# =============================================================================
def create_context_prompt(state: AgentState) -> SystemMessage:
    ctx = state.get("user_context", {})
    company_id = ctx.get("company_id")
    workspace_id = ctx.get("workspace_id")
    project_id = ctx.get("project_id")

    # Kiểm tra thiếu ID quan trọng
    missing = []
    if not company_id: missing.append("Company ID")
    if not workspace_id: missing.append("Workspace ID")

    if missing:
        # Nếu thiếu ID, trả về prompt nhắc AI hỏi người dùng
        return SystemMessage(content=f"""
        ### ⚠️ MISSING CONTEXT ###
        Bạn đang thiếu thông tin: {', '.join(missing)}.
        ⛔ KHÔNG ĐƯỢC gọi tool tạo/sửa/xóa nếu thiếu ID này.
        👉 HÃY HỎI NGƯỜI DÙNG: "Vui lòng cung cấp ID Công ty/Workspace để tôi thực hiện."
        """)

    prompt = f"""
    ### 🔒 AUTHENTICATED CONTEXT (ĐÃ XÁC THỰC) ###
    - Company ID: {company_id} (Integer)
    - Workspace ID: {workspace_id} (Integer)
    - Project ID: {project_id} (Integer/Null)

    ✅ YÊU CẦU: Bắt buộc dùng các số nguyên này khi gọi tool. KHÔNG dùng chuỗi.
    """
    return SystemMessage(content=prompt)


# =============================================================================
# 4. ĐỊNH NGHĨA CÁC NODE (ĐÃ ÁP DỤNG XOAY KEY)
# =============================================================================

def project_node(state: AgentState):
    """Xử lý Project - Có Retry Groq + Context"""
    context_msg = create_context_prompt(state)
    messages = [context_msg] + state["messages"]

    # 🔥 Gọi qua wrapper để tự động xoay key
    response = run_with_retry(create_project_agent, messages, groq_engine, "Groq")
    return {"messages": [response]}


def task_node(state: AgentState):
    """Xử lý Task - Có Retry Groq + Context"""
    context_msg = create_context_prompt(state)
    messages = [context_msg] + state["messages"]

    # 🔥 Gọi qua wrapper
    response = run_with_retry(create_task_agent, messages, groq_engine, "Groq")
    return {"messages": [response]}


def analytics_node(state: AgentState):
    """Xử lý Analytics - Có Retry Gemini + Context"""
    print("📊 [Router] Chuyển hướng sang ANALYTICS AGENT...")
    context_msg = create_context_prompt(state)

    # Ghép prompt đặc biệt
    messages = [
                   {"role": "system", "content": ANALYTICS_AGENT_SYSTEM_PROMPT},
                   context_msg,
               ] + state["messages"]

    # 🔥 Gọi qua wrapper (Analytics dùng logic riêng trong wrapper)
    response = run_with_retry(None, messages, analytics_engine, "Analytics")
    return {"messages": [response]}


def general_node(state: AgentState):
    """General Agent (Ít lỗi, nhưng cứ dùng create mới cho chắc)"""
    model = create_general_agent()
    response = model.invoke({"messages": state["messages"]})
    return {"messages": [response]}


# =============================================================================
# 5. SUPERVISOR NODE (CŨNG CẦN XOAY KEY NẾU GROQ HẾT QUOTA)
# =============================================================================
def supervisor_node(state: AgentState):
    messages = state["messages"]
    last_user_msg = messages[-1]
    user_text = str(last_user_msg.content).lower()

    if not isinstance(last_user_msg, HumanMessage):
        return {"next": "END"}

    # --- A. LOGIC GHIM LUỒNG ---
    if len(messages) >= 2:
        last_ai_msg = messages[-2]
        if isinstance(last_ai_msg, AIMessage):
            ai_text = str(last_ai_msg.content).lower()
            if "thông tin dự án" in ai_text or "mã dự án" in ai_text:
                return {"next": "Project_Agent"}

            analytics_stickies = ["đề xuất", "dự báo", "kịch bản", "rủi ro", "standup", "báo cáo"]
            if any(k in ai_text for k in analytics_stickies):
                return {"next": "Analytics_Agent"}

            keywords_confirm = ["xác nhận", "thực hiện không", "đồng ý", "chắc chắn", "bảng dưới đây"]
            if any(k in ai_text for k in keywords_confirm):
                if any(x in ai_text for x in ["task", "excel", "công việc"]):
                    return {"next": "Task_Agent"}
                if "dự án" in ai_text:
                    return {"next": "Project_Agent"}

    # --- B. LOGIC AI ROUTER ---
    recent_msgs = messages[-6:]
    history_str = ""
    for m in recent_msgs:
        role = "User" if isinstance(m, HumanMessage) else "AI"
        content = m.content if isinstance(m.content, str) else str(m.content)
        history_str += f"- {role}: {content[:150]}...\n"

    router_prompt = (
        f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
        f"=== PHÂN LOẠI AGENT ===\n"
        f"1. Analytics_Agent: Giao việc, dự báo, báo cáo, phân tích sâu.\n"
        f"2. Task_Agent: Tạo/Sửa/Xóa task, xử lý file excel.\n"
        f"3. Project_Agent: Quản lý dự án, workspace.\n"
        f"===================================\n"
        f"HISTORY:\n{history_str}\n"
        f"USER: '{last_user_msg.content}'\n"
        "DECISION [Project_Agent, Task_Agent, General_Agent, Analytics_Agent]:"
    )

    # 🔥 LOGIC RETRY CHO SUPERVISOR
    max_retries = len(groq_engine.keys)
    attempt = 0
    result = "General_Agent"

    while attempt < max_retries:
        try:
            # Lấy model với Key hiện tại
            llm = groq_engine.get_llm(temperature=0)
            ai_msg = llm.invoke(router_prompt)
            result = ai_msg.content.strip()
            print(f"\n[ROUTER AI] Selected: {result}")
            break
        except Exception as e:
            print(f"⚠️ [Supervisor Error] Key lỗi: {e}")
            groq_engine._rotate_key()
            attempt += 1

    # --- Mapping logic ---
    if "Analytics" in result: return {"next": "Analytics_Agent"}
    if "Task" in result: return {"next": "Task_Agent"}
    if "Project" in result: return {"next": "Project_Agent"}
    if "General" in result: return {"next": "General_Agent"}

    # --- C. FALLBACK ---
    if any(k in user_text for k in ["phân tích", "tại sao", "rủi ro", "chiến lược", "báo cáo"]):
        return {"next": "Analytics_Agent"}
    if "dự án" in user_text: return {"next": "Project_Agent"}
    if "task" in user_text: return {"next": "Task_Agent"}

    return {"next": "General_Agent"}


# =============================================================================
# 6. XÂY DỰNG GRAPH
# =============================================================================
workflow = StateGraph(AgentState)

# Nodes
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Project_Agent", project_node)
workflow.add_node("Task_Agent", task_node)
workflow.add_node("General_Agent", general_node)
workflow.add_node("Analytics_Agent", analytics_node)

# Tool Nodes
workflow.add_node("project_tools", ToolNode(project_tools))
workflow.add_node("task_tools", ToolNode(task_tools))
workflow.add_node("analytics_tools", ToolNode(analytics_tools))

# Edges
workflow.add_edge(START, "Supervisor")

workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {
        "Project_Agent": "Project_Agent",
        "Task_Agent": "Task_Agent",
        "General_Agent": "General_Agent",
        "Analytics_Agent": "Analytics_Agent",
        "END": END
    }
)


# Project Loop
def project_cond(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "project_tools"
    return "END"


workflow.add_conditional_edges("Project_Agent", project_cond, {"project_tools": "project_tools", "END": END})
workflow.add_edge("project_tools", "Project_Agent")


# Task Loop
def task_cond(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "task_tools"
    return "END"


workflow.add_conditional_edges("Task_Agent", task_cond, {"task_tools": "task_tools", "END": END})
workflow.add_edge("task_tools", "Task_Agent")


# Analytics Loop
def analytics_cond(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "analytics_tools"
    return "END"


workflow.add_conditional_edges("Analytics_Agent", analytics_cond, {"analytics_tools": "analytics_tools", "END": END})
workflow.add_edge("analytics_tools", "Analytics_Agent")

workflow.add_edge("General_Agent", END)

app = workflow.compile(checkpointer=MemorySaver())