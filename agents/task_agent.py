from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm

# 1. Import các tool của Task Service
from mcp_servers.task_service.tools import (
    create_task,  # Tạo 1 task
    get_my_projects_context,  # Tra cứu ngữ cảnh (Cũ)
    create_tasks_from_excel,  # Tạo từ Excel
    create_tasks_batch,  # Tạo từ Text Batch
    list_tasks,  # Xem danh sách task
    find_tasks_to_delete,  # Xóa an toàn B1: Tìm kiếm
    execute_delete_tasks_batch,  # Xóa an toàn B2: Xóa thật
    recommend_assignee  # [MỚI] Gợi ý người thực hiện (Smart Assign)
)

# 2. Import tool tra cứu ID từ Project Service (Để Task Agent tự tìm ID dự án)
from mcp_servers.project_service.tools import find_project_context

from orchestrator.prompts import TASK_AGENT_SYSTEM_PROMPT


def create_task_agent():
    # Khởi tạo LLM
    llm = get_llm(temperature=0)

    # --- ĐĂNG KÝ DANH SÁCH TOOL ---
    # Agent sẽ được phép sử dụng tất cả các công cụ này
    tools = [
        # --- Nhóm Tạo ---
        create_task,
        create_tasks_from_excel,
        create_tasks_batch,

        # --- Nhóm Tra Cứu ---
        get_my_projects_context,
        list_tasks,
        find_project_context,  # <--- Quan trọng: Giúp Task Agent tự tìm ID dự án

        # --- Nhóm Xóa ---
        find_tasks_to_delete,
        execute_delete_tasks_batch,

        # --- Nhóm Thông Minh ---
        recommend_assignee  # <--- Tool mới vừa thêm
    ]

    # Thiết lập Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", TASK_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    agent = prompt | llm.bind_tools(tools)

    return agent, tools