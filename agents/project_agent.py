from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm
# Import thêm tool get_current_date
from mcp_servers.project_service.tools import create_project, get_user_profile, get_current_date
from orchestrator.prompts import PROJECT_AGENT_SYSTEM_PROMPT


def create_project_agent():
    llm = get_llm(temperature=0)

    # Đưa tool xem ngày vào danh sách
    tools = [create_project, get_user_profile, get_current_date]

    prompt = ChatPromptTemplate.from_messages([
        ("system", PROJECT_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    agent = prompt | llm.bind_tools(tools)
    return agent, tools