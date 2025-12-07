import requests
import json
from utils.config import Config


class TaskApiClient:
    def __init__(self):
        self.base_url = Config.JAVA_BASE_URL
        self.token = Config.JAVA_ACCESS_TOKEN

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Task-Client] GET {url}")
            response = requests.get(url, headers=self.get_headers())

            if response.status_code == 401: return {"error": "Token hết hạn."}
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # In lỗi chi tiết ra Terminal
            if 'response' in locals():
                print(f"❌ [API Error Body]: {response.text}")
            return {"error": str(e)}

    def post(self, endpoint, payload_dict):
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Task-Client] POST {url}")
            # print(f"📦 [Payload]: {json.dumps(payload_dict, indent=2)}") # Uncomment để xem payload gửi đi

            response = requests.post(url, headers=self.get_headers(), json=payload_dict)

            if response.status_code == 401: return {"error": "Token hết hạn."}

            # Nếu lỗi, in nội dung lỗi từ Java ra
            if response.status_code >= 400:
                print(f"❌ [API Error {response.status_code}]: {response.text}")
                return {"error": f"HTTP {response.status_code}", "details": response.text}

            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"error": str(e), "details": str(e)}


api_client = TaskApiClient()