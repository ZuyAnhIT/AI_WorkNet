from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm

# --- QUAN TRỌNG: Import đủ 6 tool của Project Service ---
from mcp_servers.project_service.tools import (
    create_project,
    get_user_profile,
    get_current_date,
    delete_project,
    get_project_details,
    update_project  # <--- Tool mới thêm để cập nhật dự án
)
from orchestrator.prompts import PROJECT_AGENT_SYSTEM_PROMPT


def create_project_agent():
    # Khởi tạo LLM
    llm = get_llm(temperature=0)

    # --- ĐĂNG KÝ DANH SÁCH TOOL ---
    # Agent sẽ được phép sử dụng 6 công cụ này
    tools = [
        create_project,  # Tạo dự án mới
        get_user_profile,  # Tra cứu ID Company/Workspace/Project
        get_current_date,  # Lấy ngày giờ hiện tại
        delete_project,  # Xóa dự án
        get_project_details,  # Xem chi tiết tiến độ dự án
        update_project  # Cập nhật thông tin dự án
    ]

    # Thiết lập Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROJECT_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    agent = prompt | llm.bind_tools(tools)

    return agent, tools