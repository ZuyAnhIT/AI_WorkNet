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

# 1. Init Agents
project_agent_model, project_tools = create_project_agent()
task_agent_model, task_tools = create_task_agent()


# 2. Nodes
def project_node(state: AgentState):
    return {"messages": [project_agent_model.invoke(state["messages"])]}


def task_node(state: AgentState):
    return {"messages": [task_agent_model.invoke(state["messages"])]}


def supervisor_node(state: AgentState):
    messages = state["messages"]
    last_user_msg = messages[-1]

    # Nếu không phải user chat -> End
    if not isinstance(last_user_msg, HumanMessage):
        return {"next": "END"}

    # --- LOGIC MỚI: LẤY THÊM NGỮ CẢNH CŨ ---
    # Lấy tin nhắn trước đó của AI (nếu có) để biết AI vừa hỏi gì
    last_ai_msg_content = "Không có"
    if len(messages) >= 2 and isinstance(messages[-2], AIMessage):
        last_ai_msg_content = messages[-2].content

    llm = get_llm(temperature=0)

    # Prompt thông minh hơn: Đưa cả ngữ cảnh vào
    router_prompt = (
        f"{SUPERVISOR_SYSTEM_PROMPT}\n\n"
        f"--- CONTEXT ---\n"
        f"AI vừa nói: '{last_ai_msg_content}'\n"
        f"User vừa trả lời: '{last_user_msg.content}'\n"
        "-----------------\n"
        "Dựa vào Context trên, User đang nói chuyện với ai? (Project_Agent hay Task_Agent)?\n"
        "Gợi ý: Nếu AI vừa hỏi xác nhận tạo Task, và User nói 'đồng ý' -> Chọn Task_Agent."
    )

    result = llm.invoke(router_prompt).content.strip()

    print(
        f"\n[ROUTER DEBUG] Context: AI('{last_ai_msg_content[:20]}...') -> User('{last_user_msg.content}') => Selected: {result}")

    if "Task" in result: return {"next": "Task_Agent"}
    return {"next": "Project_Agent"}


# 3. Graph Construction
workflow = StateGraph(AgentState)

workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Project_Agent", project_node)
workflow.add_node("Task_Agent", task_node)
workflow.add_node("project_tools", ToolNode(project_tools))
workflow.add_node("task_tools", ToolNode(task_tools))

workflow.add_edge(START, "Supervisor")

# Conditional Edges for Supervisor
workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {"Project_Agent": "Project_Agent", "Task_Agent": "Task_Agent", "END": END}
)


# Logic Project Agent
def project_cond(state):
    if state["messages"][-1].tool_calls: return "project_tools"
    return "END"


workflow.add_conditional_edges(
    "Project_Agent",
    project_cond,
    {"project_tools": "project_tools", "END": END}
)
workflow.add_edge("project_tools", "Project_Agent")


# Logic Task Agent
def task_cond(state):
    if state["messages"][-1].tool_calls: return "task_tools"
    return "END"


workflow.add_conditional_edges(
    "Task_Agent",
    task_cond,
    {"task_tools": "task_tools", "END": END}
)
workflow.add_edge("task_tools", "Task_Agent")

app = workflow.compile(checkpointer=MemorySaver())