import requests
import json
from utils.config import Config
# Import hàm lấy token động từ context
from utils.request_context import get_user_token

class ProjectApiClient:
    def __init__(self):
        self.base_url = Config.JAVA_BASE_URL
        # Lưu ý: Không lưu self.token tĩnh ở đây nữa

    def get_token(self):
        """
        Lấy Token ưu tiên:
        1. Token từ Context (do Swagger/Frontend gửi lên qua API).
        2. Token từ file .env (Fallback nếu chạy local CLI).
        """
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

    # --- HÀM XỬ LÝ PHẢN HỒI CHUNG ---
    def _handle_response(self, response):
        """Xử lý các mã lỗi HTTP để trả về thông báo rõ ràng cho AI"""
        # 1. Lỗi Token hết hạn
        if response.status_code == 401:
            return {"error": "AUTH_ERROR", "details": "Token đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại."}

        # 2. Lỗi Không có quyền (403 Forbidden)
        if response.status_code == 403:
            return {
                "error": "PERMISSION_DENIED",
                "details": "Backend từ chối truy cập. Tài khoản không đủ quyền thực hiện hành động này."
            }

        # 3. Các lỗi API khác (400, 404, 500...)
        if response.status_code >= 400:
            print(f"❌ [API Error {response.status_code}]: {response.text}")
            return {"error": f"API_ERROR_{response.status_code}", "details": response.text}

        # 4. Thành công
        try:
            return response.json()
        except:
            return {"status": "success", "message": "Operation completed successfully."}

    def get(self, endpoint):
        """Hàm gọi API GET"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Project-Client] GET {url}")
            response = requests.get(url, headers=self.get_headers())
            return self._handle_response(response)

        except requests.exceptions.RequestException as e:
            print(f"❌ [Connection Error]: {str(e)}")
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def post_multipart(self, endpoint, payload_dict):
        """Hàm gọi API POST Multipart (Tạo dự án)"""
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
                return {"error": "415 Unsupported Media Type. Server Java từ chối format này."}

            return self._handle_response(response)

        except requests.exceptions.RequestException as e:
            print(f"❌ [Connection Error]: {str(e)}")
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def put_multipart(self, endpoint, payload_dict):
        """Hàm gọi API PUT Multipart (Cập nhật dự án)"""
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
                return {"error": "415 Unsupported Media Type. Server Java từ chối format này."}

            return self._handle_response(response)

        except requests.exceptions.RequestException as e:
            print(f"❌ [Connection Error]: {str(e)}")
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def delete(self, endpoint):
        """Hàm gọi API DELETE (Xóa dự án)"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Project-Client] DELETE {url}")
            response = requests.delete(url, headers=self.get_headers(is_multipart=False))

            return self._handle_response(response)

        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

# Singleton instance
api_client = ProjectApiClient()