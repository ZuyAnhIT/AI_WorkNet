import pandas as pd
import os  # <--- QUAN TRỌNG: Thêm thư viện này
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from .api_client import api_client


# =============================================================================
# 1. CÁC HÀM PHỤ TRỢ
# =============================================================================

def get_project_mapping():
    """Lấy danh sách dự án để tra cứu ID."""
    print("🔍 [Internal] Đang gọi API lấy danh sách dự án...")
    result = api_client.get("/api/users/me")
    if "error" in result:
        print(f"❌ [Internal] Lỗi API: {result['error']}")
        return {}

    data = result.get("data", {})
    if not data: return {}

    ws_map = {ws['workspaceId']: ws['companyId'] for ws in data.get('workspaceMemberships', [])}

    mapping = {}
    for p in data.get('projectMemberships', []):
        p_name = p['projectName'].lower().strip()
        mapping[p_name] = {
            "project_id": p['projectId'],
            "workspace_id": p['workspaceId'],
            "company_id": ws_map.get(p['workspaceId'], 0)
        }
    return mapping


def convert_date_to_iso(date_str):
    """Chuyển đổi ngày tháng về ISO 8601."""
    if not date_str or str(date_str).lower() == 'nan': return None
    if isinstance(date_str, datetime):
        return date_str.strftime("%Y-%m-%dT17:00:00.000Z")
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"]:
        try:
            return datetime.strptime(str(date_str), fmt).strftime("%Y-%m-%dT17:00:00.000Z")
        except:
            continue
    return str(date_str)


# =============================================================================
# 2. CÁC TOOL CHÍNH
# =============================================================================

# --- TOOL 1: XỬ LÝ EXCEL (FIX LỖI ĐƯỜNG DẪN WINDOWS) ---
class ExcelInput(BaseModel):
    file_path: str = Field(description="Đường dẫn file Excel")
    target_project_name: str = Field(description="Tên dự án đích")


@tool("create_tasks_from_excel", args_schema=ExcelInput)
def create_tasks_from_excel(file_path: str, target_project_name: str):
    """
    Đọc file Excel và tạo hàng loạt Task vào một dự án cụ thể.
    """
    # --- BƯỚC 1: VỆ SINH ĐƯỜNG DẪN (FIX BUG QUAN TRỌNG) ---
    # Loại bỏ dấu ngoặc kép thừa và khoảng trắng nếu AI lỡ thêm vào
    clean_path = file_path.strip().strip('"').strip("'")

    print(f"📂 [Batch-Tool] Raw Path: {file_path}")
    print(f"📂 [Batch-Tool] Clean Path: {clean_path}")

    # Kiểm tra file có thực sự tồn tại không
    if not os.path.exists(clean_path):
        return f"Lỗi: Hệ thống không tìm thấy file tại đường dẫn: {clean_path}. Hãy kiểm tra lại quyền truy cập hoặc đường dẫn."

    print(f"🎯 [Batch-Tool] Dự án đích: '{target_project_name}'")

    # --- BƯỚC 2: TRA CỨU ID DỰ ÁN ---
    project_map = get_project_mapping()
    if not project_map:
        return "Lỗi: Không lấy được danh sách dự án (Token lỗi)."

    target_key = target_project_name.lower().strip()
    target_ids = project_map.get(target_key)

    if not target_ids:
        avail = ", ".join(list(project_map.keys())[:5])
        return f"❌ Lỗi: Không tìm thấy dự án tên là '{target_project_name}'. (Có sẵn: {avail}...)"

    # --- BƯỚC 3: ĐỌC EXCEL ---
    try:
        df = pd.read_excel(clean_path)  # Dùng đường dẫn sạch
        df.columns = df.columns.str.strip()
    except Exception as e:
        return f"Lỗi khi đọc nội dung Excel (thiếu thư viện openpyxl?): {str(e)}"

    results = []
    success_count = 0

    # --- BƯỚC 4: TẠO TASK ---
    for index, row in df.iterrows():
        title = str(row.get('Title', 'No Title')).strip()
        if not title or title == 'nan': continue

        endpoint = f"/api/companies/{target_ids['company_id']}/workspaces/{target_ids['workspace_id']}/projects/{target_ids['project_id']}/tasks"

        priority = str(row.get('Priority', 'LOW')).upper()
        if priority == 'NAN': priority = 'LOW'

        def get_id_val(col_name):
            val = row.get(col_name)
            return int(val) if pd.notna(val) else None

        payload = {
            "title": title,
            "description": str(row.get('Description', '')),
            "taskType": str(row.get('TaskType', 'STORY')),
            "priority": priority,
            "dueDate": convert_date_to_iso(row.get('DueDate')),
            "storyPoints": int(row.get('StoryPoints', 0)) if pd.notna(row.get('StoryPoints')) else 0,
            "sprintId": get_id_val('SprintId'),
            "epicId": get_id_val('EpicId'),
            "assigneeId": get_id_val('AssigneeId')
        }

        res = api_client.post(endpoint, payload)

        if "error" in res:
            results.append(f"❌ Task '{title}': Lỗi - {res.get('details')}")
        else:
            success_count += 1
            results.append(f"✅ Task '{title}': Thành công")

    return f"""
    ### 📊 KẾT QUẢ IMPORT VÀO DỰ ÁN: {target_project_name}
    - Tổng số task: {len(df)}
    - Thành công: {success_count}

    {chr(10).join(results)}
    """


# --- CÁC TOOL KHÁC (Giữ nguyên) ---
@tool("get_my_projects_context")
def get_my_projects_context():
    """Tra cứu danh sách Dự án."""
    pmap = get_project_mapping()
    lines = [f"PROJECT: '{k}' => ID: {v['project_id']}" for k, v in pmap.items()]
    return "\n".join(lines) if lines else "Không có dự án."


class CreateTaskInput(BaseModel):
    title: str = Field(description="Tiêu đề")
    description: str = Field(description="Mô tả")
    company_id: int = Field(description="ID Công ty")
    workspace_id: int = Field(description="ID Workspace")
    project_id: int = Field(description="ID Dự án")
    due_date: str = Field(description="Hạn chót")
    priority: str = Field(description="Priority", default="LOW")
    assignee_id: Optional[int] = Field(default=None)
    sprint_id: Optional[int] = Field(default=None)
    epic_id: Optional[int] = Field(default=None)


@tool("create_task", args_schema=CreateTaskInput)
def create_task(title: str, description: str, company_id: int, workspace_id: int, project_id: int, due_date: str,
                priority: str = "LOW", assignee_id: int = None, sprint_id: int = None, epic_id: int = None):
    """Tạo 1 Task lẻ."""
    final_due_date = convert_date_to_iso(due_date)
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}/tasks"
    payload = {
        "title": title, "description": description, "taskType": "STORY",
        "priority": priority, "storyPoints": 0, "dueDate": final_due_date,
        "sprintId": sprint_id, "epicId": epic_id, "assigneeId": assignee_id
    }
    print(f"🔨 [Task-Tool] Tạo Task '{title}'...")
    result = api_client.post(endpoint, payload)
    if "error" in result: return f"Thất bại: {result.get('details', result['error'])}"
    return f"Thành công! Kết quả: {result}"