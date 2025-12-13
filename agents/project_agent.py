from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm

# --- IMPORT CÁC TOOL CỦA PROJECT SERVICE ---
from mcp_servers.project_service.tools import (
    create_project,       # Tạo dự án
    update_project,       # Cập nhật dự án
    delete_project,       # Xóa dự án
    get_project_details,  # Xem chi tiết
    get_user_profile,     # Xem profile chung (để lấy ID Company/Workspace)
    get_current_date,     # Lấy ngày giờ
    find_project_context, # Tra cứu ID dự án từ tên
    lookup_hierarchy,     # Tra cứu ID Công ty/Workspace (cho việc tạo dự án)
    get_workspace_projects # <--- [MỚI] Tool lấy danh sách dự án đầy đủ
)

# Import Prompt (Lấy từ file __init
# __.py như cấu trúc cũ bạn đang giữ)
from orchestrator.prompts import PROJECT_AGENT_SYSTEM_PROMPT


def create_project_agent():
    # Khởi tạo LLM (Temperature=0 để giảm ảo giác)
    llm = get_llm(temperature=0)

    # --- ĐĂNG KÝ DANH SÁCH TOOL ---
    # Agent sẽ được phép sử dụng tất cả 9 công cụ này
    tools = [
        # 1. Nhóm thao tác (CRUD)
        create_project,
        update_project,
        delete_project,

        # 2. Nhóm thông tin
        get_project_details,
        get_user_profile,
        get_current_date,

        # 3. Nhóm tra cứu & Danh sách
        find_project_context,  # Tìm 1 dự án
        lookup_hierarchy,      # Tìm nơi tạo dự án
        get_workspace_projects # <--- [QUAN TRỌNG] Lấy danh sách dự án (Fix lỗi thiếu data)
    ]

    # Thiết lập Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROJECT_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    agent = prompt | llm.bind_tools(tools)

    return agent, tools