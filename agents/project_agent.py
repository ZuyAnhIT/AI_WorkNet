from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm

# --- IMPORT CÁC TOOL CỦA PROJECT SERVICE ---
from mcp_servers.project_service.tools import (
    create_project,
    update_project,
    delete_project,
    get_project_details,
    get_user_profile,
    get_current_date,
    find_project_context,
    lookup_hierarchy,
    get_workspace_projects,
    get_company_workspaces  # <--- [MỚI] Tool lấy danh sách Workspace theo Company ID
)

# Import Prompt
from orchestrator.prompts import PROJECT_AGENT_SYSTEM_PROMPT


def create_project_agent():
    # Khởi tạo LLM (Temperature=0 để giảm ảo giác)
    llm = get_llm(temperature=0)

    # --- ĐĂNG KÝ DANH SÁCH TOOL ---
    # Agent sẽ được phép sử dụng tất cả 10 công cụ này
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
        find_project_context,   # Tìm 1 dự án
        lookup_hierarchy,       # Tìm nơi tạo dự án (ID Company/Workspace)
        get_workspace_projects, # Lấy danh sách dự án trong Workspace
        get_company_workspaces  # <--- [MỚI] Dùng để mapping tên Workspace sang ID chính xác
    ]

    # Thiết lập Prompt (Lưu ý: Bạn phải cập nhật PROJECT_AGENT_SYSTEM_PROMPT để ép Agent dùng tool này)
    prompt = ChatPromptTemplate.from_messages([
        ("system", PROJECT_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    # Model llama-3.3-70b-versatile sẽ hoạt động rất tốt với danh sách tool này
    agent = prompt | llm.bind_tools(tools)

    return agent, tools