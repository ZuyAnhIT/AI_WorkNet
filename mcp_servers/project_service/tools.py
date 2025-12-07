from langchain_core.tools import tool
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from .api_client import api_client


# --- TOOL 1: GET CURRENT DATE (MỚI) ---
@tool("get_current_date")
def get_current_date():
    """
    Lấy ngày giờ hiện tại của hệ thống.
    Luôn gọi tool này đầu tiên nếu người dùng nhắc đến thời gian tương đối như:
    "hôm nay", "ngày mai", "tuần sau", "thứ 2 tới"... để tính toán ngày chính xác.
    """
    now = datetime.now()
    # Trả về kèm thứ trong tuần để AI dễ tính (VD: Monday)
    return f"Hôm nay là: {now.strftime('%Y-%m-%d')} (Thứ {now.strftime('%A')})"


# --- TOOL 2: CREATE PROJECT ---
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


# --- TOOL 3: GET USER PROFILE (LOOKUP TABLE) ---
@tool("get_user_profile")
def get_user_profile():
    """Tra cứu danh sách Công ty và Workspace để lấy ID."""
    print("🔍 [Tool] Đang tra cứu Profile...")
    result = api_client.get("/api/users/me")

    if "error" in result: return f"Lỗi: {result['error']}"
    data = result.get("data", {})
    if not data: return "Không tìm thấy dữ liệu."

    companies = []
    for comp in data.get("companyMemberships", []):
        companies.append(f"NAME: '{comp['companyName']}' => ID: {comp['companyId']}")

    workspaces = []
    for ws in data.get("workspaceMemberships", []):
        workspaces.append(
            f"NAME: '{ws['workspaceName']}' => ID: {ws['workspaceId']} (Thuộc Company ID: {ws['companyId']})")

    return f"""
    BẢNG TRA CỨU ID (DÀNH RIÊNG CHO AI - KHÔNG ĐƯỢC IN ID RA CHO USER):

    [COMPANIES]
    {chr(10).join(companies) if companies else "Không có."}

    [WORKSPACES]
    {chr(10).join(workspaces) if workspaces else "Không có."}
    """