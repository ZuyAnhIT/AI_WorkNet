import os
import itertools
from dotenv import load_dotenv

# Load môi trường từ file .env với quyền ưu tiên ghi đè (override)
load_dotenv(override=True)


# =============================================================================
# 1. QUẢN LÝ API KEYS (Dành cho Gemini nếu cần xoay vòng tránh Rate Limit)
# =============================================================================
class GeminiKeyManager:
    _key_cycle = None

    @classmethod
    def get_next_key(cls):
        """Lấy Key tiếp theo trong danh sách xoay vòng."""
        if cls._key_cycle is None:
            cls._init_keys()
        return next(cls._key_cycle)

    @classmethod
    def _init_keys(cls):
        """Khởi tạo danh sách Key từ biến môi trường GEMINI_API_KEYS."""
        # Thử lấy từ GEMINI_API_KEYS (nhiều key cách nhau bằng dấu phẩy) hoặc GEMINI_API_KEY (1 key)
        raw_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or ""

        # Làm sạch chuỗi và chuyển thành list
        final_keys = [k.strip() for k in raw_keys.replace('\n', ',').split(',') if k.strip()]

        if not final_keys:
            # Nếu không tìm thấy key, thông báo để tránh lỗi crash
            final_keys = ["DUMMY_KEY"]
        else:
            print(f"🔑 [LLM Factory] Đã tải {len(final_keys)} Gemini API Keys.")

        cls._key_cycle = itertools.cycle(final_keys)


# =============================================================================
# 2. FACTORY CHÍNH (Đã fix lỗi tham số role & tối ưu cho Groq/Gemini)
# =============================================================================
def get_llm(temperature=0, role=None, **kwargs):
    """
    Factory trả về đối tượng LLM dựa trên cấu hình LLM_PROVIDER trong .env.

    Tham số:
    - temperature: Độ sáng tạo (0 là chính xác nhất, dùng cho Tool Call).
    - role: Nhãn của Agent yêu cầu (supervisor, project, task...).
    - **kwargs: Các tham số bổ sung tùy chọn.
    """

    # Lấy nhà cung cấp LLM từ môi trường, mặc định là 'groq'
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    # Log để theo dõi Agent nào đang gọi Model nào (Hữu ích khi Debug)
    # if role: print(f"🤖 [Factory] Agent '{role}' đang khởi tạo {provider.upper()}...")

    # --- 1. GROQ (ƯU TIÊN HIỆN TẠI) ---
    if provider == "groq":
        from langchain_groq import ChatGroq
        # Llama 3.3 70B Versatile là bản tốt nhất của Groq cho Tool Calling
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        return ChatGroq(
            model=model_name,
            temperature=temperature,
            api_key=os.getenv("GROQ_API_KEY"),
            max_retries=2
        )

    # --- 2. GOOGLE GEMINI ---
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        current_key = GeminiKeyManager.get_next_key()
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            google_api_key=current_key,
            max_retries=2,
            # Gemini đôi khi chặn các câu trả lời mang tính kỹ thuật/code,
            # có thể điều chỉnh safety_settings tại đây nếu cần.
        )

    # --- 3. DEEPSEEK ---
    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="deepseek-chat",
            temperature=temperature,
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            max_retries=2
        )

    # --- 4. OLLAMA (Dành cho chạy Local) ---
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )

    else:
        raise ValueError(f"❌ Provider '{provider}' chưa được hỗ trợ trong hệ thống!")