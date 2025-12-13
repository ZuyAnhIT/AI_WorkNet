import os
import itertools
from dotenv import load_dotenv

# Load môi trường
load_dotenv(override=True)


# ... (Giữ nguyên class GeminiKeyManager không đổi) ...
class GeminiKeyManager:
    _key_cycle = None

    @classmethod
    def get_next_key(cls):
        if cls._key_cycle is None:
            cls._init_keys()
        return next(cls._key_cycle)

    @classmethod
    def _init_keys(cls):
        raw_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or ""
        final_keys = [k.strip() for k in raw_keys.replace('\n', ',').split(',') if k.strip()]
        if not final_keys:
            print("⚠️ [Gemini Manager] Không tìm thấy Key! Sử dụng key giả.")
            final_keys = ["DUMMY_KEY"]
        print(f"🔑 [Gemini Manager] Đã tải {len(final_keys)} API Keys.")
        cls._key_cycle = itertools.cycle(final_keys)


# =============================================================================
# 2. FACTORY CHÍNH (Đã fix lỗi tham số role)
# =============================================================================
def get_llm(temperature=0, role=None, **kwargs):  # <--- THÊM role và **kwargs VÀO ĐÂY
    """
    Factory trả về LLM dựa trên biến môi trường LLM_PROVIDER.
    Chấp nhận tham số 'role' để tương thích ngược nhưng có thể không dùng.
    """
    # Mặc định dùng 'groq' nếu không khai báo
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    # (Optional) Log xem role nào đang gọi
    # if role: print(f"🤖 [LLM Factory] Role '{role}' đang yêu cầu model {provider.upper()}")

    # --- 1. GROQ (ƯU TIÊN SỐ 1) ---
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=temperature,
            api_key=os.getenv("GROQ_API_KEY"),
            max_retries=2
        )

    # --- 2. DEEPSEEK ---
    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="deepseek-chat",
            temperature=temperature,
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            max_retries=2
        )

    # --- 3. GOOGLE GEMINI ---
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        current_key = GeminiKeyManager.get_next_key()
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            temperature=temperature,
            google_api_key=current_key,
            max_retries=2
        )

    # --- 4. OLLAMA ---
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )

    else:
        raise ValueError(f"❌ Provider '{provider}' chưa được hỗ trợ!")