import uvicorn
import shutil
import os
import sys
import asyncio
import traceback
import json  # <--- MỚI: Để parse context string trong upload
from pathlib import Path
from typing import Optional, Union, List, Dict, Any  # <--- MỚI: Thêm Any

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# <--- MỚI: Import SystemMessage để chèn ngữ cảnh
from langchain_core.messages import HumanMessage, SystemMessage
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


# --- HELPER: Xử lý logic chính ---
# 👇 CẬP NHẬT: Thêm tham số context
async def process_chat(message_content: str, thread_id: str, token: str = None, context: Dict[str, Any] = None):
    try:
        # 1. Set Token cho Thread hiện tại
        if token:
            set_user_token(token)
            print(f"🔑 [API] Token received: {token[:10]}...")

        config = {"configurable": {"thread_id": thread_id}}

        # 2. XÂY DỰNG MESSAGE INPUT (Bao gồm Context System Message)
        input_messages = []

        # 👇 LOGIC MỚI: Chèn ngữ cảnh dạng "AUTHENTICATED SYSTEM STATE"
        # Mục tiêu: Ép AI dùng ID có sẵn, CẤM gọi tool tra cứu lại.
        if context:
            print(f"🌍 [Context] Received: {context}")

            # --- BẮT ĐẦU SYSTEM PROMPT MẠNH ---
            context_prompt = "### 🔒 AUTHENTICATED SYSTEM STATE (TRẠNG THÁI ĐÃ XÁC THỰC) ###\n"
            context_prompt += "Hệ thống đã tự động xác thực vị trí của User. Dưới đây là các ID BẮT BUỘC SỬ DỤNG:\n"
            context_prompt += "```json\n"
            context_prompt += "{\n"

            has_context = False

            if context.get('company_id'):
                context_prompt += f'  "company_id": {context["company_id"]},  // ĐÃ XÁC THỰC - KHÔNG CẦN TRA CỨU LẠI\n'
                has_context = True

            if context.get('workspace_id'):
                context_prompt += f'  "workspace_id": {context["workspace_id"]}, // ĐÃ XÁC THỰC - KHÔNG CẦN TRA CỨU LẠI\n'
                has_context = True

            if context.get('project_id'):
                context_prompt += f'  "project_id": {context["project_id"]}    // ĐÃ XÁC THỰC - KHÔNG CẦN TRA CỨU LẠI\n'
                has_context = True

            context_prompt += "}\n"
            context_prompt += "```\n"

            if has_context:
                context_prompt += "\n🚀 **SHORTCUT INSTRUCTION (CHỈ THỊ ĐI TẮT):**\n"
                context_prompt += "1. BẠN ĐÃ CÓ CÁC ID Ở TRÊN (trong khối JSON).\n"
                context_prompt += "2. **BỎ QUA (SKIP)** hoàn toàn bước gọi `get_user_profile`, `get_company_workspaces` hay mapping tên.\n"
                context_prompt += "3. **TRUYỀN THẲNG** các ID này vào tool nghiệp vụ (ví dụ: `create_project`, `create_task`) ngay lập tức.\n"

            # Thêm thông tin trang hiện tại (chỉ để tham khảo)
            if context.get('current_page'):
                context_prompt += f"\n- Current URL: {context['current_page']}\n"

            # Chỉ chèn nếu có ít nhất 1 ID
            if has_context:
                input_messages.append(SystemMessage(content=context_prompt))
            # --- KẾT THÚC SYSTEM PROMPT MẠNH ---

        # 3. Thêm tin nhắn của User
        input_messages.append(HumanMessage(content=message_content))

        print(f"⏳ [API] Đang xử lý (Thread: {thread_id})...")

        # 4. Gọi Graph AI
        inputs = {"messages": input_messages}
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

    # --- BẮT LỖI ---
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
    # 👇 MỚI: Nhận context dictionary từ Frontend
    context: Optional[Dict[str, Any]] = {}


@app.post("/api/chat")
async def chat_text(req: ChatRequest, token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    # 👇 DEBUG REQUEST (Có thể comment lại sau khi test xong)
    # print(f"🛑 [DEBUG REQUEST]: {req.dict()}")

    token = token_auth.credentials if token_auth else None
    # Truyền req.context vào hàm xử lý
    return await process_chat(req.message, req.thread_id, token, req.context)


# --- ENDPOINT 2: UPLOAD FILE ---
@app.post("/api/chat/upload")
async def chat_with_file(
        file: UploadFile = File(...),
        message: str = Form(""),
        thread_id: str = Form("default_session"),
        # 👇 MỚI: Nhận context dạng JSON string từ Form Data
        context: str = Form(default="{}"),
        token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    token = token_auth.credentials if token_auth else None

    # Parse context string thành dict
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
        # Truyền context_dict vào hàm xử lý
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