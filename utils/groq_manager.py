# utils/groq_manager.py

import os
from itertools import cycle
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()


class GroqKeyManager:
    def __init__(self):
        # 1. Load danh sách key
        keys_str = os.getenv("GROQ_API_KEYS", "")
        if not keys_str:
            # Fallback nếu dùng biến cũ
            keys_str = os.getenv("GROQ_API_KEY", "")

        self.keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if not self.keys:
            raise ValueError("❌ [Groq Manager] Không tìm thấy Key nào trong .env!")

        self.model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.key_cycle = cycle(self.keys)
        self.current_key = next(self.key_cycle)

        print(f"🚀 [Groq Manager] Init Model: {self.model_name}")
        print(f"🔑 [Groq Manager] Loaded {len(self.keys)} keys. Active: ...{self.current_key[-10:]}")

    def _rotate_key(self):
        """Chuyển sang key tiếp theo"""
        old_key = self.current_key
        self.current_key = next(self.key_cycle)
        print(f"🔄 [Groq Rotate] Đổi Key: ...{old_key[-6:]} ➡ ...{self.current_key[-6:]}")
        return self.current_key

    def get_llm(self, temperature=0):
        """Trả về model Groq với key hiện tại"""
        return ChatGroq(
            model=self.model_name,
            temperature=temperature,
            api_key=self.current_key,
            max_retries=1  # Tắt auto-retry của thư viện để mình tự quản lý
        )


# Singleton Instance
groq_engine = GroqKeyManager()