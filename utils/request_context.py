from contextvars import ContextVar

# Biến này sẽ lưu Token riêng biệt cho từng Request
# Mặc định là None
user_token_context: ContextVar[str] = ContextVar("user_token_context", default=None)

def set_user_token(token: str):
    """Đặt token cho request hiện tại"""
    user_token_context.set(token)

def get_user_token():
    """Lấy token của request hiện tại"""
    return user_token_context.get()