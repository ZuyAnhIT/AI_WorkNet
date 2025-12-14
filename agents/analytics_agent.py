# agents/analytics_agent.py

# =============================================================================
# 1. IMPORT CÁC TOOLS NGHIỆP VỤ (ANALYTICS SERVICE)
# =============================================================================
from mcp_servers.analytics_service.tools import (
    get_project_members,  # Lấy danh sách thành viên để map Tên -> UserID
    get_project_forecast,  # Dự báo ngày hoàn thành và rủi ro
    get_daily_standup,  # Tổng hợp dữ liệu Done/Doing cho họp Daily
    recommend_assignee  # Gợi ý người làm dựa trên Skill và Workload
)

# =============================================================================
# 2. IMPORT TOOLS HỖ TRỢ NGỮ CẢNH (USER SERVICE)
# =============================================================================
# Quan trọng: Tool này nằm ở user_service, dùng để lấy danh sách dự án user tham gia
# Giúp AI tự động map Tên dự án -> ID mà không cần hỏi lại user
from mcp_servers.user_service.tools import get_user_profile


def create_analytics_agent():
    """
    Khởi tạo và trả về danh sách công cụ dành cho Analytics Agent.

    Quy trình hoạt động lý tưởng của Agent:
    1. Gọi get_user_profile để lấy context projectMemberships (Tên & ID dự án).
    2. Sử dụng project_id tìm được để thực thi các tool phân tích nghiệp vụ.
    """

    analytics_tools = [
        # --- Nhóm 1: Tra cứu ngữ cảnh (Ưu tiên) ---
        get_user_profile,  # Tự động lấy profile và list dự án có ID

        # --- Nhóm 2: Phân tích và Gợi ý ---
        recommend_assignee,  # Smart Assignee Recommendation

        # --- Nhóm 3: Dự báo và Báo cáo ---
        get_project_forecast,  # Dự báo tiến độ & rủi ro trễ hạn
        get_daily_standup,  # Dữ liệu họp nhanh Daily Standup
        get_project_members  # Mapping thành viên dự án (Tên -> ID)
    ]

    return analytics_tools