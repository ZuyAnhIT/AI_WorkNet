from langchain_google_genai import ChatGoogleGenerativeAI
from utils.config import Config


def get_llm(temperature=0, role="general"):
    """
    Factory trả về LLM với API Key tương ứng cho từng vai trò.
    role: 'supervisor', 'project', 'task', 'general'
    """

    # 1. Chọn Key dựa trên Role
    api_key = Config.KEY_GENERAL  # Mặc định

    if role == "supervisor":
        api_key = Config.KEY_SUPERVISOR
    elif role == "project":
        api_key = Config.KEY_PROJECT
    elif role == "task":
        api_key = Config.KEY_TASK

    # Fallback: Nếu role đó chưa có key riêng thì dùng key Supervisor đỡ
    if not api_key:
        api_key = Config.KEY_SUPERVISOR

    if not api_key:
        raise ValueError(f"❌ Không tìm thấy API Key cho role: {role}")

    # 2. Khởi tạo Model
    llm = ChatGoogleGenerativeAI(
        model=Config.GEMINI_MODEL,
        google_api_key=api_key,
        temperature=temperature,
        convert_system_message_to_human=True,
        transport="rest"
    )
    return llm