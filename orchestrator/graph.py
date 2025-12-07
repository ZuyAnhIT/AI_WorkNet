from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage
from orchestrator.state import AgentState
from orchestrator.prompts import SUPERVISOR_SYSTEM_PROMPT
from utils.llm_factory import get_llm

# Import Agents (Đủ 3 nhân viên)
from agents.project_agent import create_project_agent
from agents.task_agent import create_task_agent
from agents.general_agent import create_general_agent  # <--- MỚI

# 1. Init Agents
project_agent_model, project_tools = create_project_agent()
task_agent_model, task_tools = create_task_agent()
general_agent_model = create_general_agent()  # <--- MỚI


# 2. Nodes
def project_node(state: AgentState):
    return {"messages": [project_agent_model.invoke(state["messages"])]}


def task_node(state: AgentState):
    return {"messages": [task_agent_model.invoke(state["messages"])]}


def general_node(state: AgentState):  # <--- MỚI
    return {"messages": [general_agent_model.invoke(state["messages"])]}


def supervisor_node(state: AgentState):
    messages = state["messages"]
    last_user_msg = messages[-1]

    if not isinstance(last_user_msg, HumanMessage): return {"next": "END"}

    # --- STICKY ROUTING (Ghim luồng) ---
    if len(messages) >= 2:
        last_ai_msg = messages[-2]
        if isinstance(last_ai_msg, AIMessage):
            ai_content = last_ai_msg.content.lower()
            # Nếu đang dở việc với Task (Import excel, tạo task...) -> Giữ Task Agent
            if "import" in ai_content or "tạo task" in ai_content or "excel" in ai_content or "dự án đích" in ai_content:
                print(f"\n[ROUTER STICKY] -> Task_Agent")
                return {"next": "Task_Agent"}

    # --- AI ROUTER ---
    llm = get_llm(temperature=0)
    router_prompt = (
        f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
        f"User Input: '{last_user_msg.content}'\n"
        "CHỈ TRẢ VỀ: 'Project_Agent', 'Task_Agent', hoặc 'General_Agent'."
    )
    result = llm.invoke(router_prompt).content.strip()

    print(f"\n[ROUTER DEBUG] User: '{last_user_msg.content}' -> Selected: {result}")

    # Map kết quả AI ra tên Node
    if "Task" in result: return {"next": "Task_Agent"}
    if "General" in result: return {"next": "General_Agent"}  # <--- MỚI
    return {"next": "Project_Agent"}


# 3. Graph Construction
workflow = StateGraph(AgentState)

workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Project_Agent", project_node)
workflow.add_node("Task_Agent", task_node)
workflow.add_node("General_Agent", general_node)  # <--- MỚI
workflow.add_node("project_tools", ToolNode(project_tools))
workflow.add_node("task_tools", ToolNode(task_tools))

workflow.add_edge(START, "Supervisor")

# Conditional Edges
workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {
        "Project_Agent": "Project_Agent",
        "Task_Agent": "Task_Agent",
        "General_Agent": "General_Agent",  # <--- MỚI
        "END": END
    }
)


# Logic Project
def project_cond(state):
    return "project_tools" if state["messages"][-1].tool_calls else "END"


workflow.add_conditional_edges("Project_Agent", project_cond, {"project_tools": "project_tools", "END": END})
workflow.add_edge("project_tools", "Project_Agent")


# Logic Task
def task_cond(state):
    return "task_tools" if state["messages"][-1].tool_calls else "END"


workflow.add_conditional_edges("Task_Agent", task_cond, {"task_tools": "task_tools", "END": END})
workflow.add_edge("task_tools", "Task_Agent")

# Logic General (Chỉ trả lời rồi nghỉ)
workflow.add_edge("General_Agent", END)

app = workflow.compile(checkpointer=MemorySaver())