from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm

# --- QUAN TRỌNG: Import đủ 4 tool (Tạo lẻ, Tra cứu, Excel, Batch Text) ---
from mcp_servers.task_service.tools import (
    create_task,
    get_my_projects_context,
    create_tasks_from_excel,
    create_tasks_batch  # <--- Tool mới dùng để tạo hàng loạt từ Text
)
from orchestrator.prompts import TASK_AGENT_SYSTEM_PROMPT


def create_task_agent():
    # Khởi tạo LLM
    llm = get_llm(temperature=0)

    # --- ĐĂNG KÝ DANH SÁCH TOOL ---
    # Agent sẽ được phép sử dụng 4 công cụ này
    tools = [
        create_task,  # 1. Tạo 1 task thủ công
        get_my_projects_context,  # 2. Tra cứu ID dự án
        create_tasks_from_excel,  # 3. Đọc file Excel tạo nhiều task
        create_tasks_batch  # 4. Tạo nhiều task từ danh sách Text/Chat
    ]

    # Thiết lập Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", TASK_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    agent = prompt | llm.bind_tools(tools)

    return agent, tools