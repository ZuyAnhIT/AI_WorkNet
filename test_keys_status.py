import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Lấy danh sách key
keys_str = os.getenv("GEMINI_API_KEYS", "")
keys = [k.strip() for k in keys_str.split(",") if k.strip()]

print(f"🔍 Tìm thấy {len(keys)} Key trong file .env")

model_name = "gemini-2.0-flash" # Hoặc model bạn đang dùng

for index, key in enumerate(keys):
    print(f"\n👉 Đang test Key {index + 1}: ...{key[-6:]}")
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Chào, bạn có khỏe không?")
        print(f"   ✅ Key {index + 1} HOẠT ĐỘNG TỐT! (Phản hồi: {response.text.strip()})")
    except Exception as e:
        print(f"   ❌ Key {index + 1} BỊ LỖI (CHẾT): {e}")
