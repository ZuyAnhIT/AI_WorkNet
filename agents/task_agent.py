from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm

# --- QUAN TRỌNG: Import đủ các tool (Tạo, Tra cứu, Excel, Batch Text, Xóa an toàn) ---
from mcp_servers.task_service.tools import (
    create_task,                # Tạo 1 task
    get_my_projects_context,    # Tra cứu ID dự án
    create_tasks_from_excel,    # Tạo từ Excel
    create_tasks_batch,         # Tạo từ Text Batch
    list_tasks,                 # Tra cứu danh sách task (xem ID)
    find_tasks_to_delete,       # [MỚI] Tìm kiếm & Xác nhận xóa (Bước 1)
    execute_delete_tasks_batch  # [MỚI] Thực thi xóa hàng loạt (Bước 2)
)
from orchestrator.prompts import TASK_AGENT_SYSTEM_PROMPT


def create_task_agent():
    # Khởi tạo LLM
    llm = get_llm(temperature=0)

    # --- ĐĂNG KÝ DANH SÁCH TOOL ---
    # Agent sẽ được phép sử dụng tất cả các công cụ này
    tools = [
        create_task,                # 1. Tạo 1 task thủ công
        get_my_projects_context,    # 2. Tra cứu ID dự án
        create_tasks_from_excel,    # 3. Đọc file Excel tạo nhiều task
        create_tasks_batch,         # 4. Tạo nhiều task từ danh sách Text/Chat
        list_tasks,                 # 5. Xem danh sách task
        find_tasks_to_delete,       # 6. Tìm task để xóa (Bước 1 quy trình xóa)
        execute_delete_tasks_batch  # 7. Xóa task thật (Bước 2 quy trình xóa)
    ]

    # Thiết lập Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", TASK_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    agent = prompt | llm.bind_tools(tools)

    return agent, tools