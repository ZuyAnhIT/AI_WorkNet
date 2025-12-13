from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm

# --- IMPORT CÁC TOOL CỦA PROJECT SERVICE ---
from mcp_servers.project_service.tools import (
    create_project,  # Tạo dự án
    update_project,  # Cập nhật dự án
    delete_project,  # Xóa dự án
    get_project_details,  # Xem chi tiết
    get_user_profile,  # Xem profile chung
    get_current_date,  # Lấy ngày giờ
    find_project_context,  # [QUAN TRỌNG] Tra cứu ID dự án từ tên (cho việc Sửa/Xóa/Xem)
    lookup_hierarchy  # [MỚI] Tra cứu ID Công ty/Workspace (cho việc TẠO dự án)
)

from orchestrator.prompts import PROJECT_AGENT_SYSTEM_PROMPT


def create_project_agent():
    # Khởi tạo LLM
    llm = get_llm(temperature=0)

    # --- ĐĂNG KÝ DANH SÁCH TOOL ---
    # Agent sẽ được phép sử dụng tất cả 8 công cụ này
    tools = [
        # Nhóm thao tác (CRUD)
        create_project,
        update_project,
        delete_project,

        # Nhóm thông tin
        get_project_details,
        get_user_profile,
        get_current_date,

        # Nhóm tra cứu (Lookup)
        find_project_context,  # Giúp tìm dự án đã có
        lookup_hierarchy  # Giúp tìm nơi để tạo dự án mới
    ]

    # Thiết lập Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROJECT_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    agent = prompt | llm.bind_tools(tools)

    return agent, tools