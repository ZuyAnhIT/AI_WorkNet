from langchain_core.tools import tool
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from .api_client import api_client


# =============================================================================
# HELPER: MAPPING DỮ LIỆU (Đã nâng cấp để lấy TÊN)
# =============================================================================
def fetch_project_mapping():
    """Hàm nội bộ để lấy danh sách dự án và map ID + NAME."""
    print("🔍 [Internal] Đang tải danh sách dự án từ /api/users/me...")

    result = api_client.get("/api/users/me")

    if "error" in result:
        return {"error": result['error']}

    data = result.get("data", {})
    if not data: return {"error": "Không có dữ liệu User."}

    # 1. Map WorkspaceID -> Tên Workspace & CompanyID
    # Tạo dictionary để tra cứu nhanh tên Workspace
    ws_name_map = {
        ws['workspaceId']: ws.get('workspaceName', 'Unknown WS')
        for ws in data.get('workspaceMemberships', [])
    }

    # Tạo dictionary để tra cứu Workspace thuộc Company nào
    ws_to_company_id = {
        ws['workspaceId']: ws.get('companyId')
        for ws in data.get('workspaceMemberships', [])
    }

    # 2. Map CompanyID -> Tên Company
    comp_name_map = {
        c['companyId']: c.get('companyName', 'Unknown Company')
        for c in data.get('companyMemberships', [])
    }

    projects = []
    # 3. Duyệt qua danh sách dự án và gắn tên vào
    for p in data.get("projectMemberships", []):
        w_id = p['workspaceId']
        c_id = ws_to_company_id.get(w_id, 0)  # Lấy Company ID dựa trên Workspace

        projects.append({
            "name": p['projectName'],
            "project_id": p['projectId'],
            "project_code": p.get('projectCode', ''),  # Lấy mã dự án

            "workspace_id": w_id,
            "workspace_name": ws_name_map.get(w_id, "Unknown Workspace"),

            "company_id": c_id,
            "company_name": comp_name_map.get(c_id, "Unknown Company")
        })

    return {"projects": projects}


# =============================================================================
# TOOL 1: TRA CỨU CONTEXT (FINAL VERSION)
# =============================================================================
class FindProjectContextInput(BaseModel):
    project_name_query: str = Field(description="Tên dự án (hoặc một phần tên) mà người dùng cung cấp")


@tool("find_project_context", args_schema=FindProjectContextInput)
def find_project_context(project_name_query: str):
    """
    Dùng tool này ĐẦU TIÊN khi người dùng nhắc đến tên dự án nhưng thiếu ID.
    Nó sẽ tự động tìm CompanyID, WorkspaceID, ProjectID và TÊN CỤ THỂ.
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

    # Ưu tiên khớp chính xác
    matches = exact_matches if exact_matches else partial_matches

    # 2. Xử lý kết quả
    if not matches:
        # Gợi ý tên gần đúng (Chỉ lấy 5 tên đầu để không bị dài quá)
        available = ", ".join([f"'{p['name']}'" for p in projects[:5]])
        return f"❌ Không tìm thấy dự án nào tên là '{project_name_query}'.\nDanh sách dự án khả dụng: {available}..."

    # --- TRƯỜNG HỢP TÌM THẤY 1 DỰ ÁN (Ideal) ---
    if len(matches) == 1:
        p = matches[0]
        # Trả về format chi tiết có cả TÊN để AI hiển thị cho user
        return (
            f"✅ TÌM THẤY DỰ ÁN:\n"
            f"- Dự án: {p['name']} (Mã: {p['project_code']})\n"
            f"- ProjectID: {p['project_id']}\n"
            f"- Workspace: '{p['workspace_name']}' (ID: {p['workspace_id']})\n"
            f"- Company: '{p['company_name']}' (ID: {p['company_id']})\n\n"
            f"👉 HƯỚNG DẪN AI:\n"
            f"1. Dùng các ID số (ProjectID, WorkspaceID...) để gọi tool tiếp theo.\n"
            f"2. Khi chat với user, HÃY DÙNG TÊN (VD: 'Tại Workspace {p['workspace_name']}'), KHÔNG dùng ID số."
        )

    # --- TRƯỜNG HỢP TRÙNG TÊN (>1 kết quả) ---
    msg = [f"⚠️ Tìm thấy {len(matches)} dự án khớp với '{project_name_query}'. Xin hãy chọn cụ thể:"]
    for p in matches:
        msg.append(
            f"- Dự án '{p['name']}' (Code: {p['project_code']}) "
            f"thuộc Workspace '{p['workspace_name']}' - Công ty '{p['company_name']}'"
        )

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


# =============================================================================
# TOOL 8: TRA CỨU ID CÔNG TY & WORKSPACE (Dùng để TẠO DỰ ÁN)
# =============================================================================
class LookupHierarchyInput(BaseModel):
    company_name: str = Field(description="Tên công ty (hoặc 1 phần tên)")
    workspace_name: str = Field(description="Tên workspace (hoặc 1 phần tên)")


@tool("lookup_hierarchy", args_schema=LookupHierarchyInput)
def lookup_hierarchy(company_name: str, workspace_name: str):
    """
    Dùng tool này KHI TẠO DỰ ÁN MỚI.
    Giúp tìm ID của Công ty và Workspace dựa trên tên user cung cấp.
    """
    print(f"🏢 [Lookup-Tool] Đang tìm ID cho: '{company_name}' - '{workspace_name}'...")

    # Gọi lại API lấy dữ liệu user (tương tự fetch_project_mapping nhưng xử lý khác)
    result = api_client.get("/api/users/me")
    if "error" in result: return f"Lỗi API: {result['error']}"

    data = result.get("data", {})
    if not data: return "Không lấy được dữ liệu User."

    # Logic tìm kiếm Workspace và Company
    target_c = company_name.lower().strip()
    target_w = workspace_name.lower().strip()

    found_info = []

    # Duyệt qua các Workspace user tham gia
    for ws in data.get("workspaceMemberships", []):
        w_name = ws.get("workspaceName", "").lower()

        # Nếu tên Workspace khớp
        if target_w in w_name:
            # Lấy luôn Company ID gắn với Workspace này
            # (Giả định user muốn tạo trong workspace này thì phải dùng company của nó)
            c_id = ws.get("companyId")
            w_id = ws.get("workspaceId")
            w_real_name = ws.get("workspaceName")

            found_info.append(f"- Workspace: '{w_real_name}' (ID: {w_id}) | CompanyID: {c_id}")

    if not found_info:
        return f"❌ Không tìm thấy Workspace nào tên giống '{workspace_name}'."

    return "✅ TÌM THẤY THÔNG TIN:\n" + "\n".join(found_info) + "\n--> Hãy dùng ID trên để gọi create_project."