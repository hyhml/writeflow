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
        thesis = input_data.get("thesis", {})
        previous_rounds = input_data.get("previous_rounds", [])

        writing_prompt = self._build_writing_prompt(
            topic=topic,
            thesis=thesis,
            materials=materials,
            previous_rounds=previous_rounds,
        )

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

    def _build_writing_prompt(
        self,
        *,
        topic: str,
        thesis: dict,
        materials: list,
        previous_rounds: list,
    ) -> str:
        """Build the drafting prompt around one central argument."""
        materials_context = self._build_materials_context(materials)
        thesis_context = self._build_thesis_context(thesis)

        writing_prompt = f"""请围绕以下主题撰写一篇批判性分析文章：

主题：{topic}

{thesis_context}

{materials_context}

【主轴推进任务】
你的任务不是写一篇主题综述，也不是完整覆盖这个题目的所有层面。
你的任务是围绕 Thesis Architect 的 core_claim 沿一个主轴推进：少写几个层面，但每一层都要深入。

【写作要求】
1. 全文必须围绕 core_claim 展开，每个小节都服务于证明或检验这个核心判断。
2. 不要为了显得全面而铺开多个浅层段落；宁可少写层面，也要把一个机制讲透。
3. 每个主要分析层面都必须回答五个问题：
   - 这个现象背后的机制是什么？
   - 谁从中获益？
   - 谁承担代价？
   - 为什么常见解释是错的？
   - 这个判断能不能被具体例子证明？
4. 揭示被掩盖的深层结构，挑战至少一个主流假设。
5. 提供有证据支撑但允许反驳的论证，保持文章的锋利度和思想张力。

【禁止】
- 禁止写成“主题综述式”文章。
- 禁止用并列清单覆盖教育、经济、文化、技术等多个层面却每层浅尝辄止。
- 禁止只解释现象，不追问机制、利益分配和代价转移。

直接输出文章全文，不要包含任何解释或元数据。"""

        if previous_rounds:
            writing_prompt += "\n\n=== 前几轮迭代参考 ===\n"
            for prev in previous_rounds[-2:]:
                if prev.get("writer_output"):
                    writing_prompt += f"\n轮次{prev['round']}产出：\n{prev['writer_output'][:500]}...\n"

        return writing_prompt

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

    def _build_thesis_context(self, thesis: dict) -> str:
        """Build the Thesis Architect context for drafting."""
        if not thesis:
            return "【核心判断简报】\n（无核心判断简报，请自行提出一个可争辩的核心判断。）"

        return f"""【核心判断简报】
- 核心判断：{thesis.get("core_claim", "")}
- 与普通观点的冲突：{thesis.get("conflict_with_common_view", "")}
- 将推翻的常识：{thesis.get("common_sense_overturned", "")}
- 最强证据：{thesis.get("strongest_evidence", "")}
- 最危险的反驳：{thesis.get("most_dangerous_counterargument", "")}"""

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
