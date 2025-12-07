from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from orchestrator.state import AgentState
from orchestrator.prompts import SUPERVISOR_SYSTEM_PROMPT
from utils.llm_factory import get_llm

# Import Agents
from agents.project_agent import create_project_agent
from agents.task_agent import create_task_agent
from agents.general_agent import create_general_agent

# 1. Init Agents
project_agent_model, project_tools = create_project_agent()
task_agent_model, task_tools = create_task_agent()
general_agent_model = create_general_agent()


# 2. Nodes
def project_node(state: AgentState):
    return {"messages": [project_agent_model.invoke(state["messages"])]}


def task_node(state: AgentState):
    return {"messages": [task_agent_model.invoke(state["messages"])]}


def general_node(state: AgentState):
    return {"messages": [general_agent_model.invoke(state["messages"])]}


def supervisor_node(state: AgentState):
    messages = state["messages"]
    last_user_msg = messages[-1]

    if not isinstance(last_user_msg, HumanMessage): return {"next": "END"}

    # --- 1. STICKY ROUTING (ƯU TIÊN CAO NHẤT) ---
    # Kiểm tra tin nhắn AI gần nhất để bắt context xác nhận/nhập liệu
    if len(messages) >= 2:
        last_ai_msg = messages[-2]
        if isinstance(last_ai_msg, AIMessage):
            ai_text = ""
            if isinstance(last_ai_msg.content, str):
                ai_text = last_ai_msg.content
            elif isinstance(last_ai_msg.content, list):
                for item in last_ai_msg.content:
                    if isinstance(item, dict): ai_text += item.get("text", "")

            ai_text = ai_text.lower()

            # Nếu đang hỏi xác nhận hoặc xử lý Excel -> Giữ nguyên Agent cũ
            if any(k in ai_text for k in ["xác nhận", "thực hiện không", "đồng ý", "import", "excel"]):
                print(f"\n[ROUTER STICKY] Phát hiện context hội thoại -> Phân tích sâu...")
                if "task" in ai_text or "công việc" in ai_text: return {"next": "Task_Agent"}
                if "dự án" in ai_text or "project" in ai_text: return {"next": "Project_Agent"}

    # --- 2. DEEP CONTEXT ROUTING (AI ĐỌC LỊCH SỬ) ---
    # Lấy 6 tin nhắn gần nhất để AI hiểu ngữ cảnh
    recent_msgs = messages[-6:]
    history_str = ""
    for m in recent_msgs:
        role = "User" if isinstance(m, HumanMessage) else "AI"
        content = m.content if isinstance(m.content, str) else str(m.content)
        history_str += f"- {role}: {content[:100]}...\n"  # Cắt ngắn để đỡ tốn token

    llm = get_llm(temperature=0)

    # Prompt mới: Cung cấp lịch sử hội thoại
    router_prompt = (
        f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
        f"=== LỊCH SỬ HỘI THOẠI GẦN ĐÂY (CONTEXT) ===\n"
        f"{history_str}\n"
        f"===========================================\n"
        f"USER INPUT HIỆN TẠI: '{last_user_msg.content}'\n\n"
        "Dựa vào Lịch sử và Input, hãy chọn Agent phù hợp nhất (Project_Agent / Task_Agent / General_Agent)."
    )

    result = llm.invoke(router_prompt).content.strip()

    print(f"\n[ROUTER AI] History analzyed -> Selected: {result}")

    if "Task" in result: return {"next": "Task_Agent"}
    if "General" in result: return {"next": "General_Agent"}
    return {"next": "Project_Agent"}


# 3. Graph Construction (Giữ nguyên)
workflow = StateGraph(AgentState)

workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Project_Agent", project_node)
workflow.add_node("Task_Agent", task_node)
workflow.add_node("General_Agent", general_node)
workflow.add_node("project_tools", ToolNode(project_tools))
workflow.add_node("task_tools", ToolNode(task_tools))

workflow.add_edge(START, "Supervisor")

workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {"Project_Agent": "Project_Agent", "Task_Agent": "Task_Agent", "General_Agent": "General_Agent", "END": END}
)


def project_cond(state): return "project_tools" if state["messages"][-1].tool_calls else "END"


workflow.add_conditional_edges("Project_Agent", project_cond, {"project_tools": "project_tools", "END": END})
workflow.add_edge("project_tools", "Project_Agent")


def task_cond(state): return "task_tools" if state["messages"][-1].tool_calls else "END"


workflow.add_conditional_edges("Task_Agent", task_cond, {"task_tools": "task_tools", "END": END})
workflow.add_edge("task_tools", "Task_Agent")

workflow.add_edge("General_Agent", END)

app = workflow.compile(checkpointer=MemorySaver())