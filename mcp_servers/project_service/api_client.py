import requests
import json
from utils.config import Config
# Import hàm lấy token động từ context
from utils.request_context import get_user_token

class ProjectApiClient:
    def __init__(self):
        self.base_url = Config.JAVA_BASE_URL

    def get_token(self):
        """Lấy Token ưu tiên từ Context hoặc .env"""
        dynamic_token = get_user_token()
        if dynamic_token:
            return dynamic_token
        return Config.JAVA_ACCESS_TOKEN

    def get_headers(self, is_multipart=False):
        token = self.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
        }
        if not is_multipart:
            headers["Content-Type"] = "application/json"
        return headers

    def _handle_response(self, response):
        """Xử lý phản hồi chung"""
        if response.status_code == 401:
            return {"error": "AUTH_ERROR", "details": "Token hết hạn."}
        if response.status_code == 403:
            return {"error": "PERMISSION_DENIED", "details": "Không đủ quyền."}
        if response.status_code >= 400:
            print(f"❌ [API Error {response.status_code}]: {response.text}")
            try:
                return {"error": f"API_ERROR_{response.status_code}", "details": response.json()}
            except:
                return {"error": f"API_ERROR_{response.status_code}", "details": response.text}
        try:
            return response.json()
        except:
            return {"status": "success", "message": "Operation completed."}

    # --- GET ---
    def get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Project-Client] GET {url}")
            response = requests.get(url, headers=self.get_headers())
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    # --- POST (JSON) - Thêm hàm này ---
    def post(self, endpoint, payload_dict):
        """Gửi POST request dạng JSON (thay vì multipart)"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Project-Client] POST (JSON) {url}")
            response = requests.post(url, headers=self.get_headers(), json=payload_dict)
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    # --- PUT (JSON) - QUAN TRỌNG: Sửa lỗi AttributeError ---
    def put(self, endpoint, payload_dict):
        """Gửi PUT request dạng JSON chuẩn"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Project-Client] PUT (JSON) {url}")
            # requests.put tự động encode dict thành json và set Content-Type nếu dùng tham số json=
            response = requests.put(url, headers=self.get_headers(), json=payload_dict)
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    # --- PATCH (JSON) - Thêm dự phòng ---
    def patch(self, endpoint, payload_dict):
        """Gửi PATCH request dạng JSON"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Project-Client] PATCH (JSON) {url}")
            response = requests.patch(url, headers=self.get_headers(), json=payload_dict)
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    # --- Các hàm cũ (Multipart/Delete) giữ nguyên ---
    def post_multipart(self, endpoint, payload_dict):
        # ... (Giữ nguyên code cũ của bạn) ...
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers(is_multipart=True)
        files = {
            'data': (None, json.dumps(payload_dict), 'application/json'),
            'file': (None, bytes(), 'application/octet-stream')
        }
        try:
            print(f"🔌 [Project-Client] POST MULTIPART {url}")
            response = requests.post(url, headers=headers, files=files)
            if response.status_code == 415:
                return {"error": "415 Unsupported Media Type."}
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def put_multipart(self, endpoint, payload_dict):
        # ... (Giữ nguyên code cũ của bạn) ...
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers(is_multipart=True)
        files = {
            'data': (None, json.dumps(payload_dict), 'application/json'),
            'file': (None, bytes(), 'application/octet-stream')
        }
        try:
            print(f"🔌 [Project-Client] PUT MULTIPART {url}")
            response = requests.put(url, headers=headers, files=files)
            if response.status_code == 415:
                return {"error": "415 Unsupported Media Type."}
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def delete(self, endpoint):
        # ... (Giữ nguyên code cũ của bạn) ...
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Project-Client] DELETE {url}")
            response = requests.delete(url, headers=self.get_headers(is_multipart=False))
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

# Singleton instance
api_client = ProjectApiClient()