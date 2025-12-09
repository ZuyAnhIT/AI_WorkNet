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
# Tạo các instance của Agent và lấy danh sách tool tương ứng
project_agent_model, project_tools = create_project_agent()
task_agent_model, task_tools = create_task_agent()
general_agent_model = create_general_agent()


# =============================================================================
# 2. ĐỊNH NGHĨA CÁC NODE (CÔNG VIỆC CỤ THỂ)
# =============================================================================
def project_node(state: AgentState):
    """Node xử lý các vấn đề về Dự án (Tạo, Sửa, Xóa Project)"""
    return {"messages": [project_agent_model.invoke(state["messages"])]}


def task_node(state: AgentState):
    """Node xử lý các vấn đề về Task (Tạo, Xóa, Excel, List Task)"""
    return {"messages": [task_agent_model.invoke(state["messages"])]}


def general_node(state: AgentState):
    """Node xử lý các câu hỏi chung chung (Chào hỏi, hỏi ngày giờ...)"""
    return {"messages": [general_agent_model.invoke(state["messages"])]}


# =============================================================================
# 3. SUPERVISOR NODE (BỘ NÃO ĐIỀU HƯỚNG)
# =============================================================================
def supervisor_node(state: AgentState):
    messages = state["messages"]
    last_user_msg = messages[-1]

    # Nếu tin nhắn cuối không phải của người dùng, kết thúc (tránh loop)
    if not isinstance(last_user_msg, HumanMessage):
        return {"next": "END"}

    # ------------------------------------------------------------------------
    # A. LOGIC GHIM LUỒNG (STICKY ROUTING) - QUAN TRỌNG CHO QUY TRÌNH DELETE/IMPORT
    # ------------------------------------------------------------------------
    if len(messages) >= 2:
        last_ai_msg = messages[-2]
        if isinstance(last_ai_msg, AIMessage):
            # 1. Lấy nội dung tin nhắn trước đó của AI để phân tích ngữ cảnh
            raw = last_ai_msg.content
            ai_text = ""
            if isinstance(raw, str):
                ai_text = raw
            elif isinstance(raw, list):
                # Xử lý trường hợp content là list (multimodal/tool calls)
                for item in raw:
                    if isinstance(item, str):
                        ai_text += item
                    elif isinstance(item, dict):
                        ai_text += item.get("text", "")

            ai_text = ai_text.lower()

            # 2. Check dấu hiệu đang chờ xác nhận (Confirmation Loop)
            # Các từ khóa cho thấy AI đang đợi user trả lời Yes/No hoặc chọn ID
            keywords_confirm = ["xác nhận", "thực hiện không", "đồng ý", "chắc chắn", "bảng dưới đây", "muốn xóa"]

            if any(k in ai_text for k in keywords_confirm):
                print(f"\n[ROUTER STICKY] AI đang chờ xác nhận... Phân tích ngữ cảnh.")

                # Ưu tiên 1: Nếu đang nói về XÓA TASK, ID, EXCEL -> Task_Agent
                if "task" in ai_text or "excel" in ai_text or "công việc" in ai_text or "id:" in ai_text:
                    print("   -> Context: Task_Agent (Sticky for Delete/Excel)")
                    return {"next": "Task_Agent"}

                # Ưu tiên 2: Nếu chỉ nói về DỰ ÁN (và không có từ khóa task) -> Project_Agent
                if ("dự án" in ai_text or "project" in ai_text) and "task" not in ai_text:
                    print("   -> Context: Project_Agent (Sticky for Project)")
                    return {"next": "Project_Agent"}

                # Ưu tiên 3: Fallback về Project nếu còn nghi ngờ
                if "dự án" in ai_text:
                    return {"next": "Project_Agent"}

            # 3. Check nếu đang trong luồng Excel/Batch (Luôn là Task Agent)
            if "import" in ai_text or "file excel" in ai_text or "dự án đích" in ai_text:
                print(f"\n[ROUTER STICKY] Đang xử lý Excel -> Task_Agent")
                return {"next": "Task_Agent"}

    # ------------------------------------------------------------------------
    # B. LOGIC AI ROUTER (DEEP CONTEXT) - DÙNG LLM ĐỂ CHỌN KHI BẮT ĐẦU
    # ------------------------------------------------------------------------

    # Lấy 6 tin nhắn gần nhất để AI hiểu ngữ cảnh
    recent_msgs = messages[-6:]
    history_str = ""
    for m in recent_msgs:
        role = "User" if isinstance(m, HumanMessage) else "AI"
        content = m.content if isinstance(m.content, str) else str(m.content)
        history_str += f"- {role}: {content[:150]}...\n"

    # Dùng LLM đóng vai Supervisor chuyên nghiệp
    llm = get_llm(temperature=0, role="supervisor")

    router_prompt = (
        f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
        f"=== LỊCH SỬ HỘI THOẠI (CONTEXT) ===\n"
        f"{history_str}\n"
        f"===================================\n"
        f"USER INPUT HIỆN TẠI: '{last_user_msg.content}'\n\n"
        "NHIỆM VỤ: Dựa vào lịch sử và input, hãy chọn 1 Agent duy nhất để xử lý.\n"
        "LỰA CHỌN: [Project_Agent, Task_Agent, General_Agent]\n"
        "CHÚ Ý: \n"
        "- Nếu liên quan đến Task, Công việc, Excel, Import, Xóa công việc -> Task_Agent\n"
        "- Nếu liên quan đến Dự án (Tạo, Sửa, Xóa Project tổng) -> Project_Agent\n"
        "- Còn lại -> General_Agent\n"
        "QUYẾT ĐỊNH (Chỉ trả về tên Agent):"
    )

    result = llm.invoke(router_prompt).content.strip()

    print(f"\n[ROUTER AI] Deep Context -> Selected: {result}")

    if "Task" in result: return {"next": "Task_Agent"}
    if "General" in result: return {"next": "General_Agent"}
    return {"next": "Project_Agent"}  # Mặc định an toàn


# =============================================================================
# 4. XÂY DỰNG GRAPH (WORKFLOW)
# =============================================================================
workflow = StateGraph(AgentState)

# Thêm các Node
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Project_Agent", project_node)
workflow.add_node("Task_Agent", task_node)
workflow.add_node("General_Agent", general_node)

# Thêm các Tool Node (Để Agent có thể thực thi hành động)
workflow.add_node("project_tools", ToolNode(project_tools))
workflow.add_node("task_tools", ToolNode(task_tools))

# Điểm bắt đầu
workflow.add_edge(START, "Supervisor")

# Điều kiện rẽ nhánh từ Supervisor
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


# --- VÒNG LẶP CHO PROJECT AGENT (Model -> Tool -> Model) ---
def project_cond(state):
    # Nếu Agent muốn gọi Tool -> Chuyển sang node project_tools
    # Nếu Agent đã trả lời xong -> Kết thúc (END)
    return "project_tools" if state["messages"][-1].tool_calls else "END"


workflow.add_conditional_edges("Project_Agent", project_cond, {"project_tools": "project_tools", "END": END})
workflow.add_edge("project_tools", "Project_Agent")  # Tool chạy xong thì quay lại Agent để báo cáo


# --- VÒNG LẶP CHO TASK AGENT (Model -> Tool -> Model) ---
def task_cond(state):
    return "task_tools" if state["messages"][-1].tool_calls else "END"


workflow.add_conditional_edges("Task_Agent", task_cond, {"task_tools": "task_tools", "END": END})
workflow.add_edge("task_tools", "Task_Agent")

# --- GENERAL AGENT (Chạy 1 lần rồi kết thúc) ---
workflow.add_edge("General_Agent", END)

# Compile Graph với bộ nhớ (Checkpointer)
app = workflow.compile(checkpointer=MemorySaver())