import sys
import os
import chainlit as cl
from langchain_core.messages import HumanMessage

# 1. Fix lỗi import đường dẫn
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from orchestrator.graph import app
from utils.config import Config


# --- CẤU HÌNH CHAINLIT ---

@cl.on_chat_start
async def start():
    """Hàm chạy 1 lần khi User F5 hoặc mở trang web"""
    try:
        Config.validate()
        status_msg = "Tôi có thể giúp gì cho bạn?"
    except Exception as e:
        status_msg = f"❌ **LỖI KHỞI ĐỘNG:** Không thể kết nối hệ thống. Chi tiết: {str(e)}"

    await cl.Message(content=status_msg).send()
    thread_id = cl.context.session.id
    cl.user_session.set("config", {"configurable": {"thread_id": thread_id}})


@cl.on_message
async def on_message(message: cl.Message):
    """Hàm xử lý mỗi khi User gửi tin nhắn"""

    config = cl.user_session.get("config")

    # ---------------------------------------------------------
    # 1. LOGIC XỬ LÝ FILE UPLOAD (QUAN TRỌNG: LẤY CẢ TEXT CỦA USER)
    # ---------------------------------------------------------
    if message.elements:
        file_element = message.elements[0]

        if "spreadsheet" in file_element.mime or file_element.path.endswith(".xlsx"):
            # Lấy nội dung text user gõ kèm (Ví dụ: "thêm vào dự án A")
            user_text_input = message.content if message.content else ""

            # Ghép thông tin file + lời nhắn của user vào prompt
            user_msg_content = f"""
            [SYSTEM EVENT] User vừa upload một file Excel.
            - Đường dẫn file: {file_element.path}
            - Lời nhắn của User: "{user_text_input}"

            YÊU CẦU CHO AGENT:
            1. Hãy dùng tool `create_tasks_from_excel`.
            2. Kiểm tra kỹ "Lời nhắn của User". Nếu họ đã nói tên dự án (VD: "thêm vào dự án X"), hãy dùng tên đó làm tham số `target_project_name` ngay lập tức.
            3. Nếu lời nhắn trống hoặc không có tên dự án, hãy hỏi lại user.
            """

            await cl.Message(content=f"📂 **Đã nhận file:** `{file_element.name}`. Đang đọc yêu cầu...",
                             author="LY").send()
        else:
            user_msg_content = message.content
    else:
        user_msg_content = message.content

    # ---------------------------------------------------------
    # 2. GỬI INPUT VÀO LANGGRAPH
    # ---------------------------------------------------------
    inputs = {"messages": [HumanMessage(content=user_msg_content)]}
    final_answer_msg = cl.Message(content="", author="LY")

    async for event in app.astream(inputs, config=config):
        for key, value in event.items():

            # --- TRƯỜNG HỢP A: TOOL CHẠY ---
            if key == "project_tools":
                tool_output = value["messages"][0].content
                async with cl.Step(name="Hệ thống Project", type="tool") as step:
                    step.input = "Request sent to Project API..."
                    step.output = tool_output

            elif key == "task_tools":
                tool_output = value["messages"][0].content
                async with cl.Step(name="Hệ thống Task", type="tool") as step:
                    step.input = "Request sent to Task API..."
                    step.output = tool_output

            # --- TRƯỜNG HỢP B: AI SUY NGHĨ ---
            elif key in ["Project_Agent", "Task_Agent"]:
                message_data = value["messages"][0]
                agent_name = "LY (Project)" if key == "Project_Agent" else "LY (Task)"

                if message_data.tool_calls:
                    tool_call = message_data.tool_calls[0]
                    async with cl.Step(name=f"{agent_name} đang nghĩ", type="run") as step:
                        step.input = "Phân tích yêu cầu..."
                        step.output = f"Quyết định gọi: `{tool_call['name']}`\nTham số: {tool_call['args']}"

                elif message_data.content:
                    text_content = ""
                    raw_content = message_data.content
                    if isinstance(raw_content, str):
                        text_content = raw_content
                    elif isinstance(raw_content, list):
                        for item in raw_content:
                            if isinstance(item, str):
                                text_content += item
                            elif isinstance(item, dict) and "text" in item:
                                text_content += item.get("text", "")

                    if text_content:
                        await final_answer_msg.stream_token(text_content)

    if final_answer_msg.content:
        await final_answer_msg.send()