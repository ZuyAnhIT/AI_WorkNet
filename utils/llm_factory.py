import os
import itertools
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.config import Config
from dotenv import load_dotenv

# Load lại env để chắc chắn cập nhật mới nhất
load_dotenv(override=True)


# =============================================================================
# 1. LOGIC LOAD KEY AN TOÀN
# =============================================================================

def safe_load_keys():
    """
    Load key an toàn, chấp nhận cả String (từ .env) và List (từ Config).
    """
    keys_to_process = []

    # 1. Ưu tiên lấy từ biến môi trường
    env_val = os.getenv("GEMINI_API_KEYS", "")
    if env_val:
        keys_to_process = env_val

    # 2. Nếu env rỗng, thử lấy từ Config
    if not keys_to_process:
        keys_to_process = getattr(Config, "GEMINI_API_KEYS", None) or getattr(Config, "GEMINI_API_KEY", None)

    # 3. Xử lý chuẩn hóa
    final_keys = []

    if isinstance(keys_to_process, list):
        for k in keys_to_process:
            s = str(k).strip()
            if s: final_keys.append(s)

    elif isinstance(keys_to_process, str):
        for k in keys_to_process.split(","):
            s = str(k).strip()
            if s: final_keys.append(s)

    # 4. Fallback cuối cùng
    if not final_keys:
        single = os.getenv("GEMINI_API_KEY")
        if single:
            final_keys = [str(single).strip()]

    return final_keys


# Thực thi load
_keys_list = safe_load_keys()

# Nếu vẫn rỗng -> Báo lỗi nhưng không crash server ngay (để dễ debug)
if not _keys_list:
    print("⚠️  CẢNH BÁO: Không tìm thấy API Key nào! Hãy kiểm tra .env.")
    _keys_list = ["DUMMY_KEY"]

# Tạo vòng lặp vô tận
_key_cycle = itertools.cycle(_keys_list)

print(f"🔑 [System] Đã tải {_keys_list.__len__()} API Keys. Hệ thống sẵn sàng!")


def get_next_key():
    return next(_key_cycle)


# =============================================================================
# 2. FACTORY FUNCTION
# =============================================================================

def get_llm(temperature=0, role="general"):
    """
    Factory trả về LLM, tự động đổi Key mỗi lần gọi.
    """
    current_key = get_next_key()

    # [DEBUG] Bỏ comment dòng dưới nếu bạn muốn biết chính xác key nào đang được dùng
    # masked_key = f"...{current_key[-6:]}" if len(current_key) > 6 else "Key???"
    # print(f"🔄 [LLM] Role '{role}' đang dùng Key: {masked_key}")

    llm = ChatGoogleGenerativeAI(
        model=Config.GEMINI_MODEL,
        google_api_key=current_key,
        temperature=temperature,
        # convert_system_message_to_human=True, # <--- Đã xóa dòng này vì nó Deprecated
        max_retries=5
    )
    return llm