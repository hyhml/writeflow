"""
Researcher Agent - 素材收集
"""
from typing import Dict, Any, List
from dataclasses import dataclass
from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


@dataclass
class Material:
    """素材条目"""
    material_id: str
    material_type: str  # data/case/theory/history/quote
    content: str
    source: str
    reliability: float  # 0-1
    tags: List[str]
    relevance: float  # 0-1 与主题的相关性


RESEARCHER_SYSTEM_PROMPT = """你是一位资料收集专家，专门为批判性分析文章收集素材。

你的职责：
1. 围绕主题收集多维度素材
2. 确保素材的可靠性和相关性
3. 区分事实性素材和观点性素材
4. 标注素材的潜在偏见来源

收集范围：
- **数据**：统计数字、调查报告、学术研究数据
- **案例**：具体事件、案例分析、历史参照
- **理论**：学术理论、概念框架、批判传统
- **引用**：权威人士言论、经典文献摘录
- **历史**：历史纵深、演变脉络、对比参照

素材评估标准：
- 来源可靠性（权威机构 > 学术文献 > 媒体报道 > 网络资源）
- 内容准确性（是否可验证）
- 相关性（与主题的关联程度）
- 批判性（是否存在固有的立场偏见）

输出格式（JSON）：
{
  "materials": [
    {
      "material_id": "M1",
      "material_type": "data/case/theory/quote/history",
      "content": "素材内容摘要",
      "source": "来源",
      "reliability": 0.8,
      "tags": ["标签1", "标签2"],
      "relevance": 0.7,
      "potential_bias": "可能的偏见来源"
    }
  ],
  "research_summary": "收集概要",
  "key_findings": ["关键发现1", "关键发现2"],
  "research_gaps": ["未找到的素材1", "素材缺口2"]
}"""


class ResearcherAgent(BaseAgent):
    """Researcher Agent - 素材收集专家"""

    def __init__(self, model: str = "claude-opus-4-8", api_key: str = None):
        super().__init__("researcher", model)
        self.client = get_claude_client(api_key)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理素材收集请求

        Args:
            input_data: {
                "task_id": str,
                "topic": str,  # 研究主题
                "keywords": List[str],  # 关键词
                "material_types": List[str],  # 需要的素材类型
                "depth_level": str  # shallow/medium/deep
            }
        """
        topic = input_data.get("topic", "")
        keywords = input_data.get("keywords", [])
        material_types = input_data.get("material_types", ["data", "case", "theory", "quote"])
        depth_level = input_data.get("depth_level", "medium")

        research_prompt = self._build_research_prompt(topic, keywords, material_types, depth_level)

        messages = [{"role": "user", "content": research_prompt}]

        response = await self.client.generate(
            messages=messages,
            system_prompt=RESEARCHER_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.5,
        )

        return self._parse_research_result(response["content"])

    def _build_research_prompt(
        self,
        topic: str,
        keywords: List[str],
        material_types: List[str],
        depth_level: str
    ) -> str:
        """构建研究提示"""
        prompt = f"""请围绕以下主题进行资料收集：

主题：{topic}
关键词：{', '.join(keywords)}
素材类型：{', '.join(material_types)}
研究深度：{depth_level}

请尽可能收集以下类型的素材：
"""

        if "data" in material_types:
            prompt += """
- 相关的统计数据、调查报告、学术研究数据
- 注意数据的来源、时间和可靠性
"""
        if "case" in material_types:
            prompt += """
- 相关的具体案例、事件分析
- 注意案例的典型性和代表性
"""
        if "theory" in material_types:
            prompt += """
- 相关的学术理论、概念框架
- 注意理论的有效性和适用边界
"""
        if "quote" in material_types:
            prompt += """
- 权威人士的重要言论、经典文献摘录
- 注意引用的完整性和上下文
"""
        if "history" in material_types:
            prompt += """
- 历史纵深参照、演变脉络、历史对比
- 注意历史语境的差异
"""

        prompt += """
请对每条素材评估其可靠性和相关性，并标注潜在的偏见来源。
以JSON格式输出收集结果。"""

        return prompt

    def _parse_research_result(self, content: str) -> Dict[str, Any]:
        """解析研究结果"""
        import json
        import re

        # 尝试提取JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 如果JSON解析失败，返回原始内容和解析失败标记
        return {
            "materials": [],
            "raw_content": content,
            "parse_error": "Failed to parse research result",
            "research_summary": content[:500]
        }
