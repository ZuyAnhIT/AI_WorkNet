# mcp_servers/analytics_service/tools.py
from langchain.tools import tool
# Import api_client từ task_service để dùng chung
from mcp_servers.task_service.api_client import api_client
from typing import List, Optional
from langchain.tools import tool
from pydantic import BaseModel, Field
# Giả sử bạn để api_client và get_project_mapping ở common hoặc task_service
# Bạn hãy điều chỉnh import cho đúng vị trí file thực tế của bạn
from mcp_servers.task_service.api_client import api_client
from mcp_servers.task_service.tools import get_project_mapping

# =============================================================================
# TOOL 1: LẤY DANH SÁCH THÀNH VIÊN
# =============================================================================
class GetProjectMembersInput(BaseModel):
    project_name: str = Field(description="Tên dự án cần xem thành viên")


@tool("get_project_members", args_schema=GetProjectMembersInput)
def get_project_members(project_name: str):
    """
    Lấy danh sách thành viên dự án (User ID, Name, Role).
    Dùng để phân tích nguồn lực hoặc tìm ID nhân sự.
    """
    print(f"👥 [Analytics-Tool] Đang lấy thành viên dự án '{project_name}'...")

    project_map = get_project_mapping()
    ids = project_map.get(project_name.lower().strip())
    if not ids: return f"❌ Lỗi: Không tìm thấy dự án '{project_name}'."

    endpoint = f"/api/companies/{ids['company_id']}/workspaces/{ids['workspace_id']}/projects/{ids['project_id']}/members"
    result = api_client.get(endpoint)

    if "error" in result: return f"Lỗi API: {result.get('details', result['error'])}"

    data_block = result.get("data", {})
    members = data_block.get("content", []) if isinstance(data_block, dict) else data_block

    if not members: return f"Dự án '{project_name}' chưa có thành viên nào."

    lines = [f"### DANH SÁCH NHÂN SỰ: {project_name.upper()}"]
    lines.append("| ID | Tên | Email | Vai trò |")
    lines.append("|--- |--- |--- |---|")
    for m in members:
        lines.append(f"| {m.get('userId')} | {m.get('fullName')} | {m.get('email')} | {m.get('roleName')} |")

    return "\n".join(lines)


# =============================================================================
# TOOL 2: DỰ BÁO TIẾN ĐỘ (FORECAST)
# =============================================================================
class ProjectForecastInput(BaseModel):
    project_name: str = Field(description="Tên dự án cần dự báo")


@tool("get_project_forecast", args_schema=ProjectForecastInput)
def get_project_forecast(project_name: str):
    """
    Dự báo ngày hoàn thành và rủi ro dựa trên vận tốc (Velocity) và Backlog.
    """
    print(f"🔮 [Analytics-Tool] Dự báo tiến độ dự án '{project_name}'...")

    project_map = get_project_mapping()
    ids = project_map.get(project_name.lower().strip())
    if not ids: return f"❌ Lỗi: Không tìm thấy dự án '{project_name}'."

    result = api_client.get(f"/api/analytics/projects/{ids['project_id']}/forecast")
    if "error" in result: return f"Lỗi API: {result.get('details', result['error'])}"

    data = result.get("data", {})
    if not data: return "Chưa đủ dữ liệu Sprint để dự báo."

    def fmt(scen):
        return f"Xong {scen.get('completionDate')} ({'Trễ ' + str(scen.get('daysLate')) + ' ngày' if scen.get('late') else 'Kịp hạn'})"

    lines = [f"### 🔮 DỰ BÁO TIẾN ĐỘ: {project_name}"]
    lines.append(f"- Rủi ro: {data.get('riskLevel')} ({data.get('riskMessage')})")
    lines.append(f"- Tốc độ team: {data.get('averageVelocity')} pts/sprint")
    lines.append(f"1. ☀️ Lạc quan: {fmt(data.get('optimistic', {}))}")
    lines.append(f"2. 🎯 Khả thi: {fmt(data.get('likely', {}))}")
    lines.append(f"3. 🌧️ Bi quan: {fmt(data.get('pessimistic', {}))}")

    return "\n".join(lines)


# =============================================================================
# TOOL 3: DAILY STANDUP
# =============================================================================
class DailyStandupInput(BaseModel):
    project_name: str = Field(description="Tên dự án")


@tool("get_daily_standup", args_schema=DailyStandupInput)
def get_daily_standup(project_name: str):
    """
    Lấy dữ liệu Done/Doing/Todo của thành viên cho báo cáo Daily.
    """
    print(f"☕ [Analytics-Tool] Lấy dữ liệu Daily Standup '{project_name}'...")

    project_map = get_project_mapping()
    ids = project_map.get(project_name.lower().strip())
    if not ids: return f"❌ Lỗi: Không tìm thấy dự án '{project_name}'."

    result = api_client.get(f"/api/analytics/projects/{ids['project_id']}/daily-standup")
    data = result.get("data", {})
    if not data: return "Không có dữ liệu Standup."

    lines = [f"### ☕ DAILY REPORT: {project_name} ({data.get('reportDate')})"]
    for m in data.get('members', []):
        lines.append(f"👤 **{m.get('fullName')}**")
        if m.get('completedTasks'): lines.append(f"   ✅ Xong: {', '.join(m['completedTasks'])}")
        if m.get('inProgressTasks'): lines.append(f"   🚧 Đang làm: {', '.join(m['inProgressTasks'])}")
        if m.get('todoTasks'): lines.append(f"   📋 Sắp tới: {', '.join(m['todoTasks'][:2])}...")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# TOOL 4: SMART ASSIGN (Gợi ý người làm)
# =============================================================================
class RecommendAssigneeInput(BaseModel):
    project_id: int = Field(description="ID dự án (Bắt buộc là số nguyên). Nếu chưa có, phải hỏi user hoặc tra cứu.")
    title: str = Field(description="Tiêu đề task (Trích xuất từ yêu cầu user)")
    task_type: str = Field(description="Loại task: 'STORY' (mặc định) hoặc 'BUG' (nếu có từ lỗi/fix/bug)",
                           default="STORY")
    tags: List[str] = Field(description="Danh sách từ khóa (Keyword) liên quan", default=[])
    story_points: int = Field(description="Độ khó ước lượng (Mặc định 3 nếu không rõ)", default=3)
    description: str = Field(description="Mô tả task", default="")


@tool("recommend_assignee", args_schema=RecommendAssigneeInput)
def recommend_assignee(project_id: int, title: str, task_type: str = "STORY", tags: List[str] = [],
                       story_points: int = 3, description: str = ""):
    """
    Gợi ý nhân sự phù hợp dựa trên lịch sử task và độ bận rộn (Workload).
    """
    print(f"🧠 [Analytics-Tool] Smart Assign cho Project ID: {project_id}, Task: '{title}'...")

    try:
        # 1. Xử lý Tags nếu rỗng
        final_tags = tags
        if not final_tags:
            ignore = ["fix", "lỗi", "bug", "task", "làm", "tạo", "cho", "cần", "giao", "ai"]
            final_tags = [w for w in title.split() if w.lower() not in ignore and len(w) > 2]

        payload = {
            "title": title,
            "description": description or title,
            "taskType": task_type.upper(),
            "tags": final_tags,
            "storyPoints": story_points
        }

        # 2. Gọi API
        endpoint = f"/api/analytics/projects/{project_id}/recommend-assignee"
        # Lưu ý: Cần import api_client ở đầu file
        from mcp_servers.task_service.api_client import api_client

        try:
            result = api_client.post(endpoint, payload)
        except Exception:
            return "⚠️ Lỗi kết nối Backend."

        if isinstance(result, dict) and ("error" in result or result.get("status", 200) >= 400):
            return f"⚠️ Backend Error: {result.get('message', 'Unknown')}"

        # 3. Format Kết quả cho AI đọc
        candidates = result if isinstance(result, list) else result.get("data", [])
        if not candidates: return "⚠️ Không tìm thấy ứng viên phù hợp."

        output = [f"### 🤖 KẾT QUẢ GỢI Ý (Project ID: {project_id})"]
        for c in candidates:
            score = c.get('matchScore', 0)
            status = c.get('workloadStatus', 'NORMAL')
            icon = "🟢" if status == "LOW" else "🔴 QUÁ TẢI" if status == "OVERLOADED" else "🟠"

            output.append(f"- 👤 **{c.get('fullName')}** (Score: {score}) {icon}")
            output.append(f"  - Lý do: {c.get('reason')}")
            output.append(f"  - Workload: {c.get('currentWorkloadPoints')} points")
            output.append("---")

        return "\n".join(output)

    except Exception as e:
        return f"⛔ Lỗi Tool: {str(e)}"

from langchain.tools import tool
# Import api_client từ task_service để dùng chung
from mcp_servers.task_service.api_client import api_client
@tool("get_user_profile")
def get_user_profile():
    """
    Lấy thông tin cá nhân VÀ DANH SÁCH DỰ ÁN user đang tham gia.
    Dùng tool này để tra cứu ID dự án nhanh nhất.
    """
    print("👤 [User-Tool] Đang gọi /api/users/me để lấy Profile & Project List...")

    # Gọi API
    result = api_client.get("/api/users/me")

    if "error" in result:
        return f"Lỗi lấy profile: {result.get('details', result['error'])}"

    data = result.get("data", {})
    if not data: return "Không tìm thấy dữ liệu user."

    # 1. Thông tin cơ bản
    lines = [f"### 👤 USER PROFILE: {data.get('fullName')} (ID: {data.get('id')})"]
    lines.append(f"- Email: {data.get('email')}")
    lines.append(f"- Role: {data.get('status')}")

    # 2. Bóc tách danh sách dự án (QUAN TRỌNG NHẤT)
    projects = data.get("projectMemberships", [])

    if projects:
        lines.append("\n### 📂 DANH SÁCH DỰ ÁN ĐÃ THAM GIA (Dùng để map ID):")
        lines.append("| ID | Tên Dự Án | Workspace | Vai trò |")
        lines.append("|--- |--- |--- |---|")

        for p in projects:
            p_id = p.get('projectId')
            p_name = p.get('projectName')
            w_id = p.get('workspaceId')
            role = p.get('roleCode')
            lines.append(f"| {p_id} | {p_name} | WS-{w_id} | {role} |")

        lines.append("\n💡 **GHI CHÚ CHO AI:** Nếu user nhắc tên dự án, hãy lấy ID ở cột đầu tiên.")
    else:
        lines.append("\n⚠️ User chưa tham gia dự án nào.")

    return "\n".join(lines)