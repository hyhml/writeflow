"""
Agent基类
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import uuid


class BaseAgent(ABC):
    """Agent基类"""

    def __init__(self, name: str, model: str = ""):
        self.name = name
        self.model = model

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理输入并返回结果"""
        pass

    def generate_id(self) -> str:
        """生成唯一ID"""
        return str(uuid.uuid4())


class AgentResponse:
    """Agent响应"""

    def __init__(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.content = content
        self.metadata = metadata or {}
        self.error = error

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "metadata": self.metadata,
            "error": self.error,
        }
