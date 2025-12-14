from langchain_core.tools import tool
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from .api_client import api_client
from enum import Enum
from urllib.parse import urlencode
from typing import Union
# =============================================================================
# HELPER: MAPPING DỮ LIỆU (Định nghĩa hàm này để Tool gọi được)
# =============================================================================
def fetch_project_mapping():
    """Hàm nội bộ để lấy danh sách dự án và bóc tách dữ liệu từ API /me"""
    print("🔍 [Internal] Đang bóc tách dữ liệu từ /api/users/me...")

    # Giả sử bạn đang dùng api_client đã cấu hình sẵn
    # Nếu chưa có, bạn cần import api_client từ utils của bạn
    result = api_client.get("/api/users/me")

    if "error" in result:
        return {"error": result['error']}

    data = result.get("data", {})
    if not data:
        return {"error": "Không tìm thấy dữ liệu hồ sơ."}

    return data
# =============================================================================
# TOOL: TRA CỨU THÔNG TIN USER & CÔNG TY (Bóc tách từ /api/users/me)
# =============================================================================
@tool("get_user_profile")
def get_user_profile():
    """
    Lấy danh sách Công ty và Workspace THẬT của người dùng.
    BẮT BUỘC gọi tool này trước khi yêu cầu người dùng chọn nơi tạo dự án.
    """
    print("🔍 [Internal] Đang bóc tách dữ liệu từ /api/users/me...")

    # Gọi API thực tế
    result = api_client.get("/api/users/me")

    if "error" in result:
        return f"⚠️ HỆ THỐNG: Lỗi kết nối API: {result['error']}"

    data = result.get("data", {})
    if not data:
        return "⚠️ HỆ THỐNG: Không tìm thấy dữ liệu hồ sơ người dùng."

    # 1. Bóc tách danh sách Công ty (companyMemberships)
    companies = data.get("companyMemberships", [])

    if not companies:
        return "⚠️ HỆ THỐNG: Tài khoản của bạn hiện không thuộc bất kỳ công ty nào."

    # 2. Xây dựng văn bản phản hồi (Plain Text) để chống ảo giác 100%
    # AI sẽ đọc văn bản này và hiển thị chính xác tên công ty có trong danh sách
    output = "DANH SÁCH DỮ LIỆU THỰC TẾ TỪ HỆ THỐNG (CẤM BỊA ĐẶT):\n"

    for idx, comp in enumerate(companies, 1):
        c_name = comp.get("companyName", "Unknown Company")
        c_id = comp.get("companyId")
        role = comp.get("roleCode", "N/A")

        # Format rõ ràng để AI lấy được cả Tên và ID
        output += f"{idx}. CÔNG TY: {c_name} | ID: {c_id} | VAI TRÒ: {role}\n"

    return output

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

    # Payload chuẩn chuẩn bị gửi đi
    payload = {
        "name": name,
        "projectCode": code,
        "description": description,
        "startDate": start_date,
        "dueDate": due_date,
        "priority": priority,
        "goal": goal,
        "managerId": 1,
        "projectTypeId": 1,
        "boardConfig": "{}",
        "coverImageUrl": ""
    }

    print(f"🔨 [Tool] Đang gửi yêu cầu tạo Project: {name} (Code: {code})")

    # THAY THẾ post_multipart BẰNG post (Gửi dạng JSON application/json)
    # Vì multipart thường gây lỗi encoding với tiếng Việt trên một số Backend
    result = api_client.post(endpoint, payload)

    if "error" in result:
        return f"❌ Thất bại: {result.get('details', result['error'])}"

    return f"✅ Thành công! Dự án '{name}' đã được khởi tạo trên hệ thống."

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

# =============================================================================
# TOOL 9: LẤY DANH SÁCH DỰ ÁN TRONG WORKSPACE (API MỚI)
# =============================================================================

# 1. Định nghĩa Enum trạng thái để AI chọn chính xác
class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# 2. Định nghĩa Input Schema
class GetWorkspaceProjectsInput(BaseModel):
    company_id: int = Field(description="ID của công ty (Lấy từ tool get_user_profile)")
    workspace_id: int = Field(description="ID của workspace (Lấy từ tool get_user_profile)")
    status: Optional[ProjectStatus] = Field(default=None,
                                            description="Lọc trạng thái: NEW, IN_PROGRESS, COMPLETED... (Để trống nếu lấy tất cả)")
    limit: int = Field(default=10, description="Số lượng dự án muốn lấy (Mặc định 10)")


# 3. Hàm xử lý chính
@tool("get_workspace_projects", args_schema=GetWorkspaceProjectsInput)
def get_workspace_projects(
        company_id: int,
        workspace_id: int,
        status: Optional[ProjectStatus] = None,
        limit: int = 10
):
    """
    Dùng tool này để XEM DANH SÁCH DỰ ÁN.
    Gọi API lấy danh sách dự án đầy đủ trong một Workspace cụ thể.
    """
    print(f"📂 [Project-Tool] Đang lấy list dự án tại Workspace {workspace_id} (Status: {status})...")

    # Endpoint gốc
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects"

    # Tạo dict tham số
    params = {
        "page": 0,
        "size": limit,
        "sortBy": "createdAt",
        "sortDir": "desc"
    }

    # Nếu có status thì thêm vào dict
    if status:
        params["status"] = status.value

    # --- [SỬA LỖI TẠI ĐÂY] ---
    # Thay vì truyền params=params, ta nối chuỗi thủ công:
    query_string = urlencode(params)
    full_url = f"{endpoint}?{query_string}"

    # Gọi API với full_url (api_client.get chỉ nhận 1 tham số url)
    result = api_client.get(full_url)

    # Xử lý lỗi trả về từ wrapper api_client
    if "error" in result:
        return f"❌ Lỗi API: {result['error']}"

    # Lấy dữ liệu từ response JSON chuẩn
    # Cấu trúc: { success: true, data: { content: [...] } }
    data = result.get("data", {})
    projects_list = data.get("content", [])

    if not projects_list:
        return "📭 Không tìm thấy dự án nào trong Workspace này."

    # Format kết quả trả về dạng Text để AI dễ đọc
    output_lines = [f"✅ Tìm thấy {len(projects_list)} dự án:"]

    for p in projects_list:
        p_id = p.get("id")
        name = p.get("name")
        code = p.get("projectCode")
        stt = p.get("status")
        progress = p.get("progress", 0)
        manager = p.get("managerName", "N/A")

        # Dòng format: "- [ID: 123] Tên Dự Án (Code) | Status | Progress | Manager"
        line = f"- [ID: {p_id}] {name} ({code}) | Trạng thái: {stt} | Tiến độ: {progress}% | QL: {manager}"
        output_lines.append(line)

    return "\n".join(output_lines)

# =============================================================================
# TOOL 10: LẤY DANH SÁCH WORKSPACE (Nâng cấp Auto-Mapping)
# =============================================================================

class GetWorkspacesInput(BaseModel):
    # Cho phép nhận cả Số (ID) hoặc Chữ (Tên công ty)
    company_id: Union[int, str] = Field(
        description="ID số của công ty hoặc Tên công ty (Ví dụ: 1 hoặc 'TechVision')"
    )


@tool("get_company_workspaces", args_schema=GetWorkspacesInput)
def get_company_workspaces(company_id: Union[int, str]):
    """
    Lấy danh sách Workspace của một công ty.
    Chấp nhận đầu vào là ID số hoặc Tên công ty để tự động ánh xạ.
    """

    # 1. Logic Mapping Tên -> ID (Để xử lý khi user gõ chữ thay vì chọn số)
    # Bạn có thể mở rộng danh sách này hoặc gọi fetch_project_mapping để lấy list động
    final_id = company_id
    if isinstance(company_id, str):
        name_input = company_id.lower().strip()
        if "techvision" in name_input or name_input == "1":
            final_id = 1
        elif "innovatech" in name_input or name_input == "2":
            final_id = 2
        else:
            # Nếu user nhập tên lạ, trả về hướng dẫn thay vì để AI tự bịa
            return f"❌ Không tìm thấy ID cho công ty '{company_id}'. Vui lòng chọn đúng tên trong danh sách hoặc nhập số thứ tự."

    print(f"🏢 [Project-Tool] Mapping '{company_id}' -> ID: {final_id}. Đang lấy Workspaces...")

    # 2. Gọi API với ID đã được chuẩn hóa
    endpoint = f"/api/companies/{final_id}/workspaces"
    params = {
        "page": 0,
        "size": 50,
        "sortBy": "createdAt",
        "sortDir": "desc"
    }

    query_string = urlencode(params)
    full_url = f"{endpoint}?{query_string}"

    result = api_client.get(full_url)

    if "error" in result:
        return f"❌ Lỗi API: {result['error']}"

    data = result.get("data", {})
    workspaces = data.get("content", [])

    if not workspaces:
        return f"📭 Công ty (ID: {final_id}) hiện chưa có Workspace nào."

    # 3. Trả về kết quả sạch cho AI hiển thị
    output = f"✅ Đã tìm thấy {len(workspaces)} Workspace cho công ty này:\n"
    for ws in workspaces:
        output += f"- {ws.get('workspaceName')} | ID Workspace: {ws.get('workspaceId')}\n"

    output += "\n👉 AI hãy yêu cầu người dùng chọn tên Workspace hoặc nhập ID tương ứng."
    return output