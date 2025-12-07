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

    # --- HÀM XỬ LÝ PHẢN HỒI CHUNG (MỚI THÊM) ---
    def _handle_response(self, response):
        """Xử lý các mã lỗi HTTP để trả về thông báo rõ ràng cho AI"""
        # 1. Lỗi Token hết hạn
        if response.status_code == 401:
            return {"error": "AUTH_ERROR", "details": "Token đã hết hạn hoặc không hợp lệ."}

        # 2. Lỗi Không có quyền (403 Forbidden) -> Quan trọng để AI báo user
        if response.status_code == 403:
            return {
                "error": "PERMISSION_DENIED",
                "details": "Backend từ chối truy cập. Tài khoản không đủ quyền thực hiện hành động này."
            }

        # 3. Các lỗi API khác (400, 404, 500...)
        if response.status_code >= 400:
            print(f"❌ [API Error {response.status_code}]: {response.text}")
            return {"error": f"API_ERROR_{response.status_code}", "details": response.text}

        # 4. Thành công (200, 201, 204)
        try:
            # Nếu backend trả về JSON
            return response.json()
        except:
            # Nếu backend chỉ trả về 200 OK mà không có body (thường gặp ở Delete)
            return {"status": "success", "message": "Operation completed successfully."}

    def get(self, endpoint):
        """Hàm gọi API GET"""
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers()

        try:
            print(f"🔌 [Connecting] GET {url}")
            response = requests.get(url, headers=headers)
            # Gọi hàm xử lý chung
            return self._handle_response(response)

        except requests.exceptions.RequestException as e:
            print(f"❌ [Connection Error]: {str(e)}")
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def post_multipart(self, endpoint, payload_dict):
        """Hàm gọi API POST Multipart"""
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers(is_multipart=True)

        files = {
            'data': (None, json.dumps(payload_dict), 'application/json'),
            'file': (None, bytes(), 'application/octet-stream')
        }

        try:
            print(f"🔌 [Connecting] POST MULTIPART {url}")
            response = requests.post(url, headers=headers, files=files)

            # Giữ logic cũ: Check lỗi 415 riêng
            if response.status_code == 415:
                return {"error": "415 Unsupported Media Type. Server Java từ chối format này."}

            return self._handle_response(response)

        except requests.exceptions.RequestException as e:
            print(f"❌ [Connection Error]: {str(e)}")
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def delete(self, endpoint):
        """Hàm gọi API DELETE"""
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers(is_multipart=False)

        try:
            print(f"🔌 [Project-Client] DELETE {url}")
            response = requests.delete(url, headers=headers)

            return self._handle_response(response)

        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}


# Singleton instance
api_client = ProjectApiClient()