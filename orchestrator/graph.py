from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from orchestrator.state import AgentState
from orchestrator.prompts import SUPERVISOR_SYSTEM_PROMPT
from utils.llm_factory import get_llm

from agents.project_agent import create_project_agent
from agents.task_agent import create_task_agent
from agents.general_agent import create_general_agent

# =============================================================================
# 1. KHỞI TẠO AGENTS & TOOLS
# =============================================================================
project_agent_model, project_tools = create_project_agent()
task_agent_model, task_tools = create_task_agent()
general_agent_model = create_general_agent()


# =============================================================================
# 2. ĐỊNH NGHĨA CÁC NODE (CÔNG VIỆC CỤ THỂ)
# =============================================================================
def project_node(state: AgentState):
    """Xử lý Project - CHỈ sử dụng project_tools"""
    response = project_agent_model.invoke({"messages": state["messages"]})
    return {"messages": [response]}


def task_node(state: AgentState):
    """Xử lý Task - CHỈ sử dụng task_tools"""
    response = task_agent_model.invoke({"messages": state["messages"]})
    return {"messages": [response]}


def general_node(state: AgentState):
    """Xử lý General - Chào hỏi, ngày giờ"""
    response = general_agent_model.invoke({"messages": state["messages"]})
    return {"messages": [response]}


# =============================================================================
# 3. SUPERVISOR NODE (BỘ NÃO ĐIỀU HƯỚNG)
# =============================================================================
def supervisor_node(state: AgentState):
    messages = state["messages"]
    last_user_msg = messages[-1]

    # Chuẩn hóa input người dùng
    user_text = str(last_user_msg.content).lower()

    if not isinstance(last_user_msg, HumanMessage):
        return {"next": "END"}

    # --- A. LOGIC GHIM LUỒNG (STICKY ROUTING) - QUAN TRỌNG ---
    if len(messages) >= 2:
        last_ai_msg = messages[-2]
        if isinstance(last_ai_msg, AIMessage):
            ai_text = str(last_ai_msg.content).lower()

            # [FIX 1]: Nếu AI vừa liệt kê "Thông tin dự án" -> Câu tiếp theo chắc chắn là xử lý Dự án
            # Giúp sửa lỗi: User nói "sửa trạng thái" bị router đá sang Task_Agent
            if "thông tin dự án" in ai_text or "mã dự án" in ai_text or "project code" in ai_text:
                print(f"\n[ROUTER STICKY] Context là Project Info -> Giữ tại Project_Agent")
                return {"next": "Project_Agent"}

            # [FIX 2]: Logic xác nhận hành động (Confirm)
            keywords_confirm = ["xác nhận", "thực hiện không", "đồng ý", "chắc chắn", "bảng dưới đây", "muốn xóa"]
            if any(k in ai_text for k in keywords_confirm):
                print(f"\n[ROUTER STICKY] AI đang chờ xác nhận...")
                # Ưu tiên Task Agent nếu có từ khóa liên quan task
                if any(x in ai_text for x in ["task", "excel", "công việc", "id:"]):
                    return {"next": "Task_Agent"}
                # Ưu tiên Project Agent
                if "dự án" in ai_text or "project" in ai_text:
                    return {"next": "Project_Agent"}

    # --- B. LOGIC AI ROUTER (DEEP CONTEXT) ---
    recent_msgs = messages[-6:]
    history_str = ""
    for m in recent_msgs:
        role = "User" if isinstance(m, HumanMessage) else "AI"
        content = m.content if isinstance(m.content, str) else str(m.content)
        history_str += f"- {role}: {content[:150]}...\n"

    # Dùng model riêng cho Supervisor
    llm = get_llm(temperature=0, role="supervisor")

    router_prompt = (
        f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
        f"=== LỊCH SỬ HỘI THOẠI (CONTEXT) ===\n"
        f"{history_str}\n"
        f"===================================\n"
        f"USER INPUT HIỆN TẠI: '{last_user_msg.content}'\n\n"
        "NHIỆM VỤ: Phân loại yêu cầu này thuộc về Agent nào.\n"
        "LỰA CHỌN: [Project_Agent, Task_Agent, General_Agent]\n"
        "CHÚ Ý: Chỉ trả về tên Agent, không giải thích gì thêm.\n"
        "QUYẾT ĐỊNH:"
    )

    result = llm.invoke(router_prompt).content.strip()
    print(f"\n[ROUTER AI] Deep Context -> Selected: {result}")

    # So khớp chuỗi kết quả
    if "Task" in result: return {"next": "Task_Agent"}
    if "Project" in result: return {"next": "Project_Agent"}
    if "General" in result: return {"next": "General_Agent"}

    # Fallback thủ công nếu AI Router trả về linh tinh nhưng user có ý định rõ ràng
    if "dự án" in user_text or "project" in user_text: return {"next": "Project_Agent"}
    if "task" in user_text or "công việc" in user_text: return {"next": "Task_Agent"}

    return {"next": "General_Agent"}  # Mặc định


# =============================================================================
# 4. XÂY DỰNG GRAPH (WORKFLOW)
# =============================================================================
workflow = StateGraph(AgentState)

workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Project_Agent", project_node)
workflow.add_node("Task_Agent", task_node)
workflow.add_node("General_Agent", general_node)

# ToolNode chứa các tool riêng biệt
workflow.add_node("project_tools", ToolNode(project_tools))
workflow.add_node("task_tools", ToolNode(task_tools))

workflow.add_edge(START, "Supervisor")

# Điều hướng từ Supervisor
workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {
        "Project_Agent": "Project_Agent",
        "Task_Agent": "Task_Agent",
        "General_Agent": "General_Agent",
        "END": END
    }
)


# Vòng lặp Tool Call cho Project_Agent
def project_cond(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "project_tools"
    return "END"


workflow.add_conditional_edges("Project_Agent", project_cond, {"project_tools": "project_tools", "END": END})
workflow.add_edge("project_tools", "Project_Agent")


# Vòng lặp Tool Call cho Task_Agent
def task_cond(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "task_tools"
    return "END"


workflow.add_conditional_edges("Task_Agent", task_cond, {"task_tools": "task_tools", "END": END})
workflow.add_edge("task_tools", "Task_Agent")

workflow.add_edge("General_Agent", END)

app = workflow.compile(checkpointer=MemorySaver())