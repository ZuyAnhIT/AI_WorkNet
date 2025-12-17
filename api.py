import uvicorn
import shutil
import os
import sys
import asyncio
import traceback
import json
from pathlib import Path
from typing import Optional, Union, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import HumanMessage, SystemMessage
from orchestrator.graph import app as graph_app
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


# --- HELPER: Xử lý logic chính ---
async def process_chat(message_content: str, thread_id: str, token: str = None, context: Dict[str, Any] = None):
    try:
        # 1. Set Token cho Thread hiện tại
        if token:
            set_user_token(token)
            print(f"🔑 [API] Token received: {token[:10]}...")

        config = {"configurable": {"thread_id": thread_id}}

        # 2. XÂY DỰNG MESSAGE INPUT
        input_messages = []

        # LOGIC CHÈN SYSTEM MESSAGE (Để AI hiểu ngữ cảnh bằng ngôn ngữ tự nhiên)
        if context:
            print(f"🌍 [Context] Received: {context}")

            context_prompt = "### 🔒 AUTHENTICATED SYSTEM STATE (TRẠNG THÁI ĐÃ XÁC THỰC) ###\n"
            context_prompt += "Hệ thống đã tự động xác thực vị trí của User. Dưới đây là các ID BẮT BUỘC SỬ DỤNG:\n"
            context_prompt += "```json\n{\n"

            has_context = False

            if context.get('company_id'):
                context_prompt += f'  "company_id": {context["company_id"]},  // INTEGER - KHÔNG DÙNG STRING\n'
                has_context = True

            if context.get('workspace_id'):
                context_prompt += f'  "workspace_id": {context["workspace_id"]}, // INTEGER - KHÔNG DÙNG STRING\n'
                has_context = True

            if context.get('project_id'):
                context_prompt += f'  "project_id": {context["project_id"]}    // INTEGER - KHÔNG DÙNG STRING\n'
                has_context = True

            context_prompt += "}\n```\n"

            if has_context:
                context_prompt += "\n🚀 **INSTRUCTION:**\n"
                context_prompt += "1. Dùng chính xác các số nguyên (Integer) ở trên khi gọi tool.\n"
                context_prompt += "2. KHÔNG BAO GIỜ dùng chuỗi như 'company_id' làm giá trị.\n"

            if context.get('current_page'):
                context_prompt += f"\n- Current URL: {context['current_page']}\n"

            if has_context:
                input_messages.append(SystemMessage(content=context_prompt))

        # 3. Thêm tin nhắn của User
        input_messages.append(HumanMessage(content=message_content))

        print(f"⏳ [API] Đang xử lý (Thread: {thread_id})...")

        # 4. GỌI GRAPH AI
        # 👇 [SỬA QUAN TRỌNG Ở ĐÂY]: Phải truyền "user_context" vào input để Graph nhận được
        inputs = {
            "messages": input_messages,
            "user_context": context if context else {}  # <--- DÒNG NÀY GIÚP SỬA LỖI 400
        }

        output = await asyncio.wait_for(graph_app.ainvoke(inputs, config=config), timeout=120.0)

        last_message = output["messages"][-1]

        # 5. Chuẩn hóa output
        final_text = normalize_ai_response(last_message.content)

        print("✅ [API] Xử lý xong.")

        return {
            "success": True,
            "response": final_text,
            "thread_id": thread_id,
            "tool_calls": last_message.tool_calls if hasattr(last_message, 'tool_calls') else None
        }

    except Exception as e:
        error_log = str(e).lower()
        print(f"❌ [API Error Log]: {str(e)}")
        traceback.print_exc()

        friendly_message = "Hệ thống đang bận xử lý, bạn vui lòng thử lại sau giây lát nhé."

        if "429" in error_log or "resource_exhausted" in error_log:
            friendly_message = "⚠️ Hệ thống đang tạm hết hạn mức miễn phí trong ngày."
        elif "503" in error_log or "overloaded" in error_log:
            friendly_message = "⚠️ Máy chủ AI đang quá tải. Hãy đợi 1 phút rồi nhắn lại nhé."
        elif "timeout" in error_log:
            friendly_message = "⏱️ AI suy nghĩ hơi lâu nên bị ngắt kết nối. Bạn hãy thử lại."

        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "response": friendly_message,
                "thread_id": thread_id
            }
        )


# --- ENDPOINT 1: CHAT TEXT ---
class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default_session"
    context: Optional[Dict[str, Any]] = {}


@app.post("/api/chat")
async def chat_text(req: ChatRequest, token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    token = token_auth.credentials if token_auth else None
    return await process_chat(req.message, req.thread_id, token, req.context)


# --- ENDPOINT 2: UPLOAD FILE ---
@app.post("/api/chat/upload")
async def chat_with_file(
        file: UploadFile = File(...),
        message: str = Form(""),
        thread_id: str = Form("default_session"),
        context: str = Form(default="{}"),
        token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    token = token_auth.credentials if token_auth else None

    try:
        context_dict = json.loads(context)
    except:
        context_dict = {}

    try:
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        system_msg = f"""
        [SYSTEM EVENT] User vừa upload file Excel.
        - Đường dẫn: {str(file_path.resolve())}
        - Lời nhắn: "{message}"
        YÊU CẦU: Dùng tool create_tasks_from_excel. Lấy tên dự án từ lời nhắn hoặc Context ID.
        """
        return await process_chat(system_msg, thread_id, token, context_dict)
    except Exception as e:
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