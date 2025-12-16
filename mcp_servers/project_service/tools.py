from langchain_core.tools import tool
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from .api_client import api_client
from enum import Enum
from urllib.parse import urlencode
from typing import Union
import json
import httpx
from utils.request_context import get_user_token

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
# TOOL 4: TẠO DỰ ÁN (MULTIPART/FORM-DATA CHUẨN)
# =============================================================================
class CreateProjectInput(BaseModel):
    # --- 1. CONTEXT ID (TỰ ĐỘNG) ---
    company_id: int = Field(..., description="🛑 SYSTEM_ID: Lấy từ SYSTEM CONTEXT.")
    workspace_id: int = Field(..., description="🛑 SYSTEM_ID: Lấy từ SYSTEM CONTEXT.")

    # --- 2. USER INPUT (7 TRƯỜNG BẮT BUỘC) ---
    name: str = Field(None, description="Tên dự án")
    code: str = Field(None, description="Mã dự án")
    description: str = Field(None, description="Mô tả")
    goal: str = Field(None, description="Mục tiêu")
    start_date: str = Field(None, description="Ngày bắt đầu (YYYY-MM-DD)")
    due_date: str = Field(None, description="Ngày kết thúc (YYYY-MM-DD)")
    priority: str = Field(None, description="Độ ưu tiên")


@tool("create_project", args_schema=CreateProjectInput)
def create_project(
        company_id: int,
        workspace_id: int,
        name: str = None,
        code: str = None,
        description: str = None,
        goal: str = None,
        start_date: str = None,
        due_date: str = None,
        priority: str = None
):
    """
    Tạo Project bằng Multipart/Form-data.
    """
    # 1. KIỂM TRA ĐỦ 7 TRƯỜNG
    missing = []
    if not name: missing.append("Tên dự án")
    if not code: missing.append("Mã dự án")
    if not description: missing.append("Mô tả")
    if not goal: missing.append("Mục tiêu")
    if not start_date: missing.append("Ngày bắt đầu")
    if not due_date: missing.append("Ngày kết thúc")
    if not priority: missing.append("Độ ưu tiên")

    if missing:
        return f"❌ Thiếu thông tin: {', '.join(missing)}. Vui lòng hỏi user."

    # 2. XỬ LÝ ID & DATA FORMAT
    if not company_id: company_id = 1
    if not workspace_id: workspace_id = 1

    code = code.upper().strip()
    priority = priority.upper().strip()

    # 3. TẠO DICT DỮ LIỆU (Giống hệt cấu trúc JSON bạn yêu cầu)
    project_dto = {
        "name": name,
        "projectCode": code,
        "description": description,
        "goal": goal,
        "startDate": start_date,
        "dueDate": due_date,
        "priority": priority,

        # Các trường mặc định (Backend yêu cầu)
        "managerId": None,  # Gửi null
        "boardConfig": {},  # Gửi empty object
        "coverImageUrl": "null",  # Gửi string "null"
        "projectTypeId": None  # Gửi null
    }

    # Chuyển Dict thành JSON String để nhét vào Multipart
    json_payload = json.dumps(project_dto, ensure_ascii=False)

    print(f"🔨 [Tool] Đang gửi Multipart: {name} ({code})")

    # 4. GỬI REQUEST (QUAN TRỌNG NHẤT)
    base_url = "http://localhost:8082"
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects"
    full_url = f"{base_url}{endpoint}"

    try:
        token = get_user_token()

        # Header: KHÔNG ĐƯỢC set Content-Type (httpx tự sinh boundary)
        headers = {
            "Authorization": f"Bearer {token}"
        }

        # Cấu trúc Multipart:
        # key: 'data' (tên part mà Backend @RequestPart("data") hứng)
        # value: (filename, content, content_type)
        files = {
            'data': (None, json_payload, 'application/json')
        }

        with httpx.Client(timeout=30.0) as client:
            # Dùng tham số `files=` để gửi multipart/form-data
            response = client.post(full_url, files=files, headers=headers)

            print(f"🔍 [DEBUG STATUS]: {response.status_code}")

            if response.status_code >= 400:
                return f"❌ Backend từ chối ({response.status_code}): {response.text}"

            result = response.json()

    except Exception as e:
        print(f"❌ [TOOL ERROR]: {str(e)}")
        return f"❌ Lỗi hệ thống: {str(e)}"

    data = result.get('data', {})
    new_id = data.get('id', 'N/A')

    return f"✅ Thành công! Dự án '{name}' đã được tạo (ID: {new_id})."
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
# TOOL 6: XEM CHI TIẾT DỰ ÁN (SILENT CONTEXT)
# =============================================================================
class GetProjectDetailsInput(BaseModel):
    # 👇 CỐ ĐỊNH ID TỪ CONTEXT
    company_id: int = Field(..., description="🛑 SYSTEM_ID: Lấy từ SYSTEM CONTEXT.")
    workspace_id: int = Field(..., description="🛑 SYSTEM_ID: Lấy từ SYSTEM CONTEXT.")

    # 👇 ID DỰ ÁN (User cung cấp hoặc lấy từ Context)
    project_id: int = Field(..., description="ID dự án cần xem.")


@tool("get_project_details", args_schema=GetProjectDetailsInput)
def get_project_details(company_id: int, workspace_id: int, project_id: int):
    """Xem thông tin chi tiết dự án trước khi sửa hoặc xóa."""

    # Logic phòng thủ
    if not company_id: company_id = 1
    if not workspace_id: workspace_id = 1

    base_url = "http://localhost:8082"
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}"

    print(f"🔍 [Tool] Đang xem chi tiết Project ID {project_id}...")

    try:
        # Lấy token
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}"}

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{base_url}{endpoint}", headers=headers)

            if response.status_code == 404:
                return "❌ Không tìm thấy dự án. Vui lòng kiểm tra lại Project ID."
            if response.status_code != 200:
                return f"❌ Lỗi: {response.text}"

            data = response.json().get("data", {})

    except Exception as e:
        return f"❌ Lỗi hệ thống: {str(e)}"

    if not data: return "⚠️ Không tìm thấy dữ liệu dự án."

    # Format kết quả trả về cho AI đọc để hiển thị lại cho user
    return f"""
    --- THÔNG TIN DỰ ÁN (ID: {data.get('id')}) ---
    - Tên dự án: {data.get('name')}
    - Mã dự án: {data.get('projectCode')}
    - Mô tả: {data.get('description')}
    - Mục tiêu: {data.get('goal')}
    - Thời gian: {data.get('startDate')} đến {data.get('dueDate')}
    - Độ ưu tiên: {data.get('priority')}
    - Trạng thái: {data.get('status')}
    - Người quản lý (ID): {data.get('managerId')}
    ---------------------------------------------
    """


# =============================================================================
# TOOL 7: CẬP NHẬT DỰ ÁN (FULL SCHEMA - FIX NULL ERROR)
# =============================================================================

class UpdateProjectInput(BaseModel):
    # --- 1. CONTEXT ID (SILENT - BẮT BUỘC) ---
    company_id: int = Field(..., description="🛑 SYSTEM_ID: Lấy từ SYSTEM CONTEXT.")
    workspace_id: int = Field(..., description="🛑 SYSTEM_ID: Lấy từ SYSTEM CONTEXT.")
    project_id: int = Field(..., description="ID của dự án cần sửa.")

    # --- 2. FIELDS CẦN SỬA (OPTIONAL - CHO PHÉP NULL) ---
    # Thay vì 'str', ta dùng 'Optional[str]' để chấp nhận giá trị None từ AI
    name: Optional[str] = Field(None, description="Tên mới (Nếu có)")
    project_code: Optional[str] = Field(None, description="Mã dự án mới (In hoa, không dấu)")
    description: Optional[str] = Field(None, description="Mô tả mới")
    goal: Optional[str] = Field(None, description="Mục tiêu mới")
    priority: Optional[str] = Field(None, description="Priority mới (LOW, MEDIUM, HIGH)")

    start_date: Optional[str] = Field(None, description="Ngày bắt đầu (YYYY-MM-DD)")
    due_date: Optional[str] = Field(None, description="Ngày kết thúc (YYYY-MM-DD)")
    completed_at: Optional[str] = Field(None, description="Ngày hoàn thành thực tế (Để đóng dự án)")

    status: Optional[str] = Field(None, description="Trạng thái (NEW, ACTIVE, COMPLETED...)")
    manager_id: Optional[int] = Field(None, description="ID người quản lý mới (Integer)")

    cover_image_url: Optional[str] = Field(None, description="Link ảnh bìa")
    board_config: Optional[str] = Field(None, description="Cấu hình Board")
    project_type_id: Optional[int] = Field(None, description="ID loại dự án")


@tool("update_project", args_schema=UpdateProjectInput)
def update_project(
        company_id: int, workspace_id: int, project_id: int,
        name: Optional[str] = None,
        project_code: Optional[str] = None,
        description: Optional[str] = None,
        goal: Optional[str] = None,
        priority: Optional[str] = None,
        start_date: Optional[str] = None,
        due_date: Optional[str] = None,
        completed_at: Optional[str] = None,
        status: Optional[str] = None,
        manager_id: Optional[int] = None,
        cover_image_url: Optional[str] = None,
        board_config: Optional[str] = None,
        project_type_id: Optional[int] = None
):
    """
    Cập nhật dự án. Tự động lấy dữ liệu cũ và merge với dữ liệu mới.
    """
    # 1. SETUP URL
    if not company_id: company_id = 1
    if not workspace_id: workspace_id = 1

    base_url = "http://localhost:8082"
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}"
    full_url = f"{base_url}{endpoint}"

    print(f"✏️ [Tool] Đang xử lý Update Project ID {project_id}...")

    try:
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}"}

        # 2. BƯỚC QUAN TRỌNG: LẤY DỮ LIỆU CŨ (GET)
        with httpx.Client(timeout=10.0) as client:
            get_resp = client.get(full_url, headers=headers)

            if get_resp.status_code == 404:
                return f"❌ Không tìm thấy dự án có ID {project_id}."
            if get_resp.status_code != 200:
                return f"❌ Lỗi khi lấy thông tin cũ: {get_resp.text}"

            # Data cũ từ Backend
            old_data = get_resp.json().get('data', {})

        # 3. BƯỚC MERGE: TRỘN CŨ VÀ MỚI
        # Logic: Nếu tham số mới có giá trị (không None) -> Lấy mới. Nếu None -> Giữ cũ.
        merged_data = {
            "name": name if name is not None else old_data.get("name"),
            "projectCode": project_code if project_code is not None else old_data.get("projectCode"),
            "description": description if description is not None else old_data.get("description"),
            "goal": goal if goal is not None else old_data.get("goal"),
            "priority": priority if priority is not None else old_data.get("priority"),
            "startDate": start_date if start_date is not None else old_data.get("startDate"),
            "dueDate": due_date if due_date is not None else old_data.get("dueDate"),
            "completedAt": completed_at if completed_at is not None else old_data.get("completedAt"),
            "status": status if status is not None else old_data.get("status"),
            "managerId": manager_id if manager_id is not None else old_data.get("managerId"),

            # Các trường phụ
            "boardConfig": board_config if board_config is not None else old_data.get("boardConfig"),
            "coverImageUrl": cover_image_url if cover_image_url is not None else old_data.get("coverImageUrl"),
            "projectTypeId": project_type_id if project_type_id is not None else old_data.get("projectTypeId")
        }

        # Chuẩn hóa Priority (Backend thường cần uppercase)
        if merged_data["priority"]:
            merged_data["priority"] = merged_data["priority"].upper()

        # 4. BƯỚC GỬI: PUT MULTIPART
        multipart_payload = {
            'data': (None, json.dumps(merged_data, ensure_ascii=False), 'application/json')
        }

        with httpx.Client(timeout=30.0) as client:
            # Dùng PUT
            put_resp = client.put(full_url, files=multipart_payload, headers=headers)

            print(f"🔍 [DEBUG STATUS]: {put_resp.status_code}")

            if put_resp.status_code >= 400:
                return f"❌ Backend từ chối cập nhật ({put_resp.status_code}): {put_resp.text}"

            result = put_resp.json()

    except Exception as e:
        print(f"❌ [TOOL ERROR]: {str(e)}")
        return f"❌ Lỗi hệ thống: {str(e)}"

    # 5. TRẢ KẾT QUẢ
    changed_fields = []
    if name: changed_fields.append("Tên")
    if project_code: changed_fields.append("Mã")
    if priority: changed_fields.append("Độ ưu tiên")
    if goal: changed_fields.append("Mục tiêu")

    msg_changed = ", ".join(changed_fields) if changed_fields else "thông tin chi tiết"
    return f"✅ Cập nhật thành công {msg_changed} cho dự án ID {project_id}."

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
# TOOL 9: LẤY DANH SÁCH DỰ ÁN (ĐÃ CẬP NHẬT TÌM KIẾM KEYWORD)
# =============================================================================

from urllib.parse import urlencode


# 1. Định nghĩa Enum trạng thái (Giữ nguyên)
class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# 2. Định nghĩa Input Schema (ĐÃ THÊM KEYWORD)
class GetWorkspaceProjectsInput(BaseModel):
    company_id: int = Field(description="🛑 SYSTEM_ID: Lấy từ SYSTEM CONTEXT.")
    workspace_id: int = Field(description="🛑 SYSTEM_ID: Lấy từ SYSTEM CONTEXT.")

    # 👇 [THÊM MỚI] Để AI điền tên dự án cần tìm vào đây
    keyword: Optional[str] = Field(default=None,
                                   description="Tên dự án hoặc từ khóa cần tìm kiếm (Ví dụ: 'Chatbot', 'ERP').")

    status: Optional[ProjectStatus] = Field(default=None, description="Lọc trạng thái: NEW, IN_PROGRESS...")
    limit: int = Field(default=10, description="Số lượng dự án muốn lấy")


# 3. Hàm xử lý chính
@tool("get_workspace_projects", args_schema=GetWorkspaceProjectsInput)
def get_workspace_projects(
        company_id: int,
        workspace_id: int,
        keyword: Optional[str] = None,  # 👇 [THÊM MỚI] Tham số hàm
        status: Optional[ProjectStatus] = None,
        limit: int = 10
):
    """
    Tìm kiếm dự án trong Workspace.
    Có thể lọc theo tên (keyword) hoặc trạng thái (status).
    """
    print(f"📂 [Project-Tool] Tìm kiếm tại Workspace {workspace_id} | Keyword: '{keyword}' | Status: {status}...")

    # Endpoint gốc
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects"

    # Tạo dict tham số cơ bản
    params = {
        "page": 0,
        "size": limit,
        "sortBy": "createdAt",
        "sortDir": "desc"
    }

    # 👇 [LOGIC MỚI] Map tham số keyword của Tool vào tham số tìm kiếm của API
    # Lưu ý: Kiểm tra Backend của bạn dùng ?search= hay ?keyword= hay ?name=
    # Ở đây mình giả định Backend dùng ?search=
    if keyword:
        params["search"] = keyword

        # Nếu có status thì thêm vào
    if status:
        params["status"] = status.value

    # Nối chuỗi query param
    query_string = urlencode(params)
    full_url = f"{endpoint}?{query_string}"

    # Gọi API
    result = api_client.get(full_url)

    # Xử lý lỗi
    if "error" in result:
        return f"❌ Lỗi API: {result['error']}"

    data = result.get("data", {})
    projects_list = data.get("content", [])

    if not projects_list:
        if keyword:
            return f"📭 Không tìm thấy dự án nào có tên chứa '{keyword}'."
        return "📭 Không tìm thấy dự án nào trong Workspace này."

    # Format kết quả
    output_lines = [f"✅ Tìm thấy {len(projects_list)} dự án:"]

    for p in projects_list:
        p_id = p.get("id")
        name = p.get("name")
        code = p.get("projectCode")
        stt = p.get("status")
        # Thêm hiển thị Manager ID để AI biết đường map khi cần update
        manager_id = p.get("managerId", "N/A")

        line = f"- [ID: {p_id}] {name} (Mã: {code}) | Status: {stt} | ManagerID: {manager_id}"
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