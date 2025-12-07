from langchain_core.tools import tool
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from .api_client import api_client


# =============================================================================
# TOOL 1: TIỆN ÍCH THỜI GIAN (GIỮ NGUYÊN)
# =============================================================================
@tool("get_current_date")
def get_current_date():
    """Lấy ngày giờ hiện tại."""
    now = datetime.now()
    return f"Hôm nay là: {now.strftime('%Y-%m-%d')} (Thứ {now.strftime('%A')})"


# =============================================================================
# TOOL 2: TRA CỨU THÔNG TIN (GIỮ NGUYÊN)
# =============================================================================
@tool("get_user_profile")
def get_user_profile():
    """Lấy thông tin User, danh sách Công ty, Workspace VÀ DỰ ÁN."""
    print("🔍 [Tool] Đang lấy User Profile & Project List...")
    result = api_client.get("/api/users/me")

    if "error" in result: return f"Lỗi: {result['error']}"
    data = result.get("data", {})
    if not data: return "Không tìm thấy dữ liệu."

    ws_map = {ws['workspaceId']: ws['companyId'] for ws in data.get('workspaceMemberships', [])}

    companies = []
    for comp in data.get("companyMemberships", []):
        companies.append(f"COMPANY: '{comp['companyName']}' => ID: {comp['companyId']}")

    workspaces = []
    for ws in data.get("workspaceMemberships", []):
        workspaces.append(
            f"WORKSPACE: '{ws['workspaceName']}' => ID: {ws['workspaceId']} (CompanyID: {ws['companyId']})")

    projects = []
    for p in data.get("projectMemberships", []):
        p_name = p['projectName']
        p_id = p['projectId']
        w_id = p['workspaceId']
        c_id = ws_map.get(w_id, 0)
        projects.append(f"PROJECT: '{p_name}' => ProjectID: {p_id}, WorkspaceID: {w_id}, CompanyID: {c_id}")

    return f"""
    ### BẢNG TRA CỨU ID (LOOKUP TABLE)

    [DANH SÁCH CÔNG TY]
    {chr(10).join(companies) if companies else "Không có."}

    [DANH SÁCH WORKSPACE]
    {chr(10).join(workspaces) if workspaces else "Không có."}

    [DANH SÁCH DỰ ÁN HIỆN CÓ]
    {chr(10).join(projects) if projects else "Không có."}
    """


# =============================================================================
# TOOL 3: TẠO DỰ ÁN (GIỮ NGUYÊN)
# =============================================================================
class CreateProjectInput(BaseModel):
    name: str = Field(description="Tên dự án")
    code: str = Field(description="Mã dự án (projectCode)")
    description: str = Field(description="Mô tả dự án")
    company_id: int = Field(description="ID công ty (AI tự tra cứu)")
    workspace_id: int = Field(description="ID workspace (AI tự tra cứu)")
    start_date: str = Field(description="Ngày bắt đầu (YYYY-MM-DD)")
    due_date: str = Field(description="Ngày kết thúc (YYYY-MM-DD)")
    priority: str = Field(description="Priority (LOW/MEDIUM/HIGH)")
    goal: str = Field(description="Mục tiêu dự án")


@tool("create_project", args_schema=CreateProjectInput)
def create_project(name: str, code: str, description: str, company_id: int, workspace_id: int, start_date: str,
                   due_date: str, priority: str, goal: str):
    """Tạo Project mới (Cần xác nhận)."""
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects"
    payload = {
        "name": name, "projectCode": code, "description": description,
        "startDate": start_date, "dueDate": due_date, "priority": priority, "goal": goal,
        "managerId": 0, "projectTypeId": 0, "boardConfig": {}, "coverImageUrl": ""
    }
    print(f"🔨 [Tool] Đang tạo Project '{name}'...")
    result = api_client.post_multipart(endpoint, payload)
    if "error" in result: return f"Thất bại: {result.get('details', result['error'])}"
    return f"Thành công! Kết quả: {result}"


# =============================================================================
# TOOL 4: XÓA DỰ ÁN (GIỮ NGUYÊN)
# =============================================================================
class DeleteProjectInput(BaseModel):
    company_id: int = Field(description="ID công ty chứa dự án")
    workspace_id: int = Field(description="ID workspace chứa dự án")
    project_id: int = Field(description="ID dự án cần xóa")


@tool("delete_project", args_schema=DeleteProjectInput)
def delete_project(company_id: int, workspace_id: int, project_id: int):
    """Xóa một dự án."""
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}"
    print(f"🔥 [Tool] Đang XÓA Project ID {project_id}...")
    result = api_client.delete(endpoint)

    if "error" in result:
        return f"Thất bại: {result.get('details', result['error'])}"

    return f"Thành công! Dự án ID {project_id} đã bị xóa vĩnh viễn."


# =============================================================================
# TOOL 5: XEM CHI TIẾT DỰ ÁN (GIỮ NGUYÊN)
# =============================================================================
class GetProjectDetailsInput(BaseModel):
    company_id: int = Field(description="ID công ty")
    workspace_id: int = Field(description="ID workspace")
    project_id: int = Field(description="ID dự án")


@tool("get_project_details", args_schema=GetProjectDetailsInput)
def get_project_details(company_id: int, workspace_id: int, project_id: int):
    """Xem thông tin chi tiết dự án."""
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}"
    print(f"🔍 [Tool] Đang xem chi tiết Project ID {project_id}...")

    result = api_client.get(endpoint)

    if "error" in result:
        return f"Thất bại: {result.get('details', result['error'])}"

    data = result.get("data", {})
    if not data: return "Không tìm thấy dữ liệu dự án."

    return f"""
    DATA HIỆN TẠI (Dùng để merge khi update):
    - Name: {data.get('name')}
    - Code: {data.get('projectCode')}
    - Description: {data.get('description')}
    - Goal: {data.get('goal')}
    - Priority: {data.get('priority')}
    - StartDate: {data.get('startDate')}
    - DueDate: {data.get('dueDate')}
    - CompletedAt: {data.get('completedAt')}
    - ManagerId: {data.get('managerId')}
    - Status: {data.get('status')}
    """


# =============================================================================
# TOOL 6: CẬP NHẬT DỰ ÁN (MỚI THÊM)
# =============================================================================
class UpdateProjectInput(BaseModel):
    company_id: int = Field(description="ID công ty")
    workspace_id: int = Field(description="ID workspace")
    project_id: int = Field(description="ID dự án")

    # Các trường thông tin (Optional)
    name: Optional[str] = Field(description="Tên dự án mới", default=None)
    code: Optional[str] = Field(description="Mã dự án mới", default=None)
    description: Optional[str] = Field(description="Mô tả mới", default=None)
    start_date: Optional[str] = Field(description="Ngày bắt đầu mới (YYYY-MM-DD)", default=None)
    due_date: Optional[str] = Field(description="Hạn chót mới (YYYY-MM-DD)", default=None)
    priority: Optional[str] = Field(description="Priority mới (LOW/MEDIUM/HIGH)", default=None)
    goal: Optional[str] = Field(description="Mục tiêu mới", default=None)

    # Các trường kỹ thuật (Optional)
    manager_id: Optional[int] = Field(description="ID quản lý", default=0)
    completed_at: Optional[str] = Field(description="Ngày hoàn thành", default=None)


@tool("update_project", args_schema=UpdateProjectInput)
def update_project(
        company_id: int, workspace_id: int, project_id: int,
        name: str = None, code: str = None, description: str = None,
        start_date: str = None, due_date: str = None, priority: str = None,
        goal: str = None, manager_id: int = 0, completed_at: str = None
):
    """
    Cập nhật thông tin dự án.
    Lưu ý: Agent PHẢI truyền đầy đủ tất cả các trường (lấy từ get_project_details).
    """
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}"

    payload = {
        "name": name,
        "projectCode": code,
        "description": description,
        "startDate": start_date,
        "dueDate": due_date,
        "completedAt": completed_at,
        "priority": priority,
        "goal": goal,
        "managerId": manager_id,
        "projectTypeId": 0,
        "boardConfig": "string",
        "coverImageUrl": "string"
    }

    print(f"✏️ [Tool] Đang UPDATE Project ID {project_id}...")

    # Gọi hàm PUT mới
    result = api_client.put_multipart(endpoint, payload)

    if "error" in result:
        return f"Thất bại: {result.get('details', result['error'])}"

    return f"Thành công! Dự án đã được cập nhật. Kết quả: {result}"