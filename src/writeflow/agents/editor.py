"""
Editor Agent - 编辑打磨
"""
from typing import Dict, Any, Optional
from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


EDITOR_SYSTEM_PROMPT = """你是一位批判性文章的编辑，你的职责不是让文章"更易读"或"更安全"，而是确保文章：

1. 保持了清晰的核心判断
2. 删除了所有自我保护的妥协
3. 强化了机制、获益者、代价和具体证据
4. 弱化了可能分散注意力的边缘内容
5. 只做表达清理、结构顺滑和冗余删除，不重写文章立场

【编辑原则】
- 砍掉所有"虽然有争议但..."类型的废话
- 将模糊的"有人认为"改为明确的"XX理论/利益集团/意识形态"
- 删除无法支撑论点的华丽修辞
- 强化那些让你的编辑心跳加速的"危险段落"
- 不得削弱 Thesis Architect 的 core_claim
- 不得把尖锐判断改成折中综述

【锋利度检测】
检查以下软化信号并修正：
- "在一定程度上" → 删除或改为"正是因为"
- "任何事物都有两面性" → 删除
- "客观地说" → 改为"我的论据显示"
- "这也提醒我们" → 改为直接陈述
- "虽然...但是..." → 删除前半部分

【最终检查】
- 文章的第一个论点是否让人感到不适但无法反驳？
- 删掉最后一段"总结"后文章是否反而更有力？
- 如果主流媒体要转载，他们会最想删哪一段？那一段必须保留。

【禁止】
- 不要为了"易读"而稀释核心判断
- 不要添加"两面性"的和稀泥表述
- 不要添加安慰性的"希望"结尾"""


class EditorAgent(BaseAgent):
    """Editor Agent - 编辑打磨专家"""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.client = get_claude_client(api_key=api_key, model=model)
        super().__init__("editor", self.client.model)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理编辑请求

        Args:
            input_data: {
                "task_id": str,
                "content": str,  # 文章内容
                "quality_scores": Dict[str, float],  # 判浅评分
                "key_issues": List[str],  # 主要问题
                "criticisms": List[dict],  # 质疑列表
            }
        """
        content = input_data.get("content", "")
        quality_scores = input_data.get("quality_scores", {})
        key_issues = input_data.get("key_issues", [])
        criticisms = input_data.get("criticisms", [])
        thesis = input_data.get("thesis", {})
        observation_brief = input_data.get("observation_brief", {})
        human_interventions = input_data.get("human_interventions", [])

        edit_prompt = self._build_edit_prompt(
            content,
            quality_scores,
            key_issues,
            criticisms,
            thesis,
            observation_brief,
            human_interventions,
        )

        messages = [{"role": "user", "content": edit_prompt}]

        response = await self.client.generate(
            messages=messages,
            system_prompt=EDITOR_SYSTEM_PROMPT,
            max_tokens=8192,
            temperature=0.5,
        )

        return {
            "content": response["content"],
            "usage": response["usage"],
            "model": self.model,
        }

    def _build_edit_prompt(
        self,
        content: str,
        quality_scores: Dict[str, float],
        key_issues: list,
        criticisms: list,
        thesis: dict | None = None,
        observation_brief: dict | None = None,
        human_interventions: list | None = None,
    ) -> str:
        """构建编辑提示"""
        prompt = f"""请对以下批判性文章进行最终编辑打磨：

【当前版本】
{content}

【不可削弱的核心判断】
{(thesis or {}).get("core_claim", "")}

【不可删除的人类观察与写作要求】
{observation_brief or {}}

【运行中人工补充】
{human_interventions or []}

【判浅评分】
"""
        for dim, score in quality_scores.items():
            prompt += f"- {dim}: {score}/10\n"

        if key_issues:
            prompt += "\n【需要解决的主要问题】\n"
            for issue in key_issues:
                prompt += f"- {issue}\n"

        if criticisms:
            prompt += "\n【仍需回应的质疑】\n"
            for c in criticisms[:3]:
                prompt += f"- {c.get('question', c.get('content', ''))}\n"

        prompt += """
【编辑要求】
1. 只做表达清理、结构顺滑和冗余删除
2. 保持文章的核心判断，不要稀释
3. 不得把尖锐判断改成折中综述
4. 删除所有自我保护的妥协表述
5. 强化机制、获益者、代价和具体证据
6. 不得删除、改写或抹平“不可删除的人类观察与写作要求”中的原始方向和语气

直接输出编辑后的文章全文。"""

        return prompt
