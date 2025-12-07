from langchain_core.tools import tool
from pydantic import BaseModel, Field
from datetime import datetime
from .api_client import api_client


# =============================================================================
# TOOL 1: TIỆN ÍCH THỜI GIAN
# =============================================================================
@tool("get_current_date")
def get_current_date():
    """
    Lấy ngày giờ hiện tại.
    Dùng để tính toán khi user nói: "hôm nay", "ngày mai", "tuần sau"...
    """
    now = datetime.now()
    return f"Hôm nay là: {now.strftime('%Y-%m-%d')} (Thứ {now.strftime('%A')})"


# =============================================================================
# TOOL 2: TRA CỨU THÔNG TIN (USER, COMPANY, WORKSPACE, PROJECT)
# =============================================================================
@tool("get_user_profile")
def get_user_profile():
    """
    Lấy thông tin User, danh sách Công ty, Workspace VÀ DỰ ÁN.
    QUAN TRỌNG: Dùng tool này để tra cứu ID trước khi thực hiện Tạo hoặc Xóa dự án.
    """
    print("🔍 [Tool] Đang lấy User Profile & Project List...")
    result = api_client.get("/api/users/me")

    if "error" in result: return f"Lỗi: {result['error']}"
    data = result.get("data", {})
    if not data: return "Không tìm thấy dữ liệu."

    # 1. Tạo Map: WorkspaceID -> CompanyID (để dễ tra cứu ngược)
    ws_map = {ws['workspaceId']: ws['companyId'] for ws in data.get('workspaceMemberships', [])}

    # 2. Danh sách Công ty
    companies = []
    for comp in data.get("companyMemberships", []):
        companies.append(f"COMPANY: '{comp['companyName']}' => ID: {comp['companyId']}")

    # 3. Danh sách Workspace
    workspaces = []
    for ws in data.get("workspaceMemberships", []):
        workspaces.append(
            f"WORKSPACE: '{ws['workspaceName']}' => ID: {ws['workspaceId']} (CompanyID: {ws['companyId']})")

    # 4. Danh sách Dự án (Cần thiết để xóa dự án)
    projects = []
    for p in data.get("projectMemberships", []):
        p_name = p['projectName']
        p_id = p['projectId']
        w_id = p['workspaceId']
        c_id = ws_map.get(w_id, 0)  # Lấy CompanyID từ map
        projects.append(f"PROJECT: '{p_name}' => ProjectID: {p_id}, WorkspaceID: {w_id}, CompanyID: {c_id}")

    return f"""
    ### BẢNG TRA CỨU ID (LOOKUP TABLE)
    (Chỉ dùng cho AI xử lý, không hiển thị ID thô cho người dùng)

    [DANH SÁCH CÔNG TY]
    {chr(10).join(companies) if companies else "Không có."}

    [DANH SÁCH WORKSPACE]
    {chr(10).join(workspaces) if workspaces else "Không có."}

    [DANH SÁCH DỰ ÁN HIỆN CÓ]
    {chr(10).join(projects) if projects else "Không có."}
    """


# =============================================================================
# TOOL 3: TẠO DỰ ÁN
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
    """
    Tạo Project mới. CHỈ ĐƯỢC GỌI SAU KHI NGƯỜI DÙNG ĐÃ XÁC NHẬN "ĐỒNG Ý".
    """
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects"

    payload = {
        "name": name, "projectCode": code, "description": description,
        "startDate": start_date, "dueDate": due_date, "priority": priority, "goal": goal,
        "managerId": 0, "projectTypeId": 0, "boardConfig": {}, "coverImageUrl": ""
    }

    print(f"🔨 [Tool] Đang tạo Project '{name}'...")
    result = api_client.post_multipart(endpoint, payload)

    if "error" in result:
        return f"Thất bại: {result.get('details', result['error'])}"
    return f"Thành công! Kết quả: {result}"


# =============================================================================
# TOOL 4: XÓA DỰ ÁN (MỚI THÊM)
# =============================================================================
class DeleteProjectInput(BaseModel):
    company_id: int = Field(description="ID công ty chứa dự án")
    workspace_id: int = Field(description="ID workspace chứa dự án")
    project_id: int = Field(description="ID dự án cần xóa")


@tool("delete_project", args_schema=DeleteProjectInput)
def delete_project(company_id: int, workspace_id: int, project_id: int):
    """
    Xóa một dự án.
    CẢNH BÁO: Phải tra cứu ID chính xác bằng 'get_user_profile' và XÁC NHẬN với user trước khi gọi.
    """
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}"

    print(f"🔥 [Tool] Đang XÓA Project ID {project_id}...")

    result = api_client.delete(endpoint)

    if "error" in result:
        return f"Thất bại: {result.get('details', result['error'])}"

    return f"Thành công! Dự án ID {project_id} đã bị xóa vĩnh viễn."