from langchain_google_genai import ChatGoogleGenerativeAI
from utils.config import Config

def get_llm(temperature=0):
    """
    Factory trả về model Gemini đã được cấu hình.
    """
    if not Config.GEMINI_API_KEY:
        raise ValueError("Chưa cấu hình GEMINI_API_KEY!")

    llm = ChatGoogleGenerativeAI(
        model=Config.GEMINI_MODEL,
        google_api_key=Config.GEMINI_API_KEY,
        temperature=temperature,
        convert_system_message_to_human=True # Giúp Gemini hiểu rõ vai trò System
    )
    return llm