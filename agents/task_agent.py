# agents/task_agent.py

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm
from orchestrator.prompts.task import TASK_AGENT_SYSTEM_PROMPT

# 1. IMPORT TOOL TỪ TASK SERVICE (File tools.py bạn vừa gửi)
from mcp_servers.task_service.tools import (
    create_task,  # Tạo 1 task
    get_my_projects_context,  # Lấy ngữ cảnh nhanh
    create_tasks_from_excel,  # Tạo từ Excel
    create_tasks_batch,  # Tạo từ Text
    list_tasks,  # Xem danh sách
    find_tasks_to_delete,  # Tìm task để xóa
    execute_delete_tasks_batch,  # Xóa task
    recommend_assignee,  # Gợi ý người làm
    get_project_members,  # Lấy thành viên
    get_project_forecast,  # Dự báo
    get_daily_standup  # Họp nhanh
)

# 2. IMPORT TOOL TỪ PROJECT SERVICE (BẮT BUỘC ĐỂ ĐIỀU HƯỚNG)
from mcp_servers.project_service.tools import (
    get_user_profile,  # Lấy CompanyID
    get_company_workspaces,  # Lấy WorkspaceID
    get_workspace_projects,  # <--- QUAN TRỌNG: Dùng để lấy danh sách dự án -> Tự tìm ID
    get_project_details  # Check chi tiết
)


def create_task_agent():
    # Khởi tạo LLM (Temperature=0 để đảm bảo tính chính xác)
    llm = get_llm(temperature=0)

    # 3. ĐĂNG KÝ DANH SÁCH TOOL (WHITELIST)
    tools = [
        # --- NHÓM 1: ĐIỀU HƯỚNG & TÌM KIẾM (Project Tools) ---
        get_user_profile,
        get_company_workspaces,
        get_workspace_projects,  # AI dùng tool này để lấy list dự án, sau đó tự lọc ra ID
        get_project_details,
        get_my_projects_context,

        # --- NHÓM 2: TẠO & QUẢN LÝ TASK (Task Tools) ---
        create_task,
        list_tasks,

        # --- NHÓM 3: BATCH & EXCEL ---
        create_tasks_from_excel,
        create_tasks_batch,

        # --- NHÓM 4: XÓA TASK ---
        find_tasks_to_delete,
        execute_delete_tasks_batch,

        # --- NHÓM 5: THÔNG MINH (ANALYTICS) ---
        recommend_assignee,
        get_project_members,
        get_project_forecast,
        get_daily_standup
    ]

    # Thiết lập Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", TASK_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    agent = prompt | llm.bind_tools(tools)

    return agent, tools