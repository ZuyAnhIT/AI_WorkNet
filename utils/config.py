import os
from dotenv import load_dotenv

load_dotenv(override=True)


class Config:
    # Model
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Danh sách Keys
    KEY_SUPERVISOR = os.getenv("GEMINI_KEY_SUPERVISOR")
    KEY_PROJECT = os.getenv("GEMINI_KEY_PROJECT")
    KEY_TASK = os.getenv("GEMINI_KEY_TASK")
    KEY_GENERAL = os.getenv("GEMINI_KEY_GENERAL")

    # Java
    JAVA_BASE_URL = os.getenv("BACKEND_BASE_URL") or os.getenv("JAVA_BACKEND_URL", "http://localhost:8082")
    JAVA_ACCESS_TOKEN = os.getenv("JAVA_ACCESS_TOKEN")

    @staticmethod
    def validate():
        if not Config.KEY_SUPERVISOR:
            raise ValueError("❌ Thiếu GEMINI_KEY_SUPERVISOR")
        # Có thể validate thêm các key khác nếu cần