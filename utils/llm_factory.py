import os
from dotenv import load_dotenv

# Load môi trường
load_dotenv(override=True)

# 👇 Chỉ import sẵn Gemini (Vì nó đang là bộ não chính)
from utils.gemini_manager import analytics_engine

# =============================================================================
# FACTORY CHÍNH 
# =============================================================================
def get_llm(temperature=0, role=None, **kwargs):
    """
    Factory trả về đối tượng LLM dựa trên cấu hình LLM_PROVIDER.
    """
    # Lấy nhà cung cấp LLM từ môi trường, mặc định là 'gemini'
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    # --- 1. GROQ ---
    if provider == "groq":
        # LAZY IMPORT: Chuyển import vào trong hàm. 
        # Nếu không có key Groq trong .env thì hệ thống khởi động vẫn không bị crash!
        from utils.groq_manager import groq_engine
        return groq_engine.get_llm(temperature=temperature)

    # --- 2. GOOGLE GEMINI ---
    elif provider == "gemini":
        return analytics_engine.get_llm(temperature=temperature)

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

    # --- 4. OLLAMA (Local) ---
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )

    else:
        raise ValueError(f"❌ Provider '{provider}' chưa được hỗ trợ trong hệ thống!")