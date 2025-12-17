import os
from dotenv import load_dotenv

# Load môi trường
load_dotenv(override=True)

# 👇 IMPORT CÁC MANAGER (Đã tích hợp sẵn logic xoay key)
from utils.groq_manager import groq_engine
from utils.gemini_manager import analytics_engine # Bản chất là Gemini Manager

# =============================================================================
# FACTORY CHÍNH (Đã nâng cấp để dùng Auto-Rotate Key)
# =============================================================================
def get_llm(temperature=0, role=None, **kwargs):
    """
    Factory trả về đối tượng LLM dựa trên cấu hình LLM_PROVIDER.
    Giờ đây nó sẽ gọi sang các Manager để đảm bảo lấy được Key đang sống (Active).
    """

    # Lấy nhà cung cấp LLM từ môi trường, mặc định là 'groq'
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    # Log nhẹ để debug (có thể tắt đi)
    # if role: print(f"🤖 [Factory] Agent '{role}' đang yêu cầu model từ {provider.upper()}...")

    # --- 1. GROQ (Sử dụng GroqKeyManager) ---
    if provider == "groq":
        # Gọi sang Manager để lấy model với key hiện tại
        return groq_engine.get_llm(temperature=temperature)

    # --- 2. GOOGLE GEMINI (Sử dụng GeminiKeyManager) ---
    elif provider == "gemini":
        # Gọi sang Manager để lấy model với key hiện tại
        return analytics_engine.get_llm(temperature=temperature)

    # --- 3. DEEPSEEK (Giữ nguyên logic cũ - chưa có manager) ---
    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="deepseek-chat",
            temperature=temperature,
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            max_retries=2
        )

    # --- 4. OLLAMA (Local - Giữ nguyên logic cũ) ---
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )

    else:
        raise ValueError(f"❌ Provider '{provider}' chưa được hỗ trợ trong hệ thống!")