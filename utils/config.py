import os
from dotenv import load_dotenv

# Load file .env
load_dotenv()

class Config:
    # 1. Cấu hình AI (Gemini)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # 2. Cấu hình Java Backend
    # Đọc key BACKEND_BASE_URL (ưu tiên) hoặc JAVA_BACKEND_URL (cũ)
    JAVA_BASE_URL = os.getenv("BACKEND_BASE_URL") or os.getenv("JAVA_BACKEND_URL", "http://localhost:8082")
    JAVA_ACCESS_TOKEN = os.getenv("JAVA_ACCESS_TOKEN")

    @staticmethod
    def validate():
        if not Config.GEMINI_API_KEY:
            raise ValueError("❌ Thiếu GEMINI_API_KEY trong file .env")
        if not Config.JAVA_ACCESS_TOKEN:
            raise ValueError("❌ Thiếu JAVA_ACCESS_TOKEN trong file .env. Hãy copy token sau khi login và dán vào.")