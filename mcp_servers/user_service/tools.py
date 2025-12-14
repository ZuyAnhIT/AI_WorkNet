# mcp_servers/user_service/tools.py
from langchain.tools import tool
from mcp_servers.task_service.api_client import api_client


@tool("get_user_profile")
def get_user_profile():
    """
    Lấy thông tin cá nhân và DANH SÁCH DỰ ÁN người dùng đang tham gia.
    Đây là công cụ quan trọng nhất để tìm ID dự án từ tên dự án.
    """
    print("👤 [User-Tool] Đang truy vấn profile tại /api/users/me...")

    # Thực hiện gọi API
    result = api_client.get("/api/users/me")

    if "error" in result:
        return f"Lỗi lấy thông tin người dùng: {result.get('details', result['error'])}"

    data = result.get("data", {})
    if not data:
        return "⚠️ Không tìm thấy dữ liệu người dùng."

    # Xây dựng phản hồi cho AI đọc
    lines = [f"### 👤 THÔNG TIN NGƯỜI DÙNG: {data.get('fullName')}"]

    # Trích xuất danh sách dự án để AI tự map Tên -> ID
    projects = data.get("projectMemberships", [])
    if projects:
        lines.append("\n### 📂 DANH SÁCH DỰ ÁN CỦA BẠN (Sử dụng để lấy ID):")
        lines.append("| ID Dự án | Tên Dự án | Vai trò |")
        lines.append("|--- |--- |---|")
        for p in projects:
            lines.append(f"| {p.get('projectId')} | {p.get('projectName')} | {p.get('roleCode')} |")

        lines.append(
            "\n💡 **Ghi chú cho AI:** Hãy sử dụng bảng này để tra cứu ID dự án chính xác trước khi thực hiện phân tích.")
    else:
        lines.append("\n⚠️ Bạn chưa tham gia vào bất kỳ dự án nào.")

    return "\n".join(lines)