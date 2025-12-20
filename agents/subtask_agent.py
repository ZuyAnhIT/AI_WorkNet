from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm

# --- IMPORT TOOL TÌM KIẾM ---
from mcp_servers.subtask_service.tools import get_project_tasks

# Import Prompt điều khiển
from orchestrator.prompts.subtask import SUBTASK_AGENT_SYSTEM_PROMPT

def create_subtask_agent():
    # Khởi tạo model với temperature=0
    llm = get_llm(temperature=0, role="subtask_agent")

    # Đăng ký tool (Hiện tại chỉ có tool xem danh sách)
    tools = [get_project_tasks]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SUBTASK_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Bind tool vào Agent
    agent = prompt | llm.bind_tools(tools)

    return agent, tools