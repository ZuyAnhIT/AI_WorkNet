import pandas as pd
import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, List
from typing import Optional
from langchain.tools import tool
from pydantic import BaseModel, Field
from .api_client import api_client
from datetime import datetime


# =============================================================================
# 1. CÁC HÀM PHỤ TRỢ (INTERNAL HELPERS)
# =============================================================================

# --- HÀM PHỤ TRỢ ---
def convert_date_to_iso(date_str):
    """Chuyển đổi ngày tháng user nhập về ISO 8601."""
    if not date_str or str(date_str).lower() == 'nan': return None
    # Thử các định dạng ngày phổ biến ở VN
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"]:
        try:
            # Lưu ý: Thêm giờ cố định 17:00 (Cuối ngày làm việc) để tránh bị trôi sang ngày hôm trước do múi giờ
            return datetime.strptime(str(date_str), fmt).strftime("%Y-%m-%dT17:00:00.000Z")
        except:
            continue
    return str(date_str)

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
# 2. CÁC TOOL CHÍNH (MCP TOOLS)
# =============================================================================

# --- TOOL 1: TRA CỨU CONTEXT DỰ ÁN ---
@tool("get_my_projects_context")
def get_my_projects_context():
    """Tra cứu danh sách Dự án của tôi."""
    pmap = get_project_mapping()
    lines = [f"PROJECT: '{k}' => ID: {v['project_id']}" for k, v in pmap.items()]
    return "\n".join(lines) if lines else "Không có dự án."



# --- TOOL TẠO TASK (ĐÃ CẬP NHẬT) ---
def convert_date_to_iso(date_str):
    if not date_str or str(date_str).lower() == 'nan': return None
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"]:
        try:
            return datetime.strptime(str(date_str), fmt).strftime("%Y-%m-%dT17:00:00.000Z")
        except:
            continue
    return str(date_str)


# --- CẬP NHẬT TOOL CREATE TASK ---
class CreateTaskInput(BaseModel):
    title: str = Field(description="Tiêu đề task")
    description: str = Field(description="Mô tả chi tiết")
    company_id: int = Field(description="ID Công ty")
    workspace_id: int = Field(description="ID Workspace")
    project_id: int = Field(description="ID Dự án")

    # Optional fields
    due_date: Optional[str] = Field(default=None, description="Hạn chót (dd/mm/yyyy)")
    priority: str = Field(default="LOW", description="LOW, MEDIUM, HIGH")
    assignee_id: Optional[int] = Field(default=None)
    sprint_id: Optional[int] = Field(default=None)
    epic_id: Optional[int] = Field(default=None)
    story_points: Optional[int] = Field(default=None)


@tool("create_task", args_schema=CreateTaskInput)
def create_task(
        title: str, description: str,
        company_id: int, workspace_id: int, project_id: int,
        due_date: str = None, priority: str = "LOW",
        assignee_id: int = None, sprint_id: int = None, epic_id: int = None, story_points: int = None
):
    """Tạo task mới."""
    final_due_date = convert_date_to_iso(due_date)
    final_priority = priority.upper() if priority else "LOW"

    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}/tasks"

    payload = {
        "title": title, "description": description, "taskType": "STORY",
        "priority": final_priority, "dueDate": final_due_date,
        "storyPoints": story_points, "sprintId": sprint_id, "epicId": epic_id, "assigneeId": assignee_id
    }

    print(f"🔨 [Task-Tool] Tạo Task '{title}' -> Project {project_id}...")

    result = api_client.post(endpoint, payload)

    # --- BẮT LỖI CỤ THỂ TỪ BACKEND ---
    if "error" in result:
        err_msg = str(result.get('message') or result.get('details') or result.get('error'))

        # Lỗi chưa cấu hình Board (Nguyên nhân gây 404 và Timeout)
        if "no status board configuration" in err_msg.lower():
            return (
                f"⛔ LỖI NGHIỆP VỤ: Dự án (ID {project_id}) chưa được cấu hình Bảng trạng thái (Kanban Board).\n"
                f"👉 Vui lòng vào Web để tạo Board/Column cho dự án này trước khi thêm Task."
            )

        return f"❌ Thất bại: {err_msg}"

    data = result.get("data", {})
    return f"✅ Tạo thành công! Task ID: {data.get('id')} | Title: {data.get('title')}"
# --- TOOL 3: XỬ LÝ EXCEL (BATCH FILE) ---
class ExcelInput(BaseModel):
    file_path: str = Field(description="Đường dẫn file Excel")
    target_project_name: str = Field(description="Tên dự án đích (Lấy từ lời nói của user)")


@tool("create_tasks_from_excel", args_schema=ExcelInput)
def create_tasks_from_excel(file_path: str, target_project_name: str):
    """Đọc file Excel và tạo hàng loạt Task vào dự án đích."""
    clean_path = file_path.strip().strip('"').strip("'")
    print(f"📂 [Batch-Tool] Đọc file: {clean_path} -> Dự án: {target_project_name}")

    if not os.path.exists(clean_path):
        return f"Lỗi: Không tìm thấy file tại {clean_path}"

    project_map = get_project_mapping()
    if not project_map: return "Lỗi: Không lấy được danh sách dự án."

    target_ids = project_map.get(target_project_name.lower().strip())
    if not target_ids:
        avail = ", ".join(list(project_map.keys())[:5])
        return f"❌ Lỗi: Không tìm thấy dự án '{target_project_name}'. (Có sẵn: {avail}...)"

    try:
        df = pd.read_excel(clean_path)
        df.columns = df.columns.str.strip()
    except Exception as e:
        return f"Lỗi đọc file: {str(e)}"

    results = []
    success_count = 0

    for index, row in df.iterrows():
        title = str(row.get('Title', 'No Title')).strip()
        if not title or title == 'nan': continue

        endpoint = f"/api/companies/{target_ids['company_id']}/workspaces/{target_ids['workspace_id']}/projects/{target_ids['project_id']}/tasks"
        priority = str(row.get('Priority', 'LOW')).upper()
        if priority == 'NAN': priority = 'LOW'

        def get_id(col):
            val = row.get(col)
            return int(val) if pd.notna(val) else None

        payload = {
            "title": title,
            "description": str(row.get('Description', '')),
            "taskType": str(row.get('TaskType', 'STORY')),
            "priority": priority,
            "dueDate": convert_date_to_iso(row.get('DueDate')),
            "storyPoints": int(row.get('StoryPoints', 0)) if pd.notna(row.get('StoryPoints')) else 0,
            "sprintId": get_id('SprintId'),
            "epicId": get_id('EpicId'),
            "assigneeId": get_id('AssigneeId')
        }

        res = api_client.post(endpoint, payload)
        if "error" in res:
            results.append(f"❌ '{title}': Lỗi - {res.get('details')}")
        else:
            success_count += 1
            results.append(f"✅ '{title}': OK")

    return f"### KẾT QUẢ IMPORT:\nThành công: {success_count}/{len(df)}\n{chr(10).join(results)}"


# --- TOOL 4: TẠO TASK TỪ TEXT (BATCH TEXT JSON) ---
class TaskItem(BaseModel):
    title: str = Field(description="Tiêu đề task")
    description: str = Field(description="Mô tả", default="")
    priority: str = Field(description="Priority", default="LOW")
    due_date: str = Field(description="Hạn chót", default=None)
    story_points: int = Field(description="Story Points", default=0)
    task_type: str = Field(description="STORY/TASK", default="STORY")


class BatchCreateTaskInput(BaseModel):
    target_project_name: str = Field(description="Tên dự án đích")
    tasks: List[TaskItem] = Field(description="Danh sách các task cần tạo")


@tool("create_tasks_batch", args_schema=BatchCreateTaskInput)
def create_tasks_batch(target_project_name: str, tasks: List[TaskItem]):
    """
    Tạo NHIỀU task cùng lúc từ danh sách Text/Json (Tiết kiệm quota).
    """
    print(f"📦 [Batch-Text] Tạo {len(tasks)} task -> {target_project_name}")
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


# --- TOOL 5: LIST TASKS (TRA CỨU ĐỂ XÓA) - MỚI THÊM ---
class ListTasksInput(BaseModel):
    project_id: int = Field(description="ID Dự án")
    workspace_id: int = Field(description="ID Workspace")
    company_id: int = Field(description="ID Công ty")


@tool("list_tasks", args_schema=ListTasksInput)
def list_tasks(company_id: int, workspace_id: int, project_id: int):
    """Liệt kê danh sách task trong dự án để tìm ID (dùng trước khi xóa)."""
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}/tasks"
    print(f"🔍 [Task-Tool] Lấy danh sách task của Project {project_id}...")

    result = api_client.get(endpoint)
    if "error" in result: return f"Lỗi: {result.get('details', result['error'])}"

    data = result.get("data", [])
    if not data: return "Dự án này chưa có task nào."

    lines = []
    for t in data:
        lines.append(f"- Task: '{t['title']}' | ID: {t['id']} | Status: {t['status']}")
    return f"DANH SÁCH TASK:\n{chr(10).join(lines)}"


# --- TOOL 6: DELETE TASK - MỚI THÊM ---
class DeleteTaskInput(BaseModel):
    task_id: int = Field(description="ID Task")
    project_id: int = Field(description="ID Dự án")
    workspace_id: int = Field(description="ID Workspace")
    company_id: int = Field(description="ID Công ty")


@tool("delete_task", args_schema=DeleteTaskInput)
def delete_task(company_id: int, workspace_id: int, project_id: int, task_id: int):
    """Xóa một task."""
    endpoint = f"/api/companies/{company_id}/workspaces/{workspace_id}/projects/{project_id}/tasks/{task_id}"
    print(f"🔥 [Task-Tool] Đang XÓA Task ID {task_id}...")

    result = api_client.delete(endpoint)

    if "error" in result:
        return f"Thất bại: {result.get('details', result['error'])}"

    return f"Thành công! Task ID {task_id} đã xóa."


# =============================================================================
# 7. QUY TRÌNH XOÁ TASK AN TOÀN (TÌM KIẾM -> XÁC NHẬN -> XOÁ)
# =============================================================================

class FindTasksToDeleteInput(BaseModel):
    target_project_name: str = Field(description="Tên dự án chứa task")
    task_keywords: List[str] = Field(description="Danh sách tên hoặc từ khóa của các task muốn xóa")


@tool("find_tasks_to_delete", args_schema=FindTasksToDeleteInput)
def find_tasks_to_delete(target_project_name: str, task_keywords: List[str]):
    """
    BƯỚC 1: Tìm ID các task dựa trên tên người dùng cung cấp.
    Dùng tool này để hiển thị danh sách cho người dùng XÁC NHẬN trước khi xóa.
    """
    print(f"🔍 [Delete-Flow] Tìm task '{task_keywords}' trong dự án '{target_project_name}'...")

    # 1. Lấy thông tin dự án
    project_map = get_project_mapping()
    if not project_map: return "Lỗi: Không lấy được danh sách dự án."

    ids = project_map.get(target_project_name.lower().strip())
    if not ids: return f"❌ Lỗi: Không tìm thấy dự án '{target_project_name}'."

    # 2. Lấy toàn bộ task trong dự án đó
    endpoint = f"/api/companies/{ids['company_id']}/workspaces/{ids['workspace_id']}/projects/{ids['project_id']}/tasks"
    result = api_client.get(endpoint)

    if isinstance(result, dict) and "error" in result:
        return f"Lỗi API: {result.get('details', result['error'])}"

    # 3. Xử lý dữ liệu trả về an toàn (Fix lỗi TypeError string indices)
    raw_data = result.get("data", [])

    # Xác định all_tasks là List
    all_tasks = []
    if isinstance(raw_data, list):
        all_tasks = raw_data
    elif isinstance(raw_data, dict):
        # Support phân trang (content/items)
        if "content" in raw_data:
            all_tasks = raw_data["content"]
        elif "items" in raw_data:
            all_tasks = raw_data["items"]
        else:
            all_tasks = [raw_data]  # Fallback

    if not all_tasks: return "Dự án này trống, không có task nào để xóa."

    # 4. Lọc task theo từ khóa (Safe loop)
    found_tasks = []
    not_found = []

    for kw in task_keywords:
        kw_lower = kw.lower().strip()
        matches = []

        for t in all_tasks:
            # Kiểm tra t có phải dict không
            if not isinstance(t, dict): continue

            # Lấy tên task (hỗ trợ cả title và name)
            t_name = str(t.get('title') or t.get('name', '')).lower()

            if kw_lower in t_name:
                matches.append(t)

        if matches:
            for m in matches:
                # Tránh trùng lặp
                if not any(ft['id'] == m['id'] for ft in found_tasks):
                    found_tasks.append(m)
        else:
            not_found.append(kw)

    # 5. Trả về kết quả dạng Text
    if not found_tasks:
        return f"Không tìm thấy task nào khớp với các từ khóa: {', '.join(not_found)}"

    response_lines = ["⚠️ TÔI ĐÃ TÌM THẤY CÁC TASK SAU, BẠN CÓ CHẮC MUỐN XÓA KHÔNG?"]
    response_lines.append(f"(Dự án: {target_project_name})")
    response_lines.append("-" * 30)

    # Format danh sách để Agent hiển thị cho user chọn
    for t in found_tasks:
        display_name = t.get('title') or t.get('name', 'No Name')
        status = t.get('status', 'Unknown')
        response_lines.append(f"🔴 ID: {t['id']} | Tên: {display_name} | Trạng thái: {status}")

    response_lines.append("-" * 30)
    if not_found:
        response_lines.append(f"(Không tìm thấy: {', '.join(not_found)})")

    response_lines.append("\n👉 Nếu đồng ý, hãy yêu cầu xóa các ID ở trên (hoặc 'Xóa hết danh sách trên').")

    return "\n".join(response_lines)


class BatchDeleteInput(BaseModel):
    target_project_name: str = Field(description="Tên dự án")
    task_ids: List[int] = Field(description="Danh sách ID các task cần xóa")


@tool("execute_delete_tasks_batch", args_schema=BatchDeleteInput)
def execute_delete_tasks_batch(target_project_name: str, task_ids: List[int]):
    """
    BƯỚC 2: Thực hiện xóa hàng loạt task sau khi người dùng đã chốt ID.
    """
    print(f"🔥 [Delete-Flow] Đang xóa {len(task_ids)} task trong '{target_project_name}'...")

    # (Đoạn lấy project_map giữ nguyên để validate tên dự án, nhưng không dùng ID project để gọi API nữa)
    project_map = get_project_mapping()
    ids = project_map.get(target_project_name.lower().strip())

    if not ids:
        # Nếu không tìm thấy dự án, vẫn cho phép xóa nếu user chắc chắn (hoặc return lỗi tùy bạn)
        # Nhưng tốt nhất cứ return lỗi để an toàn
        return f"❌ Lỗi: Không tìm thấy dự án '{target_project_name}'."

    results = []
    success_count = 0

    # 2. Vòng lặp xóa từng ID
    for tid in task_ids:
        # --- SỬA LẠI ENDPOINT CHO ĐÚNG VỚI BACKEND ---
        endpoint = f"/api/tasks/{tid}"
        # ---------------------------------------------

        print(f"🔌 [DELETE] {endpoint}")  # Debug log
        res = api_client.delete(endpoint)

        if "error" in res:
            results.append(f"❌ ID {tid}: Thất bại - {res.get('details', res.get('message', 'Lỗi lạ'))}")
        else:
            success_count += 1
            results.append(f"✅ ID {tid}: Đã xóa.")

    return f"### KẾT QUẢ XÓA:\nThành công: {success_count}/{len(task_ids)}\n{chr(10).join(results)}"

# --- TOOL SMART ASSIGN (ĐÚNG SPEC API) ---
class RecommendAssigneeInput(BaseModel):
    project_id: int = Field(description="ID của dự án (Bắt buộc phải là số thực tế đã tra cứu)")
    title: str = Field(description="Tiêu đề task")
    task_type: str = Field(description="Loại task: 'STORY' hoặc 'BUG'", default="STORY")
    tags: List[str] = Field(description="Danh sách từ khóa", default=[])
    story_points: int = Field(description="Độ khó ước lượng", default=3)
    description: str = Field(description="Mô tả thêm", default="")


@tool("recommend_assignee", args_schema=RecommendAssigneeInput)
def recommend_assignee(project_id: int, title: str, task_type: str = "STORY", tags: List[str] = [],
                       story_points: int = 3, description: str = ""):
    """
    Gợi ý nhân sự (Smart Assign) dựa trên ID dự án.
    """
    print(f"🧠 [Smart-Tool] Đang phân tích ứng viên cho Project ID: {project_id}, Task: '{title}'...")

    try:
        # 1. Chuẩn bị Payload
        final_tags = tags
        if not final_tags:
            ignore = ["fix", "lỗi", "bug", "task", "làm", "tạo", "cho", "cần"]
            final_tags = [w for w in title.split() if w.lower() not in ignore and len(w) > 2]

        payload = {
            "title": title,
            "description": description or title,
            "taskType": task_type.upper(),
            "tags": final_tags,
            "storyPoints": story_points
        }

        # 2. GỌI API (Có Try/Except an toàn)
        endpoint = f"/api/analytics/projects/{project_id}/recommend-assignee"

        try:
            result = api_client.post(endpoint, payload)
        except Exception as api_err:
            print(f"❌ [API Connect Error]: {api_err}")
            return "⚠️ Không thể kết nối tới hệ thống phân tích (Backend Error). Vui lòng thử lại."

        if isinstance(result, dict) and ("error" in result or result.get("status", 200) >= 400):
            err_msg = result.get("details") or result.get("message") or result.get("error")
            return f"⚠️ Backend trả về lỗi: {err_msg}"

        # 3. Xử lý kết quả
        candidates = result if isinstance(result, list) else result.get("data", [])

        if not candidates:
            return "⚠️ Không tìm thấy ứng viên phù hợp trong dự án này."

        output = [f"### 🤖 KẾT QUẢ PHÂN TÍCH (Project ID: {project_id})"]
        for c in candidates:
            name = c.get('fullName', 'Unknown')
            score = c.get('matchScore', 0)
            reason = c.get('reason', 'N/A')
            status = c.get('workloadStatus', 'NORMAL')

            icon = "🟢" if status == "LOW" else "🔴 QUÁ TẢI" if status == "OVERLOADED" else "🟠"

            output.append(f"- **{name}** (Score: {score}) {icon}")
            output.append(f"  Lý do: {reason}")
            output.append("---")

        return "\n".join(output)

    except Exception as e:
        return f"⛔ Lỗi không xác định tại Tool: {str(e)}"
#=============================================================================
# TOOL 9: LẤY DANH SÁCH THÀNH VIÊN (Mapping Tên -> UserID)
# =============================================================================

class GetProjectMembersInput(BaseModel):
    project_name: str = Field(description="Tên dự án cần xem thành viên")


@tool("get_project_members", args_schema=GetProjectMembersInput)
def get_project_members(project_name: str):
    """
    Lấy danh sách thành viên trong dự án để map từ Tên sang ID.
    Dùng khi user nói: "Giao task cho [Tên]".
    """
    print(f"👥 [Member-Tool] Đang lấy thành viên dự án '{project_name}'...")

    # 1. Map tên dự án sang ID (Công ty/Workspace/Project)
    project_map = get_project_mapping()
    ids = project_map.get(project_name.lower().strip())

    if not ids:
        return f"❌ Lỗi: Không tìm thấy dự án '{project_name}'."

    # 2. Gọi API (Đúng theo ảnh bạn cung cấp)
    # Endpoint: /api/companies/{companyId}/workspaces/{workspaceId}/projects/{projectId}/members
    endpoint = f"/api/companies/{ids['company_id']}/workspaces/{ids['workspace_id']}/projects/{ids['project_id']}/members"

    result = api_client.get(endpoint)

    if "error" in result:
        return f"Lỗi lấy danh sách thành viên: {result.get('details', result['error'])}"

    # 3. Xử lý dữ liệu trả về (Theo mẫu JSON bạn gửi: data -> content)
    # JSON mẫu: {"data": {"content": [{"userId": 7, "fullName": "..."}]}}
    data_block = result.get("data", {})
    members = []

    if isinstance(data_block, dict):
        members = data_block.get("content", [])
    elif isinstance(data_block, list):
        members = data_block  # Trường hợp API trả list trực tiếp

    if not members:
        return f"Dự án '{project_name}' hiện chưa có thành viên nào."

    # 4. Format kết quả để Agent dễ đọc
    lines = [f"### DANH SÁCH THÀNH VIÊN DỰ ÁN '{project_name}'"]
    lines.append(f"(Tổng: {len(members)} thành viên)")
    lines.append("| UserID | Tên Thành Viên | Email | Vai trò |")
    lines.append("|--- |--- |--- |---|")

    for m in members:
        # Lấy thông tin quan trọng
        u_id = m.get('userId', 'N/A')
        full_name = m.get('fullName', 'No Name')
        email = m.get('email', '')
        role = m.get('roleName', 'Member')

        lines.append(f"| {u_id} | {full_name} | {email} | {role} |")

    lines.append("\n👉 **GHI CHÚ CHO AI:**")
    lines.append("- Khi user giao task (Assign), hãy dùng **UserID** để điền vào trường `assignee_id`.")
    lines.append(
        "- Ví dụ: User nói 'Giao cho Phương', bạn tìm thấy 'Võ Thị Phương' có UserID là 8 -> Gọi create_task(..., assignee_id=8).")

    return "\n".join(lines)


# =============================================================================
# TOOL 10: DỰ BÁO TIẾN ĐỘ & RỦI RO (PROJECT FORECAST)
# =============================================================================

class ProjectForecastInput(BaseModel):
    project_name: str = Field(description="Tên dự án cần dự báo tiến độ")


@tool("get_project_forecast", args_schema=ProjectForecastInput)
def get_project_forecast(project_name: str):
    """
    Dự báo ngày hoàn thành dự án và cảnh báo rủi ro.
    """
    print(f"🔮 [Forecast-Tool] Đang tính toán dự báo cho dự án '{project_name}'...")

    project_map = get_project_mapping()
    ids = project_map.get(project_name.lower().strip())

    if not ids:
        return f"❌ Lỗi: Không tìm thấy dự án '{project_name}'."

    endpoint = f"/api/analytics/projects/{ids['project_id']}/forecast"
    result = api_client.get(endpoint)

    if "error" in result:
        return f"Lỗi gọi API dự báo: {result.get('details', result['error'])}"

    data = result.get("data", {})
    if not data:
        return "Hiện chưa có đủ dữ liệu để dự báo (Cần ít nhất 1 Sprint đã hoàn thành)."

    backlog = data.get('totalBacklogPoints', 0)
    velocity = data.get('averageVelocity', 0)
    due_date = data.get('projectDueDate', 'N/A')
    risk_level = data.get('riskLevel', 'LOW')
    risk_msg = data.get('riskMessage', '')

    opt = data.get('optimistic', {})
    likely = data.get('likely', {})
    pess = data.get('pessimistic', {})

    # [FIX] Hàm helper để xử lý text trạng thái -> Tránh lỗi SyntaxError trên Python 3.10
    def format_status(scenario):
        if not scenario.get('late'):
            return "Kịp hạn"
        return f"Trễ {scenario.get('daysLate')} ngày"

    lines = [f"### 🔮 BÁO CÁO DỰ BÁO TIẾN ĐỘ: {project_name.upper()}"]
    lines.append(f"- Tổng việc còn lại: {backlog} Points")
    lines.append(f"- Tốc độ trung bình: {velocity} Points/Sprint")
    lines.append(f"- Deadline cứng: {due_date}")
    lines.append(f"- ⚠️ MỨC ĐỘ RỦI RO: {risk_level}")
    lines.append(f"- Cảnh báo từ hệ thống: '{risk_msg}'")
    lines.append("-" * 30)

    lines.append("### 📊 3 KỊCH BẢN DỰ KIẾN:")

    # Sử dụng hàm helper đã tạo ở trên
    lines.append(f"1. ☀️ TỐT NHẤT (Optimistic): Xong ngày {opt.get('completionDate')} "
                 f"({format_status(opt)}). "
                 f"(Nếu team cày {opt.get('velocityUsed')} pts/sprint).")

    lines.append(f"2. 🎯 KHẢ THI NHẤT (Likely): Xong ngày {likely.get('completionDate')} "
                 f"({format_status(likely)}). "
                 f"(Với tốc độ hiện tại {likely.get('velocityUsed')} pts/sprint).")

    lines.append(f"3. 🌧️ XẤU NHẤT (Pessimistic): Xong ngày {pess.get('completionDate')} "
                 f"({format_status(pess)}). "
                 f"(Nếu tốc độ giảm còn {pess.get('velocityUsed')} pts/sprint).")

    lines.append("\n👉 **HƯỚNG DẪN AI:** Dựa vào 3 kịch bản trên để trả lời user một cách khéo léo.")

    return "\n".join(lines)


# =============================================================================
# TOOL 11: DỮ LIỆU HỌP NHANH (DAILY STANDUP)
# =============================================================================
class DailyStandupInput(BaseModel):
    project_name: str = Field(description="Tên dự án cần lấy báo cáo standup")


@tool("get_daily_standup", args_schema=DailyStandupInput)
def get_daily_standup(project_name: str):
    """
    Lấy dữ liệu công việc của các thành viên (Đã xong, Đang làm) để phục vụ họp Daily Standup.
    """
    print(f"☕ [Standup-Tool] Đang tổng hợp báo cáo nhanh cho dự án '{project_name}'...")

    # 1. Map tên dự án sang ID
    project_map = get_project_mapping()
    ids = project_map.get(project_name.lower().strip())

    if not ids:
        return f"❌ Lỗi: Không tìm thấy dự án '{project_name}'."

    # 2. Gọi API Standup
    endpoint = f"/api/analytics/projects/{ids['project_id']}/daily-standup"
    result = api_client.get(endpoint)

    if "error" in result:
        return f"Lỗi lấy dữ liệu Standup: {result.get('details', result['error'])}"

    # 3. [FIX QUAN TRỌNG] Bóc tách đúng lớp "data" trong JSON
    # API trả về: { "success": true, "data": { ... } }
    real_data = result.get("data", {})

    # Kiểm tra kỹ nếu real_data rỗng
    if not real_data:
        return "Không có dữ liệu standup nào trong Sprint hiện tại (Backend trả về data rỗng)."

    sprint = real_data.get('sprintName', 'Unknown Sprint')
    date = real_data.get('reportDate', 'Today')
    members = real_data.get('members', [])

    if not members:
        return f"Dự án '{project_name}' hiện chưa có thành viên nào hoạt động trong Sprint này."

    # 4. Format văn bản
    lines = [f"### ☕ BÁO CÁO DAILY STANDUP: {project_name.upper()}"]
    lines.append(f"📅 Ngày: {date} | 🏃 {sprint}")
    lines.append("-" * 30)

    for m in members:
        name = m.get('fullName', 'Unknown')
        done = m.get('completedTasks', [])
        doing = m.get('inProgressTasks', [])
        todo = m.get('todoTasks', [])

        lines.append(f"👤 **{name}**:")

        # Phần Đã Xong
        if done:
            lines.append(f"   ✅ Đã xong: {', '.join(done)}")
        else:
            # Nếu không có task xong, báo cáo nhẹ nhàng
            pass

            # Phần Đang Làm (Quan trọng nhất)
        if doing:
            lines.append(f"   🚧 Đang làm: {', '.join(doing)}")
        elif not done:
            lines.append("   ⚠️ Chưa có task nào đang chạy.")

        # Phần Sắp tới
        if todo:
            # Chỉ hiển thị tối đa 2 task todo để đỡ dài
            lines.append(f"   📋 Sắp tới: {', '.join(todo[:2])}...")

        lines.append("")  # Dòng trống

    lines.append("-" * 30)
    lines.append("👉 **HƯỚNG DẪN AI:**")
    lines.append("- Tóm tắt tình hình team dựa trên dữ liệu trên.")
    lines.append("- Nếu ai đang làm (🚧) task quan trọng (VD: Fix bug, Integrate Payment), hãy nhắc đến.")
    lines.append("- Đừng chỉ liệt kê, hãy kể chuyện tự nhiên.")

    return "\n".join(lines)