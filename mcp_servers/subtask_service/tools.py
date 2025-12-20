from langchain_core.tools import tool
from pydantic import BaseModel, Field
from .api_client import subtask_api_client


class GetProjectTasksInput(BaseModel):
    company_id: int = Field(..., description="ID công ty (lấy từ Context)")
    workspace_id: int = Field(..., description="ID workspace (lấy từ Context)")
    project_id: int = Field(..., description="ID dự án (lấy từ Context)")


@tool("get_project_tasks", args_schema=GetProjectTasksInput)
def get_project_tasks(company_id: int, workspace_id: int, project_id: int):
    """
    📋 [SUBTASK-LOOKUP] Lấy danh sách tất cả các task trong một dự án.
    Dùng tool này để tìm ID của một task khi biết tên của nó.
    """
    print(f"📋 [SUBTASK-TOOL] 🔍 Đang tra cứu danh sách task cho Project ID: {project_id}...")

    # Khai báo endpoint nghiệp vụ ngay tại Tool
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}/tasks"

    # Sử dụng api_client để thực hiện request GET
    result = subtask_api_client.get(endpoint)

    if "error" in result:
        return f"❌ [SUBTASK] Không thể lấy danh sách task: {result.get('details', 'Unknown')}"

    tasks = result if isinstance(result, list) else result.get("data", [])

    if not tasks:
        return "📭 Dự án này hiện chưa có task nào."

    # Format dữ liệu sạch sẽ để AI dễ đọc và lấy ID
    output = "📋 [SUBTASK] DANH SÁCH TASK TRONG DỰ ÁN (DÙNG ID ĐỂ XỬ LÝ TIẾP):\n"
    for t in tasks:
        output += f"- [ID: {t.get('id')}] Tên: '{t.get('title')}' | Trạng thái: {t.get('status')}\n"

    return output


# Danh sách tool hiện tại chỉ có 1 tool lookup
subtask_tools_list = [get_project_tasks]