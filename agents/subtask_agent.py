from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm
from orchestrator.prompts.subtask import SUBTASK_AGENT_SYSTEM_PROMPT

# --- CHỈ IMPORT TOOL TỪ SUBTASK SERVICE ---
# Vì Context (ID) đã được api.py cung cấp sẵn trong System Message
from mcp_servers.subtask_service.tools import (
    subtask_find_parent_task,  # Dùng để tìm taskId từ tên task cha
    subtask_create_api         # Dùng để thực thi tạo subtask
)

def create_subtask_agent():
    """
    Khởi tạo Subtask Agent.
    Agent này hoạt động dựa trên Context ID (company, workspace, project)
    được truyền từ api.py và chỉ sử dụng các tool nghiệp vụ subtask.
    """
    # Khởi tạo LLM với Temperature=0 để đảm bảo trích xuất dữ liệu từ Context chính xác
    llm = get_llm(temperature=0, role="subtask_agent")

    # 3. DANH SÁCH TOOL (Chỉ bao gồm các tool nghiệp vụ Subtask)
    tools = [
        subtask_find_parent_task, # Bước 1: Tìm ID task cha
        subtask_create_api         # Bước 2: Tạo subtask
    ]

    # Thiết lập Prompt
    # SUBTASK_AGENT_SYSTEM_PROMPT trong orchestrator nên được viết để nhắc AI
    # luôn kiểm tra thông tin ID trong tin nhắn hệ thống trước khi hỏi User.
    prompt = ChatPromptTemplate.from_messages([
        ("system", SUBTASK_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    # Gắn tool vào Agent
    # AI sẽ tự động lấy các ID từ SystemMessage (do api.py gửi) để điền vào tool
    agent = prompt | llm.bind_tools(tools)

    return agent, tools