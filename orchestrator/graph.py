from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from orchestrator.state import AgentState
from orchestrator.prompts import SUPERVISOR_SYSTEM_PROMPT
from utils.llm_factory import get_llm

# --- IMPORT CÁC AGENT & MANAGER ---
from agents.project_agent import create_project_agent
from agents.task_agent import create_task_agent
from agents.general_agent import create_general_agent
from agents.analytics_agent import create_analytics_agent  # [NEW]

# Import cho Analytics Agent (Gemini)
from orchestrator.prompts.analytics import ANALYTICS_AGENT_SYSTEM_PROMPT
from utils.gemini_manager import analytics_engine

# =============================================================================
# 1. KHỞI TẠO AGENTS & TOOLS
# =============================================================================
# Agent Project (Quản lý dự án/workspace)
project_agent_model, project_tools = create_project_agent()

# Agent Task (CRUD Task)
task_agent_model, task_tools = create_task_agent()

# Agent General (Chém gió)
general_agent_model = create_general_agent()

# [NEW] Agent Analytics (Phân tích, Dự báo, Gợi ý)
# Lưu ý: Ta chỉ lấy tools, model sẽ được lấy động từ Gemini Manager
analytics_tools = create_analytics_agent()


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


# [NEW] Node chuyên gia phân tích (Gemini Multi-Key + Tools)
def analytics_node(state: AgentState):
    """
    Xử lý Phân tích/Báo cáo - Sử dụng Gemini Multi-Key.
    Node này có khả năng bind tools để Gemini biết cách gọi API.
    """
    print("📊 [Router] Chuyển hướng sang ANALYTICS AGENT (Gemini)...")

    # Ghép System Prompt chuyên gia vào đầu context
    messages = [
                   {"role": "system", "content": ANALYTICS_AGENT_SYSTEM_PROMPT},
               ] + state["messages"]

    try:
        # 1. Lấy model từ Manager (đã load key hiện tại)
        llm = analytics_engine.get_llm()

        # 2. Bind Tools: Gắn tool vào model để Gemini biết cách gọi
        llm_with_tools = llm.bind_tools(analytics_tools)

        # 3. Gọi model
        # Lưu ý: Ta gọi trực tiếp invoke để giữ tính năng tool binding.
        response = llm_with_tools.invoke(messages)

    except Exception as e:
        print(f"⚠️ [Analytics Error]: {str(e)}")
        # Kích hoạt đổi key cho lần sau (phòng trường hợp lỗi do Quota)
        analytics_engine._rotate_key()

        # Fallback response nếu crash
        response = AIMessage(
            content=f"⚠️ Hệ thống phân tích đang bận hoặc gặp lỗi kết nối. Vui lòng thử lại. (Lỗi: {str(e)})")

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

    # --- A. LOGIC GHIM LUỒNG (STICKY ROUTING) ---
    if len(messages) >= 2:
        last_ai_msg = messages[-2]
        if isinstance(last_ai_msg, AIMessage):
            ai_text = str(last_ai_msg.content).lower()

            # Nếu AI trước đó đang nói về thông tin dự án -> Giữ tại Project
            if "thông tin dự án" in ai_text or "mã dự án" in ai_text:
                return {"next": "Project_Agent"}

            # [NEW] Nếu AI trước đó đang phân tích/đề xuất -> Giữ tại Analytics
            # Ví dụ: AI vừa hỏi "Bạn muốn giao cho ai?", User trả lời "Chọn ông A" -> Vẫn phải vào Analytics để xử lý tiếp nếu cần
            analytics_stickies = ["đề xuất", "dự báo", "kịch bản", "rủi ro", "standup", "báo cáo"]
            if any(k in ai_text for k in analytics_stickies):
                return {"next": "Analytics_Agent"}

            # Xác nhận hành động chung
            keywords_confirm = ["xác nhận", "thực hiện không", "đồng ý", "chắc chắn", "bảng dưới đây"]
            if any(k in ai_text for k in keywords_confirm):
                if any(x in ai_text for x in ["task", "excel", "công việc"]):
                    return {"next": "Task_Agent"}
                if "dự án" in ai_text:
                    return {"next": "Project_Agent"}

    # --- B. LOGIC AI ROUTER (DEEP CONTEXT) ---
    recent_msgs = messages[-6:]
    history_str = ""
    for m in recent_msgs:
        role = "User" if isinstance(m, HumanMessage) else "AI"
        content = m.content if isinstance(m.content, str) else str(m.content)
        history_str += f"- {role}: {content[:150]}...\n"

    # Dùng model riêng cho Supervisor (thường là model nhanh/nhẹ)
    llm = get_llm(temperature=0, role="supervisor")

    # [UPDATED] Cập nhật Prompt cho Router để biết về Analytics Agent
    router_prompt = (
        f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
        f"=== PHÂN LOẠI AGENT THEO CHỨC NĂNG ===\n"
        f"1. **Analytics_Agent (Chuyên gia Phân tích):**\n"
        f"   - Giao việc: 'Giao cho ai?', 'Ai rảnh?', 'Ai nên làm task này?'.\n"
        f"   - Dự báo/Tiến độ: 'Bao giờ xong?', 'Kịp deadline không?', 'Tiến độ dự án'.\n"
        f"   - Báo cáo: 'Hôm nay team làm gì?', 'Daily Standup', 'Tình hình công việc', 'Danh sách thành viên'.\n"
        f"   - Phân tích sâu: 'Tại sao chậm?', 'Đánh giá rủi ro'.\n\n"
        f"2. **Task_Agent (Thực thi - Chân tay):**\n"
        f"   - Tạo/Sửa/Xóa task: 'Tạo task mới', 'Xóa task cũ', 'Sửa tiêu đề'.\n"
        f"   - Liệt kê task: 'Danh sách task', 'Tìm task'.\n"
        f"   - Xử lý File: 'Đọc file excel', 'Tạo task từ file'.\n\n"
        f"3. **Project_Agent:** Quản lý dự án, workspace, thông tin công ty.\n"
        f"===================================\n"
        f"=== LỊCH SỬ HỘI THOẠI ===\n"
        f"{history_str}\n"
        f"===================================\n"
        f"USER INPUT HIỆN TẠI: '{last_user_msg.content}'\n\n"
        "NHIỆM VỤ: Phân loại yêu cầu này thuộc về Agent nào.\n"
        "LỰA CHỌN: [Project_Agent, Task_Agent, General_Agent, Analytics_Agent]\n"
        "CHÚ Ý: Chỉ trả về tên Agent.\n"
        "QUYẾT ĐỊNH:"
    )

    result = llm.invoke(router_prompt).content.strip()
    print(f"\n[ROUTER AI] Deep Context -> Selected: {result}")

    # So khớp chuỗi kết quả
    if "Analytics" in result: return {"next": "Analytics_Agent"}  # [NEW]
    if "Task" in result: return {"next": "Task_Agent"}
    if "Project" in result: return {"next": "Project_Agent"}
    if "General" in result: return {"next": "General_Agent"}

    # --- C. FALLBACK THỦ CÔNG (Keyword Mapping) ---
    # Nhóm Analytics
    if any(k in user_text for k in
           ["phân tích", "tại sao", "rủi ro", "chiến lược", "báo cáo", "dự báo", "standup", "thành viên", "giao cho ai",
            "ai rảnh"]):
        return {"next": "Analytics_Agent"}
    # Nhóm Project
    if "dự án" in user_text or "project" in user_text: return {"next": "Project_Agent"}
    # Nhóm Task
    if "task" in user_text or "công việc" in user_text: return {"next": "Task_Agent"}

    return {"next": "General_Agent"}


# =============================================================================
# 4. XÂY DỰNG GRAPH (WORKFLOW)
# =============================================================================
workflow = StateGraph(AgentState)

# --- Add Nodes ---
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Project_Agent", project_node)
workflow.add_node("Task_Agent", task_node)
workflow.add_node("General_Agent", general_node)
workflow.add_node("Analytics_Agent", analytics_node)  # [NEW] Node Analytics

# --- Add Tool Nodes (Nơi thực thi code Python) ---
workflow.add_node("project_tools", ToolNode(project_tools))
workflow.add_node("task_tools", ToolNode(task_tools))
workflow.add_node("analytics_tools", ToolNode(analytics_tools))  # [NEW] Node Tool Analytics

# --- Edges bắt đầu ---
workflow.add_edge(START, "Supervisor")

# --- Điều hướng từ Supervisor ---
workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {
        "Project_Agent": "Project_Agent",
        "Task_Agent": "Task_Agent",
        "General_Agent": "General_Agent",
        "Analytics_Agent": "Analytics_Agent",  # [NEW]
        "END": END
    }
)


# --- Vòng lặp Tool Call cho Project_Agent ---
def project_cond(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "project_tools"
    return "END"


workflow.add_conditional_edges("Project_Agent", project_cond, {"project_tools": "project_tools", "END": END})
workflow.add_edge("project_tools", "Project_Agent")


# --- Vòng lặp Tool Call cho Task_Agent ---
def task_cond(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "task_tools"
    return "END"


workflow.add_conditional_edges("Task_Agent", task_cond, {"task_tools": "task_tools", "END": END})
workflow.add_edge("task_tools", "Task_Agent")


# --- [NEW] Vòng lặp Tool Call cho Analytics_Agent ---
# Logic: Nếu Gemini trả về tool_calls -> Chạy node analytics_tools -> Quay lại Gemini
def analytics_cond(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "analytics_tools"
    return "END"


workflow.add_conditional_edges("Analytics_Agent", analytics_cond, {"analytics_tools": "analytics_tools", "END": END})
workflow.add_edge("analytics_tools", "Analytics_Agent")

# --- Edge kết thúc cho General ---
workflow.add_edge("General_Agent", END)

# Compile Graph
app = workflow.compile(checkpointer=MemorySaver())