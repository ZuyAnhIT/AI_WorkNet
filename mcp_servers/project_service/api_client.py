import requests
import json
from utils.config import Config


class ProjectApiClient:
    def __init__(self):
        self.base_url = Config.JAVA_BASE_URL
        self.token = Config.JAVA_ACCESS_TOKEN

    def get_headers(self, is_multipart=False):
        headers = {
            "Authorization": f"Bearer {self.token}",
        }
        if not is_multipart:
            headers["Content-Type"] = "application/json"
        return headers

    def get(self, endpoint):
        """Hàm gọi API GET (Mới thêm)"""
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers()

        try:
            print(f"🔌 [Connecting] GET {url}")
            response = requests.get(url, headers=headers)

            if response.status_code == 401:
                return {"error": "Token hết hạn hoặc không hợp lệ. Hãy cập nhật lại .env"}

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = e.response.text if e.response else str(e)
            print(f"❌ [API Error]: {error_msg}")
            return {"error": str(e), "details": error_msg}

    def post_multipart(self, endpoint, payload_dict):
        """Hàm gọi API POST Multipart (Giữ nguyên)"""
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers(is_multipart=True)

        files = {
            'data': (None, json.dumps(payload_dict), 'application/json'),
            'file': (None, bytes(), 'application/octet-stream')
        }

        try:
            print(f"🔌 [Connecting] POST MULTIPART {url}")
            response = requests.post(url, headers=headers, files=files)

            if response.status_code == 415:
                return {"error": "415 Unsupported Media Type. Server Java từ chối format này."}

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            error_msg = e.response.text if e.response else str(e)
            print(f"❌ [API Error]: {error_msg}")
            return {"error": str(e), "details": error_msg}


api_client = ProjectApiClient()