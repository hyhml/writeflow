"""
Agent模块
"""
from writeflow.agents.base import BaseAgent, AgentResponse
from writeflow.agents.researcher import ResearcherAgent
from writeflow.agents.thesis_architect import ThesisArchitectAgent
from writeflow.agents.writer import WriterAgent
from writeflow.agents.devil_advocate import DevilAdvocateAgent
from writeflow.agents.judge import JudgeAgent
from writeflow.agents.editor import EditorAgent

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "ResearcherAgent",
    "ThesisArchitectAgent",
    "WriterAgent",
    "DevilAdvocateAgent",
    "JudgeAgent",
    "EditorAgent",
]
