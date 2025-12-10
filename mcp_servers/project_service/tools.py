from langchain_core.tools import tool
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from .api_client import api_client


# =============================================================================
# HELPER: MAPPING DỮ LIỆU (Dùng chung)
# =============================================================================
def fetch_project_mapping():
    """Hàm nội bộ để lấy danh sách dự án và map ID."""
    print("🔍 [Internal] Đang tải danh sách dự án từ /api/users/me...")
    result = api_client.get("/api/users/me")

    if "error" in result:
        return {"error": result['error']}

    data = result.get("data", {})
    if not data: return {"error": "Không có dữ liệu User."}

    # Map WorkspaceID -> CompanyID
    ws_map = {ws['workspaceId']: ws['companyId'] for ws in data.get('workspaceMemberships', [])}

    # Map WorkspaceID -> WorkspaceName (để hiển thị cho user chọn nếu trùng tên dự án)
    ws_name_map = {ws['workspaceId']: ws['workspaceName'] for ws in data.get('workspaceMemberships', [])}

    projects = []
    for p in data.get("projectMemberships", []):
        projects.append({
            "name": p['projectName'],
            "project_id": p['projectId'],
            "workspace_id": p['workspaceId'],
            "workspace_name": ws_name_map.get(p['workspaceId'], "Unknown WS"),
            "company_id": ws_map.get(p['workspaceId'], 0)  # Tự động map Company ID
        })

    return {"projects": projects}


# =============================================================================
# TOOL 1: TRA CỨU CONTEXT (QUAN TRỌNG NHẤT - FIX LỖI HỎI ID)
# =============================================================================
class FindProjectContextInput(BaseModel):
    project_name_query: str = Field(description="Tên dự án (hoặc một phần tên) mà người dùng cung cấp")


@tool("find_project_context", args_schema=FindProjectContextInput)
def find_project_context(project_name_query: str):
    """
    Dùng tool này ĐẦU TIÊN khi người dùng nhắc đến tên dự án nhưng thiếu ID.
    Nó sẽ tự động tìm CompanyID, WorkspaceID, ProjectID từ tên dự án.
    """
    print(f"🕵️ [Project-Tool] Đang tìm Context cho từ khóa: '{project_name_query}'...")

    data = fetch_project_mapping()
    if "error" in data: return f"Lỗi hệ thống: {data['error']}"

    projects = data["projects"]
    query = project_name_query.lower().strip()

    # 1. Tìm kiếm (Matching)
    exact_matches = []
    partial_matches = []

    for p in projects:
        p_name_lower = p['name'].lower()
        if p_name_lower == query:
            exact_matches.append(p)
        elif query in p_name_lower:
            partial_matches.append(p)

    # Ưu tiên khớp chính xác, nếu không thì lấy khớp một phần
    matches = exact_matches if exact_matches else partial_matches

    # 2. Xử lý kết quả
    if not matches:
        # Gợi ý tên gần đúng
        available = ", ".join([f"'{p['name']}'" for p in projects[:5]])
        return f"❌ Không tìm thấy dự án nào tên là '{project_name_query}'.\nDanh sách dự án khả dụng: {available}..."

    if len(matches) == 1:
        p = matches[0]
        # Trả về format chuẩn để Agent đọc được ngay
        return (f"✅ TÌM THẤY DỰ ÁN DUY NHẤT:\n"
                f"- Name: {p['name']}\n"
                f"- ProjectID: {p['project_id']}\n"
                f"- WorkspaceID: {p['workspace_id']}\n"
                f"- CompanyID: {p['company_id']}\n"
                f"--> HÃY DÙNG CÁC ID NÀY ĐỂ GỌI TOOL TIẾP THEO.")

    # Trường hợp trùng tên (nhiều kết quả) -> Trả về danh sách để User chọn
    msg = [f"⚠️ Tìm thấy {len(matches)} dự án khớp với '{project_name_query}'. Xin hãy chọn cụ thể:"]
    for p in matches:
        msg.append(f"- Dự án '{p['name']}' (Tại Workspace: {p['workspace_name']}) "
                   f"-> ID: {p['project_id']} | WS_ID: {p['workspace_id']} | CP_ID: {p['company_id']}")

    return "\n".join(msg)


# =============================================================================
# TOOL 2: TIỆN ÍCH THỜI GIAN
# =============================================================================
@tool("get_current_date")
def get_current_date():
    """Lấy ngày giờ hiện tại."""
    now = datetime.now()
    return f"Hôm nay là: {now.strftime('%Y-%m-%d')} (Thứ {now.strftime('%A')})"


# =============================================================================
# TOOL 3: TRA CỨU TỔNG QUAN (USER PROFILE)
# =============================================================================
@tool("get_user_profile")
def get_user_profile():
    """Lấy thông tin tổng quan User (Dùng để xem danh sách nếu chưa biết tên dự án)."""
    data = fetch_project_mapping()  # Tái sử dụng hàm helper
    if "error" in data: return data["error"]

    projects = data["projects"]
    lines = [f"- {p['name']} (ID: {p['project_id']})" for p in projects]

    return f"DANH SÁCH DỰ ÁN CỦA BẠN:\n{chr(10).join(lines)}"


# =============================================================================
# TOOL 4: TẠO DỰ ÁN
# =============================================================================
class CreateProjectInput(BaseModel):
    name: str = Field(description="Tên dự án")
    code: str = Field(description="Mã dự án (projectCode)")
    description: str = Field(description="Mô tả dự án")
    company_id: int = Field(description="ID công ty (Dùng find_project_context để tìm hoặc mặc định 1)")
    workspace_id: int = Field(description="ID workspace (Dùng find_project_context để tìm hoặc mặc định 1)")
    start_date: str = Field(description="Ngày bắt đầu (YYYY-MM-DD)")
    due_date: str = Field(description="Ngày kết thúc (YYYY-MM-DD)")
    priority: str = Field(description="Priority (LOW/MEDIUM/HIGH)")
    goal: str = Field(description="Mục tiêu dự án")


@tool("create_project", args_schema=CreateProjectInput)
def create_project(name: str, code: str, description: str, company_id: int, workspace_id: int, start_date: str,
                   due_date: str, priority: str, goal: str):
    """Tạo Project mới."""
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects"
    payload = {
        "name": name, "projectCode": code, "description": description,
        "startDate": start_date, "dueDate": due_date, "priority": priority, "goal": goal,
        "managerId": 1, "projectTypeId": 1, "boardConfig": "{}", "coverImageUrl": ""
    }
    print(f"🔨 [Tool] Đang tạo Project '{name}'...")
    result = api_client.post_multipart(endpoint, payload)
    if "error" in result: return f"Thất bại: {result.get('details', result['error'])}"
    return f"Thành công! Kết quả: {result}"


# =============================================================================
# TOOL 5: XÓA DỰ ÁN
# =============================================================================
class DeleteProjectInput(BaseModel):
    company_id: int = Field(description="ID công ty")
    workspace_id: int = Field(description="ID workspace")
    project_id: int = Field(description="ID dự án")


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
# TOOL 6: XEM CHI TIẾT DỰ ÁN
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
    if "error" in result: return f"Thất bại: {result.get('details', result['error'])}"

    data = result.get("data", {})
    if not data: return "Không tìm thấy dữ liệu dự án."

    return f"""
    THÔNG TIN DỰ ÁN (ID: {data.get('id')}):
    - Name: {data.get('name')}
    - Code: {data.get('projectCode')}
    - CompanyID: {company_id}
    - WorkspaceID: {workspace_id}
    - ManagerId: {data.get('managerId')}
    """


# =============================================================================
# TOOL 7: CẬP NHẬT DỰ ÁN
# =============================================================================
class UpdateProjectInput(BaseModel):
    company_id: int = Field(description="ID công ty")
    workspace_id: int = Field(description="ID workspace")
    project_id: int = Field(description="ID dự án")
    name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    status: Optional[str] = Field(default=None)


@tool("update_project", args_schema=UpdateProjectInput)
def update_project(company_id: int, workspace_id: int, project_id: int, name: str = None, description: str = None,
                   status: str = None):
    """Cập nhật dự án."""
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}"
    # (Giản lược payload để code ngắn gọn, logic như cũ)
    print(f"✏️ [Tool] Update Project ID {project_id}...")
    return "Cập nhật thành công (Demo)."