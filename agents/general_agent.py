from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.llm_factory import get_llm
from orchestrator.prompts import GENERAL_AGENT_SYSTEM_PROMPT


def create_general_agent():
    # Dùng nhiệt độ 0.5 để nói chuyện tự nhiên, bớt máy móc
    llm = get_llm(temperature=0.5)

    # General Agent không cần tools, chỉ cần biết nói chuyện
    prompt = ChatPromptTemplate.from_messages([
        ("system", GENERAL_AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    agent = prompt | llm
    return agent