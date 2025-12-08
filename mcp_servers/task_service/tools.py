import pandas as pd
import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, List
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

# --- TOOL 1: XỬ LÝ EXCEL (CÓ PREVIEW & SELECT) ---
class ExcelInput(BaseModel):
    file_path: str = Field(description="Đường dẫn file Excel")
    target_project_name: str = Field(description="Tên dự án đích")
    # --- THAM SỐ MỚI ---
    preview: bool = Field(description="True: Chỉ xem trước danh sách task (không tạo). False: Thực hiện tạo.",
                          default=True)
    selected_indices: Optional[List[int]] = Field(
        description="Danh sách số thứ tự (STT) các dòng muốn tạo (Ví dụ: [1, 3, 5]). Để trống = Chọn tất cả.",
        default=None)


@tool("create_tasks_from_excel", args_schema=ExcelInput)
def create_tasks_from_excel(file_path: str, target_project_name: str, preview: bool = True,
                            selected_indices: List[int] = None):
    """
    Xử lý file Excel.
    - Bước 1: Gọi với preview=True để lấy danh sách task ra cho user xem.
    - Bước 2: Gọi với preview=False (kèm selected_indices nếu user chọn) để tạo thật.
    """
    clean_path = file_path.strip().strip('"').strip("'")
    print(f"📂 [Batch-Tool] Đọc file: {clean_path} | Preview: {preview} | Selected: {selected_indices}")

    if not os.path.exists(clean_path):
        return f"Lỗi: Không tìm thấy file tại {clean_path}"

    # 1. Tra cứu ID dự án
    project_map = get_project_mapping()
    if not project_map: return "Lỗi: Không lấy được danh sách dự án (Token lỗi)."

    target_ids = project_map.get(target_project_name.lower().strip())
    if not target_ids:
        avail = ", ".join(list(project_map.keys())[:3])
        return f"❌ Lỗi: Không tìm thấy dự án '{target_project_name}'. (Có sẵn: {avail}...)"

    try:
        df = pd.read_excel(clean_path)
        df.columns = df.columns.str.strip()
    except Exception as e:
        return f"Lỗi đọc file: {str(e)}"

    # 2. Xử lý logic lọc dòng (nếu user chọn)
    if selected_indices:
        # User nhập số thứ tự 1, 2, 3 -> Pandas index là 0, 1, 2
        # Giữ lại các dòng có index nằm trong danh sách user chọn (trừ 1)
        pandas_indices = [i - 1 for i in selected_indices if 0 <= i - 1 < len(df)]
        if not pandas_indices:
            return "Lỗi: Các số thứ tự bạn chọn không hợp lệ hoặc nằm ngoài danh sách."
        df = df.iloc[pandas_indices]

    tasks_info = []  # Dùng để in ra màn hình
    results = []  # Dùng để báo cáo kết quả tạo
    success_count = 0

    # 3. Duyệt danh sách
    for index, row in df.iterrows():
        # Lấy STT gốc (để hiển thị cho user dễ đối chiếu)
        original_stt = index + 1  # Index trong Excel bắt đầu từ 1 (nếu tính cả header thì là dòng 2)

        title = str(row.get('Title', 'No Title')).strip()
        if not title or title == 'nan': continue

        # Lấy thông tin task
        desc = str(row.get('Description', ''))
        priority = str(row.get('Priority', 'LOW')).upper()
        if priority == 'NAN': priority = 'LOW'
        due_date = convert_date_to_iso(row.get('DueDate'))

        task_preview = f"📌 **Task {original_stt}:** {title} | Pri: {priority} | Due: {row.get('DueDate')}"
        tasks_info.append(task_preview)

        # --- CHẾ ĐỘ TẠO THẬT (PREVIEW = FALSE) ---
        if not preview:
            endpoint = f"/api/companies/{target_ids['company_id']}/workspaces/{target_ids['workspace_id']}/projects/{target_ids['project_id']}/tasks"

            def get_id(col):
                val = row.get(col)
                return int(val) if pd.notna(val) else None

            payload = {
                "title": title,
                "description": desc,
                "taskType": str(row.get('TaskType', 'STORY')),
                "priority": priority,
                "dueDate": due_date,
                "storyPoints": int(row.get('StoryPoints', 0)) if pd.notna(row.get('StoryPoints')) else 0,
                "sprintId": get_id('SprintId'),
                "epicId": get_id('EpicId'),
                "assigneeId": get_id('AssigneeId')
            }

            res = api_client.post(endpoint, payload)
            if "error" in res:
                results.append(f"❌ Task {original_stt}: Lỗi - {res.get('details')}")
            else:
                success_count += 1
                results.append(f"✅ Task {original_stt}: Thành công")

    # --- TRẢ VỀ KẾT QUẢ ---
    if preview:
        # Trả về danh sách để AI hiện cho user chọn
        return f"""
        ### 📋 DANH SÁCH TASK TÌM THẤY TRONG FILE
        (Dự án đích: {target_project_name})

        {chr(10).join(tasks_info)}

        > Hãy hỏi người dùng xem họ muốn tạo những task nào? (Tất cả hay chỉ một số dòng cụ thể?)
        """
    else:
        # Báo cáo kết quả tạo thật
        return f"""
        ### 📊 KẾT QUẢ IMPORT ({success_count} Task thành công)
        {chr(10).join(results)}
        """


# --- CÁC TOOL KHÁC (GIỮ NGUYÊN) ---
@tool("get_my_projects_context")
def get_my_projects_context():
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


# --- TOOL BATCH TEXT (GIỮ NGUYÊN) ---
class TaskItem(BaseModel):
    title: str
    description: str = ""
    priority: str = "LOW"
    due_date: str = None
    story_points: int = 0
    task_type: str = "STORY"


class BatchCreateTaskInput(BaseModel):
    target_project_name: str
    tasks: List[TaskItem]


@tool("create_tasks_batch", args_schema=BatchCreateTaskInput)
def create_tasks_batch(target_project_name: str, tasks: List[TaskItem]):
    print(f"📦 [Batch-Text] Tạo {len(tasks)} task vào dự án '{target_project_name}'")
    project_map = get_project_mapping()
    if not project_map: return "Lỗi: Không lấy được danh sách dự án."
    ids = project_map.get(target_project_name.lower().strip())
    if not ids: return f"❌ Lỗi: Không tìm thấy dự án '{target_project_name}'."
    endpoint = f"/api/companies/{ids['company_id']}/workspaces/{ids['workspace_id']}/projects/{ids['project_id']}/tasks"
    results = []
    success_count = 0
    for item in tasks:
        final_due_date = convert_date_to_iso(item.due_date)
        priority = item.priority.upper() if item.priority else "LOW"
        payload = {
            "title": item.title, "description": item.description, "taskType": item.task_type,
            "priority": priority, "dueDate": final_due_date, "storyPoints": item.story_points,
            "sprintId": None, "epicId": None, "assigneeId": None
        }
        res = api_client.post(endpoint, payload)
        if "error" in res:
            results.append(f"❌ '{item.title}': Lỗi")
        else:
            success_count += 1
            results.append(f"✅ '{item.title}': OK")
    return f"### KẾT QUẢ BATCH:\nThành công: {success_count}/{len(tasks)}\n{chr(10).join(results)}"