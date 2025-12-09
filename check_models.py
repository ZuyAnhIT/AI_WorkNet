import os
import google.generativeai as genai
from dotenv import load_dotenv
import sys

# --- 1. Load cấu hình ---
load_dotenv(override=True)

# Lấy key
keys_str = os.getenv("GEMINI_API_KEYS", "")
keys_list = [k.strip() for k in keys_str.split(",") if k.strip()]

if keys_list:
    api_key = keys_list[0]
    print(f"🔑 Đang dùng Key: ...{api_key[-6:]}")
else:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        print(f"🔑 Đang dùng Single Key: ...{api_key[-6:]}")
    else:
        print("❌ LỖI: Không tìm thấy API Key nào trong file .env")
        sys.exit(1)

# --- 2. Kết nối ---
genai.configure(api_key=api_key)

print("\n📡 Đang lấy danh sách Model (Chế độ tương thích)...\n")

try:
    print(f"{'ID MODEL (Copy cái này)':<40} | {'TÍNH NĂNG'}")
    print("-" * 70)

    found_flash = False

    for m in genai.list_models():
        # Lấy methods an toàn
        methods = getattr(m, 'supported_generation_methods', [])

        if 'generateContent' in methods:
            # Chỉ in ra name (ID model) vì nó luôn tồn tại
            model_id = m.name
            print(f"✅ {model_id:<37} | {methods}")

            if "flash" in model_id:
                found_flash = True

    print("-" * 70)

    if found_flash:
        print("\n✨ Tìm thấy model dòng Flash! Hãy sửa file .env thành:")
        print("GEMINI_MODEL=gemini-1.5-flash")
    else:
        print("\n⚠️ Không thấy dòng 'flash'. Có thể thư viện quá cũ.")
        print("👉 Hãy thử dùng model cổ điển: GEMINI_MODEL=gemini-pro")

except Exception as e:
    print(f"\n❌ LỖI KẾT NỐI: {e}")