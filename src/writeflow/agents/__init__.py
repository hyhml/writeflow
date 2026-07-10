"""
Agent模块
"""
from writeflow.agents.base import BaseAgent, AgentResponse
from writeflow.agents.observation_interviewer import ObservationInterviewerAgent
from writeflow.agents.local_voice_collector import LocalVoiceCollectorAgent
from writeflow.agents.researcher import ResearcherAgent
from writeflow.agents.thesis_architect import ThesisArchitectAgent
from writeflow.agents.real_novelty_gate import RealNoveltyGateAgent
from writeflow.agents.writer import WriterAgent
from writeflow.agents.devil_advocate import DevilAdvocateAgent
from writeflow.agents.judge import JudgeAgent
from writeflow.agents.editor import EditorAgent

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "ObservationInterviewerAgent",
    "LocalVoiceCollectorAgent",
    "ResearcherAgent",
    "ThesisArchitectAgent",
    "RealNoveltyGateAgent",
    "WriterAgent",
    "DevilAdvocateAgent",
    "JudgeAgent",
    "EditorAgent",
]
