"""
WriteFLow - Claude Code批判性写作工具

被Claude Code直接调用的Python库，辅助完成意识形态批判、
社会揭露、理论分析类深度稿件的创作。
"""
__version__ = "0.2.3"

from writeflow.writeflow import WriteFlow, WriteResult, QualityScores, DebateSummary, TraceEvent

__all__ = [
    "__version__",
    "WriteFlow",
    "WriteResult",
    "QualityScores",
    "DebateSummary",
    "TraceEvent",
]
