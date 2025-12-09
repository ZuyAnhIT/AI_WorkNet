import uvicorn
import shutil
import os
import sys
import asyncio
import traceback
from pathlib import Path
from typing import Optional, Union, List, Dict

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import HumanMessage
from orchestrator.graph import app as graph_app
from utils.config import Config
from utils.request_context import set_user_token

# --- CẤU HÌNH ---
UPLOAD_DIR = Path(".temp_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="A2A AI Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "message": "Dữ liệu không đúng định dạng."},
    )


# --- HÀM MỚI: CHUẨN HÓA NỘI DUNG AI ---
def normalize_ai_response(content: Union[str, List[Union[str, Dict]]]) -> str:
    """
    Chuyển đổi mọi định dạng trả về của LangChain/Gemini thành chuỗi String duy nhất.
    Giúp Frontend không bị lỗi khi nhận được List thay vì String.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                text_parts.append(item["text"])
        return "".join(text_parts)

    return str(content)


# --- HELPER: Xử lý logic chính (Đã thêm Try-Catch Bọc Đường) ---
async def process_chat(message_content: str, thread_id: str, token: str = None):
    try:
        # --- LOGIC XỬ LÝ CHÍNH ---
        if token:
            set_user_token(token)
            print(f"🔑 [API] Token received: {token[:10]}...")

        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [HumanMessage(content=message_content)]}

        print(f"⏳ [API] Đang xử lý (Thread: {thread_id})...")

        # Timeout 120s
        output = await asyncio.wait_for(graph_app.ainvoke(inputs, config=config), timeout=120.0)

        last_message = output["messages"][-1]

        # Chuẩn hóa output
        final_text = normalize_ai_response(last_message.content)

        print("✅ [API] Xử lý xong.")

        return {
            "success": True,
            "response": final_text,  # Luôn là String Markdown
            "thread_id": thread_id,
            "tool_calls": last_message.tool_calls if hasattr(last_message, 'tool_calls') else None
        }

    # --- BẮT LỖI VÀ TRẢ VỀ THÔNG BÁO THÂN THIỆN ---
    except Exception as e:
        # 1. In lỗi chi tiết ra Terminal để Dev sửa
        error_log = str(e).lower()
        print(f"❌ [API Error Log]: {str(e)}")
        traceback.print_exc()

        # 2. Chọn câu thông báo cho người dùng
        friendly_message = "Hệ thống đang bận xử lý, bạn vui lòng thử lại sau giây lát nhé."

        if "429" in error_log or "resource_exhausted" in error_log:
            friendly_message = "⚠️ Hệ thống đang tạm hết hạn mức miễn phí trong ngày. Bạn vui lòng quay lại sau hoặc liên hệ quản trị viên để nâng cấp."

        elif "503" in error_log or "overloaded" in error_log or "unavailable" in error_log:
            friendly_message = "⚠️ Máy chủ AI đang quá tải do nhiều người dùng cùng lúc. Bạn hãy đợi khoảng 1 phút rồi nhắn lại nhé."

        elif "404" in error_log or "not_found" in error_log:
            friendly_message = "🛠️ Tính năng AI này đang được bảo trì để nâng cấp. Vui lòng thử lại sau."

        elif "403" in error_log or "permission_denied" in error_log:
            friendly_message = "🔒 Hệ thống gặp sự cố xác thực kết nối. Vui lòng báo cho kỹ thuật viên."

        elif "timeout" in error_log:
            friendly_message = "⏱️ AI suy nghĩ hơi lâu nên bị ngắt kết nối. Bạn hãy thử hỏi lại câu ngắn hơn xem sao."

        elif "list" in error_log and "strip" in error_log:
            friendly_message = "⚠️ Lỗi cấu hình nội bộ. Vui lòng báo Admin kiểm tra file cấu hình."

        # 3. TRẢ VỀ JSON 200 OK (Để giao diện không báo lỗi đỏ)
        # Frontend sẽ hiển thị 'friendly_message' như một tin nhắn bình thường của Bot
        return JSONResponse(
            status_code=200,
            content={
                "success": False,  # Đánh dấu là false nhưng vẫn trả về 200
                "response": friendly_message,
                "thread_id": thread_id
            }
        )


# --- ENDPOINT 1: CHAT TEXT ---
class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default_session"


@app.post("/api/chat")
async def chat_text(req: ChatRequest, token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    token = token_auth.credentials if token_auth else None
    return await process_chat(req.message, req.thread_id, token)


# --- ENDPOINT 2: UPLOAD FILE ---
@app.post("/api/chat/upload")
async def chat_with_file(
        file: UploadFile = File(...),
        message: str = Form(""),
        thread_id: str = Form("default_session"),
        token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    token = token_auth.credentials if token_auth else None
    try:
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        system_msg = f"""
        [SYSTEM EVENT] User vừa upload file Excel.
        - Đường dẫn: {str(file_path.resolve())}
        - Lời nhắn: "{message}"
        YÊU CẦU: Dùng tool create_tasks_from_excel. Lấy tên dự án từ lời nhắn.
        """
        return await process_chat(system_msg, thread_id, token)
    except Exception as e:
        # Nếu lỗi ngay khâu upload file (chưa vào process_chat)
        print(f"❌ [Upload Error]: {str(e)}")
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "response": "⚠️ Lỗi khi tải file lên. Vui lòng kiểm tra lại file của bạn."
            }
        )


# --- HEALTH CHECK ---
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "A2A AI Agent"}


if __name__ == "__main__":
    print("🚀 Starting Server at http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)