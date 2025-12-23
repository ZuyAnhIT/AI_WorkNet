from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from .api_client import subtask_api_client
from utils.gemini_manager import analytics_engine # Import manager chứa Gemini

# =============================================================================
# SCHEMA ĐỊNH NGHĨA ĐẦU VÀO
# =============================================================================

class FindParentTaskInput(BaseModel):
    company_id: int = Field(..., description="ID công ty")
    workspace_id: int = Field(..., description="ID workspace")
    project_id: int = Field(..., description="ID dự án")
    task_name_query: str = Field(..., description="Tên task cha cần tìm ID")


class CreateSubtaskInput(BaseModel):
    company_id: int = Field(..., description="ID công ty")
    workspace_id: int = Field(..., description="ID workspace")
    project_id: int = Field(..., description="ID dự án")
    task_id: int = Field(..., description="ID task cha đã tìm thấy")
    title: str = Field(..., description="Tiêu đề việc con")
    description: str = Field(..., description="Mô tả việc con")


# =============================================================================
# TOOL 1: TRA CỨU ID TASK CHA
# =============================================================================
@tool("subtask_find_parent_task", args_schema=FindParentTaskInput)
def subtask_find_parent_task(company_id: int, workspace_id: int, project_id: int, task_name_query: str):
    """
    📋 [SUBTASK-LOOKUP] Bước 1: Tra cứu danh sách task để lấy taskId từ tên task.
    """
    print(f"\n🔍 [SUBTASK-LOOKUP] Bắt đầu tìm ID cho task: '{task_name_query}'...")

    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}/tasks"
    result = subtask_api_client.get(endpoint)

    # 1. Xử lý lỗi từ API Client
    if isinstance(result, dict) and "error" in result:
        msg = f"❌ [SUBTASK-LOOKUP-ERROR] Lỗi API: {result['details']}"
        return msg

    # --- LOG DEBUG: Bạn hãy nhìn vào Terminal để xem cấu trúc này ---
    # print(f" DEBUG API RESPONSE: {result}")

    # 2. Chiến thuật bóc tách dữ liệu linh hoạt (Multi-layer extraction)
    raw_tasks = []

    if isinstance(result, list):
        # Trường hợp: API trả về mảng trực tiếp [...]
        raw_tasks = result
    elif isinstance(result, dict):
        data_part = result.get("data", {})
        if isinstance(data_part, list):
            # Trường hợp: {"data": [...]}
            raw_tasks = data_part
        elif isinstance(data_part, dict):
            # Trường hợp phân trang: {"data": {"content": [...]}}
            raw_tasks = data_part.get("content", [])
        else:
            # Trường hợp: {"content": [...]}
            raw_tasks = result.get("content", [])

    # Kiểm tra cuối cùng
    if not isinstance(raw_tasks, list):
        # In ra type để debug
        msg = f"❌ [SUBTASK-LOOKUP-ERROR] Định dạng dữ liệu không hợp lệ. Hệ thống trả về kiểu: {type(result)}"
        print(msg)
        return msg

    query = task_name_query.lower().strip()

    # 3. Lọc danh sách an toàn
    matches = []
    for t in raw_tasks:
        if isinstance(t, dict):
            t_title = str(t.get("title", "")).lower()
            if query in t_title:
                matches.append(t)

    if not matches:
        return f"❌ [SUBTASK-LOOKUP] Không tìm thấy task cha nào khớp với từ khóa '{task_name_query}'."

    # 4. Trả về kết quả
    output = "📋 [SUBTASK-LOOKUP-RESULTS] DANH SÁCH TASK CHA KHỚP YÊU CẦU (CẤM BỊA ID):\n"
    for t in matches:
        t_id = t.get('id', 'N/A')
        t_name = t.get('title', 'Không có tên')
        output += f"- [ID: {t_id}] Tên gốc: '{t_name}'\n"

    print(f"✅ [SUBTASK-LOOKUP] Tìm thấy {len(matches)} kết quả phù hợp.")
    return output
# =============================================================================
# TOOL 2: TẠO SUBTASK
# =============================================================================

@tool("subtask_create_api", args_schema=CreateSubtaskInput)
def subtask_create_api(company_id: int, workspace_id: int, project_id: int, task_id: int, title: str, description: str):
    """
    🚀 [SUBTASK-CREATE] Bước 2: Thực hiện tạo subtask mới sau khi đã có taskId và thông tin.
    """
    print(f"\n🚀 [SUBTASK-CREATE] Đang gửi yêu cầu tạo subtask '{title}' cho TaskID: {task_id}...")

    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}/tasks/{task_id}/subtasks"

    payload = {
        "title": title,
        "description": description,
        "assigneeId": None,
        "estimatedHours": None
    }

    result = subtask_api_client.post(endpoint, payload)

    if isinstance(result, dict) and "error" in result:
        msg = f"❌ [SUBTASK-CREATE-ERROR] Thất bại: {result['details']}"
        print(msg)
        return msg

    # Lấy ID mới tạo từ response
    data = result.get('data', {}) if isinstance(result, dict) else {}
    new_id = data.get('id') or (result.get('id') if isinstance(result, dict) else 'N/A')

    success_msg = f"✅ [SUBTASK-CREATE-SUCCESS] Đã tạo thành công subtask '{title}' (ID mới: {new_id}) vào task cha {task_id}."
    print(success_msg)
    return success_msg


# --- SCHEMA ĐẦU VÀO CHO SUGGESTION ---
class SuggestionInput(BaseModel):
    parent_title: str = Field(..., description="Tiêu đề của task cha")
    parent_description: Optional[str] = Field(None, description="Mô tả chi tiết của task cha (nếu có)")


# --- TOOL 3: GỢI Ý SUBTASK ---
@tool("subtask_generate_suggestions", args_schema=SuggestionInput)
def subtask_generate_suggestions(parent_title: str, parent_description: str = ""):
    """
    💡 [SUBTASK-SUGGEST] Sử dụng trí tuệ nhân tạo để phân tích task cha và đề xuất danh sách các việc con (subtask) thực tế.
    """
    print(f"\n💡 [SUBTASK-SUGGEST] Đang dùng Gemini để phân tích task: '{parent_title}'...")
    system_instruction = """
    Bạn là một Senior Project Manager. Hãy chia nhỏ task được cung cấp thành 3-5 subtask cụ thể.
    Yêu cầu trả về danh sách ngắn gọn, thực tế, chia theo các lớp: Giao diện, Xử lý Logic, và Kiểm thử.
    Định dạng mỗi subtask: [Tên việc con] - [Mô tả ngắn]
    """

    user_content = f"Task cha: {parent_title}\nMô tả: {parent_description if parent_description else 'Không có mô tả'}"

    try:
        response = llm.invoke([
            ("system", system_instruction),
            ("human", user_content)
        ])
        print("✅ [SUBTASK-SUGGEST] Đã tạo xong danh sách gợi ý.")
        return response.content
    except Exception as e:
        return f"❌ Lỗi khi gợi ý: {str(e)}"
# Xuất danh sách tool để Agent sử dụng
subtask_tools_list = [subtask_find_parent_task, subtask_create_api, subtask_generate_suggestions]