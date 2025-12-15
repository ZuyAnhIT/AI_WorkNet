import requests
import json
from utils.config import Config
# Import hàm lấy token động từ context (để hỗ trợ Multi-User/Multi-Thread)
from utils.request_context import get_user_token


class ProjectApiClient:
    def __init__(self):
        self.base_url = Config.JAVA_BASE_URL

    def get_token(self):
        """
        Lấy Token ưu tiên từ Context (Request hiện tại)
        Nếu không có (chạy local/test), lấy từ .env
        """
        dynamic_token = get_user_token()
        if dynamic_token:
            return dynamic_token
        return Config.JAVA_ACCESS_TOKEN

    def get_headers(self, is_multipart=False):
        """
        Tạo Header.
        Lưu ý: Nếu là Multipart, KHÔNG được set Content-Type thủ công.
        """
        token = self.get_token()
        headers = {
            "Authorization": f"Bearer {token}",
        }
        if not is_multipart:
            headers["Content-Type"] = "application/json"
        return headers

    def _handle_response(self, response):
        """Hàm xử lý phản hồi chung cho toàn bộ hệ thống"""
        # 1. Lỗi Auth
        if response.status_code == 401:
            return {"error": "AUTH_ERROR", "details": "Token không hợp lệ hoặc đã hết hạn."}
        if response.status_code == 403:
            return {"error": "PERMISSION_DENIED", "details": "Bạn không có quyền thực hiện hành động này."}

        # 2. Lỗi Backend (400, 404, 500...)
        if response.status_code >= 400:
            print(f"❌ [API Error {response.status_code}]: {response.text}")
            try:
                error_body = response.json()
                # Trả về chi tiết lỗi nếu Backend gửi JSON
                return {
                    "error": f"API_ERROR_{response.status_code}",
                    "details": error_body.get("detail") or error_body.get("message") or error_body
                }
            except:
                return {"error": f"API_ERROR_{response.status_code}", "details": response.text}

        # 3. Thành công (200, 201)
        try:
            return response.json()
        except:
            return {"status": "success", "message": "Operation completed."}

    # =========================================================================
    # CÁC METHOD CƠ BẢN (GET, POST, PUT, DELETE)
    # =========================================================================

    def get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Client] GET {url}")
            response = requests.get(url, headers=self.get_headers())
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def post(self, endpoint, payload_dict):
        """Gửi POST dạng JSON (Dùng cho các API chuẩn)"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Client] POST (JSON) {url}")
            response = requests.post(url, headers=self.get_headers(), json=payload_dict)
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def put(self, endpoint, payload_dict):
        """Gửi PUT dạng JSON"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Client] PUT (JSON) {url}")
            response = requests.put(url, headers=self.get_headers(), json=payload_dict)
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def patch(self, endpoint, payload_dict):
        """Gửi PATCH dạng JSON"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Client] PATCH (JSON) {url}")
            response = requests.patch(url, headers=self.get_headers(), json=payload_dict)
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    def delete(self, endpoint):
        """Gửi DELETE"""
        url = f"{self.base_url}{endpoint}"
        try:
            print(f"🔌 [Client] DELETE {url}")
            response = requests.delete(url, headers=self.get_headers())
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}

    # =========================================================================
    # MULTIPART METHODS (QUAN TRỌNG ĐỂ FIX LỖI 415)
    # =========================================================================

    def post_multipart(self, endpoint, payload_dict, file_path=None):
        """
        Tự động đóng gói Dictionary thành Multipart Form Data.
        - payload_dict -> JSON String -> Part 'data'
        - file_path -> File Binary -> Part 'file'
        """
        url = f"{self.base_url}{endpoint}"
        headers = self.get_headers(is_multipart=True)  # Không set Content-Type JSON

        # Chuẩn bị files cho requests
        # Part 'data': Backend yêu cầu @RequestPart("data")
        files = {
            'data': (None, json.dumps(payload_dict, ensure_ascii=False), 'application/json')
        }

        # Part 'file' (Optional)
        if file_path:
            try:
                files['file'] = ('upload.jpg', open(file_path, 'rb'), 'application/octet-stream')
            except FileNotFoundError:
                print(f"⚠️ Không tìm thấy file: {file_path}")

        try:
            print(f"🔌 [Client] POST MULTIPART {url}")
            response = requests.post(url, headers=headers, files=files)

            if response.status_code == 415:
                return {"error": "415 Unsupported Media Type (Backend config mismatch)"}

            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            return {"error": "CONNECTION_ERROR", "details": str(e)}


# Singleton instance để import ở các nơi khác
api_client = ProjectApiClient()