import requests
import json
from utils.config import Config
from utils.request_context import get_user_token

class SubtaskApiClient:
    def __init__(self):
        self.base_url = Config.JAVA_BASE_URL

    def get_token(self):
        dynamic_token = get_user_token()
        return dynamic_token if dynamic_token else Config.JAVA_ACCESS_TOKEN

    def get_headers(self, is_multipart=False):
        token = self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        if not is_multipart:
            headers["Content-Type"] = "application/json"
        return headers

    def _handle_response(self, response):
        if response.status_code == 401:
            return {"error": "AUTH_ERROR", "details": "Token không hợp lệ hoặc hết hạn."}
        if response.status_code == 403:
            return {"error": "PERMISSION_DENIED", "details": "Không có quyền thực hiện."}
        if response.status_code >= 400:
            print(f"❌ [Subtask API Error {response.status_code}]: {response.text}")
            try:
                error_body = response.json()
                return {"error": f"API_ERROR_{response.status_code}", "details": error_body.get("detail") or error_body.get("message") or error_body}
            except:
                return {"error": f"API_ERROR_{response.status_code}", "details": response.text}
        try:
            return response.json()
        except:
            return {"status": "success", "message": "Operation completed."}

    def get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Subtask-Client] GET {url}")
            response = requests.get(url, headers=self.get_headers())
            return self._handle_response(response)
        except Exception as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def post(self, endpoint, payload_dict):
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Subtask-Client] POST (JSON) {url}")
            response = requests.post(url, headers=self.get_headers(), json=payload_dict)
            return self._handle_response(response)
        except Exception as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

# Singleton instance
subtask_api_client = SubtaskApiClient()