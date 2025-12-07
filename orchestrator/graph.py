from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage
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

    # ========================================================================
    # LOGIC GHIM LUỒNG (STICKY ROUTING) - CỰC KỲ QUAN TRỌNG
    # ========================================================================
    if len(messages) >= 2:
        last_ai_msg = messages[-2]
        if isinstance(last_ai_msg, AIMessage):
            # Xử lý nội dung AI (nếu là list thì nối lại)
            raw = last_ai_msg.content
            ai_text = ""
            if isinstance(raw, str):
                ai_text = raw
            elif isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str):
                        ai_text += item
                    elif isinstance(item, dict):
                        ai_text += item.get("text", "")

            ai_text = ai_text.lower()

            # 1. NẾU AI ĐANG HỎI XÁC NHẬN (CONFIRMATION STICKY)
            # Dấu hiệu: "xác nhận thông tin", "thực hiện không", "đồng ý"
            if "xác nhận" in ai_text or "thực hiện không" in ai_text or "đồng ý" in ai_text:
                print(f"\n[ROUTER STICKY] AI đang chờ xác nhận -> Kiểm tra ngữ cảnh...")

                # Nếu nội dung xác nhận có chứa từ khóa của Task
                if "task" in ai_text or "excel" in ai_text or "danh sách" in ai_text or "số lượng" in ai_text:
                    print("   -> Điều hướng về: Task_Agent")
                    return {"next": "Task_Agent"}

                # Nếu nội dung xác nhận có chứa từ khóa của Project
                if "dự án" in ai_text or "project" in ai_text:
                    print("   -> Điều hướng về: Project_Agent")
                    return {"next": "Project_Agent"}

            # 2. NẾU ĐANG TRONG LUỒNG IMPORT EXCEL/BATCH
            if "import" in ai_text or "file excel" in ai_text or "dự án đích" in ai_text:
                print(f"\n[ROUTER STICKY] Đang xử lý Excel -> Task_Agent")
                return {"next": "Task_Agent"}

    # ========================================================================
    # LOGIC AI ROUTER (NẾU KHÔNG CÓ STICKY)
    # ========================================================================
    llm = get_llm(temperature=0)
    router_prompt = (
        f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
        f"User Input: '{last_user_msg.content}'\n"
        "CHỈ TRẢ VỀ: 'Project_Agent', 'Task_Agent', hoặc 'General_Agent'."
    )
    result = llm.invoke(router_prompt).content.strip()

    print(f"\n[ROUTER DEBUG] User: '{last_user_msg.content}' -> Selected: {result}")

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
    {
        "Project_Agent": "Project_Agent",
        "Task_Agent": "Task_Agent",
        "General_Agent": "General_Agent",
        "END": END
    }
)


def project_cond(state):
    return "project_tools" if state["messages"][-1].tool_calls else "END"


workflow.add_conditional_edges("Project_Agent", project_cond, {"project_tools": "project_tools", "END": END})
workflow.add_edge("project_tools", "Project_Agent")


def task_cond(state):
    return "task_tools" if state["messages"][-1].tool_calls else "END"


workflow.add_conditional_edges("Task_Agent", task_cond, {"task_tools": "task_tools", "END": END})
workflow.add_edge("task_tools", "Task_Agent")

workflow.add_edge("General_Agent", END)

app = workflow.compile(checkpointer=MemorySaver())