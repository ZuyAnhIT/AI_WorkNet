import operator
from typing import Annotated, List, TypedDict
from langchain_core.messages import BaseMessage


# Định nghĩa cấu trúc dữ liệu được truyền qua lại giữa các Node
class AgentState(TypedDict):
    # Danh sách tin nhắn (Lịch sử chat + Tool output)
    # operator.add nghĩa là: tin nhắn mới sẽ nối đuôi tin nhắn cũ
    messages: Annotated[List[BaseMessage], operator.add]

    # Biến xác định node tiếp theo sẽ chạy
    next: str