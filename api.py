import uvicorn
import shutil
import os
import sys
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

# Fix lỗi import đường dẫn
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import HumanMessage
from orchestrator.graph import app as graph_app
from utils.config import Config
from utils.request_context import set_user_token

# --- CẤU HÌNH ---
UPLOAD_DIR = Path(".temp_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)  # Tạo thư mục lưu file tạm

app = FastAPI(
    title="A2A AI Chatbot API",
    description="API Chatbot hỗ trợ Text & File Upload",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


# --- HELPER: Xử lý logic gọi AI chung ---
async def process_chat(message_content: str, thread_id: str, token: str = None):
    try:
        if token:
            set_user_token(token)
            print(f"🔑 [API] Token received: {token[:10]}...")

        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [HumanMessage(content=message_content)]}

        output = await graph_app.ainvoke(inputs, config=config)
        last_message = output["messages"][-1]

        return {
            "success": True,
            "response": last_message.content,
            "thread_id": thread_id,
            "tool_calls": last_message.tool_calls if hasattr(last_message, 'tool_calls') else None
        }
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# --- ENDPOINT 1: CHAT TEXT (JSON) ---
class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default_session"


@app.post("/api/chat", summary="Chat bằng văn bản")
async def chat_text(
        req: ChatRequest,
        token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    token = token_auth.credentials if token_auth else None
    return await process_chat(req.message, req.thread_id, token)


# --- ENDPOINT 2: CHAT + UPLOAD FILE (MULTIPART) ---
@app.post("/api/chat/upload", summary="Chat kèm Upload File (Excel)")
async def chat_with_file(
        # Nhận file
        file: UploadFile = File(...),
        # Nhận text kèm theo (Dùng Form vì Multipart không nhận JSON body)
        message: str = Form(""),
        thread_id: str = Form("default_session"),
        token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Upload file Excel và xử lý.
    - **file**: Chọn file từ máy tính.
    - **message**: Lời nhắn (VD: "Thêm vào dự án E-Commerce").
    """
    token = token_auth.credentials if token_auth else None

    try:
        # 1. Lưu file xuống ổ cứng
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Lấy đường dẫn tuyệt đối để gửi cho AI
        abs_path = str(file_path.resolve())
        print(f"📂 [API] File saved at: {abs_path}")

        # 2. Tạo prompt hệ thống (giống logic main.py)
        system_msg = f"""
        [SYSTEM EVENT] User vừa upload một file Excel.
        - Đường dẫn file: {abs_path}
        - Lời nhắn của User: "{message}"

        YÊU CẦU:
        1. Dùng tool `create_tasks_from_excel`.
        2. Nếu user đã nói tên dự án trong lời nhắn, dùng nó làm `target_project_name`.
        3. Nếu chưa có, hỏi lại user.
        """

        # 3. Gọi AI
        return await process_chat(system_msg, thread_id, token)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


if __name__ == "__main__":
    print("🚀 Starting Server at http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)