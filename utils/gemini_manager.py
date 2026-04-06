# utils/gemini_manager.py

import os
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, InternalServerError

class GeminiKeyManager:
    def __init__(self):
        # 1. Load Keys từ biến môi trường
        keys_str = os.getenv("GEMINI_API_KEYS", "")
        self.api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if not self.api_keys:
            raise ValueError("❌ [Gemini Manager] Chưa cấu hình GEMINI_API_KEYS trong .env")

        # Mặc định sử dụng gemini-2.5-flash
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.current_key_index = 0
        print(f"🚀 [Gemini Manager] Đã load {len(self.api_keys)} Keys. Model: {self.model_name}")

    def _get_current_key(self) -> str:
        return self.api_keys[self.current_key_index]

    def _rotate_key(self):
        """Chuyển sang key tiếp theo trong danh sách vòng tròn"""
        old_key = self._get_current_key()[-4:]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        new_key = self._get_current_key()[-4:]
        print(f"🔄 [Key Rotation] Key ...{old_key} bị lỗi/hết hạn. ➡️ Đổi sang Key ...{new_key}")

    def get_llm(self, temperature=0.3) -> ChatGoogleGenerativeAI:
        """Tạo đối tượng LLM mới với Key hiện tại"""
        return ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=self._get_current_key(),
            temperature=temperature
            # ĐÃ XÓA: convert_system_message_to_human=True
        )

    def invoke_with_retry(self, messages, max_retries=3):
        """
        Hàm gọi model thông minh: Tự động đổi key khi gặp lỗi Quota.
        """
        attempt = 0
        # Cho phép thử lại số lần = số lượng key + max_retries
        limit = len(self.api_keys) + max_retries

        while attempt < limit:
            try:
                llm = self.get_llm()
                # print(f"🔌 [Gemini] Đang gọi API (Key Index: {self.current_key_index})...")

                # Gọi API
                return llm.invoke(messages)

            except (ResourceExhausted, ServiceUnavailable) as e:
                # Bắt đúng lỗi hết tiền/hết quota của Google
                print(f"⚠️ [Gemini Error] Quota Exceeded: {str(e)}")
                print("♻️ Đang kích hoạt cơ chế ĐẢO KEY...")

                self._rotate_key()  # Đổi key
                attempt += 1
                time.sleep(1)  # Nghỉ 1s

            except Exception as e:
                print(f"❌ [Gemini Critical Error]: {str(e)}")
                raise e  # Lỗi khác (Code/Prompt) thì văng lỗi luôn

        raise Exception("⛔ Tất cả Key đều đã thử nhưng vẫn thất bại! Vui lòng thêm Key mới.")

# Export instance để dùng chung 
# (Vẫn giữ tên biến analytics_engine để không làm lỗi các file cũ đang import nó)
analytics_engine = GeminiKeyManager()