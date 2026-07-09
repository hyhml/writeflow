"""
Writer Agent - 批判性写作
"""
from typing import Dict, Any, Optional
from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


WRITER_SYSTEM_PROMPT = """你是一位批判性思维作家，专门从事意识形态批判、社会分析和理论研究。

【核心原则】
1. 你的文章目的是"迫使思考"，而非"提供答案"
2. 每提出一个论点，必须同时呈现其内在矛盾
3. 挑战权威是职责，不是风险
4. 宁可观点偏激引发争论，不可立场模糊两边讨好

【写作要求】
- 开篇必须直面核心矛盾，不回避
- 论证过程：假设→证据→反驳→再反驳
- 主动预判反对意见并正面回应
- 结论留有开放性，承认复杂性

【禁止】
- 充当"解释者"为现状找理由
- 使用"虽然...但是..."的妥协句式美化主流
- 以"客观"为名回避价值判断
- 堆砌学术术语制造深刻假象

【深度自检清单】
□ 我是否只是描述了"是什么"而没有追问"为什么是这样而不是那样"？
□ 我是否揭示了表面现象背后的利益结构或权力关系？
□ 我的论证是否依赖于一个未声明的隐含前提？
□ 如果我的核心观点被推翻，代价是什么——谁会受损？
□ 我是否区分了"事实描述"和"价值判断"？
□ 我的批判是否有建设性出口，还是仅为破坏而破坏？"""


WRITER_DEFENSE_PROMPT = """你是一位批判性思维作家，现在需要为你的文章进行辩护。

当你收到针对你文章的质疑时：
1. 认真分析每条质疑，确认其是否合理
2. 如果质疑合理，承认并说明你将如何改进
3. 如果质疑不合理，提供具体的反驳依据
4. 重点关注：论点的前提、论证的逻辑、证据的选取

回复格式：
- 质疑: [原质疑内容]
- 回应: [你的回应]
- 动作: [承认/反驳] + [改进说明或反驳依据]"""


class WriterAgent(BaseAgent):
    """Writer Agent - 批判性写作专家"""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.client = get_claude_client(api_key=api_key, model=model)
        super().__init__("writer", self.client.model)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理写作请求

        Args:
            input_data: {
                "task_id": str,
                "round": int,
                "mode": "write" | "defense",
                "topic": str,  # 写作主题
                "materials": List[dict],  # 素材（来自Researcher）
                "previous_rounds": List[dict],  # 前几轮迭代
                "content": str,  # 文章内容（defense模式）
                "criticisms": List[dict],  # 质疑列表（defense模式）
            }
        """
        mode = input_data.get("mode", "write")

        if mode == "defense":
            return await self._defend(input_data)
        else:
            return await self._write(input_data)

    async def _write(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成批判性文章"""
        topic = input_data.get("topic", "")
        materials = input_data.get("materials", [])
        previous_rounds = input_data.get("previous_rounds", [])

        # 构建素材上下文
        materials_context = self._build_materials_context(materials)

        # 构建写作提示
        writing_prompt = f"""请围绕以下主题撰写一篇批判性分析文章：

主题：{topic}

{materials_context}

【写作要求】
1. 揭示被掩盖的深层结构
2. 挑战至少一个主流假设
3. 提供有证据支撑但允许反驳的论证
4. 保持文章的锋利度和思想张力

直接输出文章全文，不要包含任何解释或元数据。"""

        # 加入前几轮的反馈
        if previous_rounds:
            writing_prompt += "\n\n=== 前几轮迭代参考 ===\n"
            for prev in previous_rounds[-2:]:
                if prev.get("writer_output"):
                    writing_prompt += f"\n轮次{prev['round']}产出：\n{prev['writer_output'][:500]}...\n"

        messages = [{"role": "user", "content": writing_prompt}]

        response = await self.client.generate(
            messages=messages,
            system_prompt=WRITER_SYSTEM_PROMPT,
            max_tokens=8192,
            temperature=0.7,
        )

        return {
            "content": response["content"],
            "usage": response["usage"],
            "model": self.model,
        }

    async def _defend(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """为文章辩护"""
        content = input_data.get("content", "")
        criticisms = input_data.get("criticisms", [])

        defense_request = f"请为以下文章进行辩护，回应针对文章的质疑：\n\n文章内容：\n{content}\n\n"

        if criticisms:
            defense_request += "\n针对文章的质疑：\n"
            for i, c in enumerate(criticisms, 1):
                if isinstance(c, dict):
                    defense_request += f"\n质疑{i}：{c.get('question', c.get('content', ''))}"
                    if c.get("basis"):
                        defense_request += f"\n依据：{c['basis']}"
                    if c.get("consequence"):
                        defense_request += f"\n后果：{c['consequence']}"

        defense_request += "\n\n请逐一回应这些质疑。"

        messages = [{"role": "user", "content": defense_request}]

        response = await self.client.generate(
            messages=messages,
            system_prompt=WRITER_DEFENSE_PROMPT,
            max_tokens=4096,
            temperature=0.5,
        )

        return {
            "content": response["content"],
            "usage": response["usage"],
            "model": self.model,
        }

    def _build_materials_context(self, materials: list) -> str:
        """构建素材上下文"""
        if not materials:
            return "（无素材，请基于主题独立思考创作）"

        context = "【参考素材】\n\n"

        # 按类型分组
        by_type = {}
        for m in materials:
            m_type = m.get("material_type", "unknown")
            if m_type not in by_type:
                by_type[m_type] = []
            by_type[m_type].append(m)

        for m_type, items in by_type.items():
            context += f"【{m_type.upper()}】\n"
            for item in items[:5]:  # 每类型最多5条
                context += f"- {item.get('content', '')} (来源: {item.get('source', '未知')})\n"
            context += "\n"

        return context
