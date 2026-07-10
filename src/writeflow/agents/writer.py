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


WRITER_REVISION_PROMPT = """你是一位批判性思维作家，现在需要直接修订文章正文。

你的任务不是解释你如何回应质疑，也不是输出辩护清单，而是把 Judge 和 Devil Advocate 指出的真实问题吸收到文章里，直接交付一篇更强的完整文章。

【修订原则】
1. 优先解决 Judge 标出的浅度问题：概念克制、句子必要性、层次穿透、方案具体性。
2. 优先回答 depth_questions 中 status 为 missing 或 not_deep_enough 的具体追问。
3. 如果 Devil Advocate 的质疑成立，把它转化为正文中的更强论证或更具体证据。
4. 如果质疑不成立，也不要写“我不同意”，而是在正文中用更清楚的推理消解它。
5. 保持 Thesis Architect 的 core_claim，不要把文章改成折中综述。

【禁止】
- 不要输出修改说明。
- 不要输出辩护清单。
- 不要说“我会如何修改”。
- 不要用新增术语遮盖原本的浅度问题。

直接输出修订后的完整文章正文。"""


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
                "mode": "write" | "revision" | "defense",
                "topic": str,  # 写作主题
                "materials": List[dict],  # 素材（来自Researcher）
                "previous_rounds": List[dict],  # 前几轮迭代
                "rewrite_feedback": dict,  # Judge退回重写意见（write模式）
                "content": str,  # 文章内容（revision/defense模式）
                "criticisms": List[dict],  # 质疑列表（revision/defense模式）
                "judge_feedback": dict,  # 判浅结果（revision模式）
            }
        """
        mode = input_data.get("mode", "write")

        if mode == "revision":
            return await self._revise(input_data)
        if mode == "defense":
            return await self._defend(input_data)
        return await self._write(input_data)

    async def _write(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """生成批判性文章"""
        topic = input_data.get("topic", "")
        materials = input_data.get("materials", [])
        thesis = input_data.get("thesis", {})
        observation_brief = input_data.get("observation_brief", {})
        local_voice_brief = input_data.get("local_voice_brief", {})
        novelty_assets = input_data.get("novelty_assets", [])
        depth_questions = input_data.get("depth_questions", [])
        previous_rounds = input_data.get("previous_rounds", [])
        rewrite_feedback = input_data.get("rewrite_feedback", {})

        writing_prompt = self._build_writing_prompt(
            topic=topic,
            thesis=thesis,
            materials=materials,
            observation_brief=observation_brief,
            local_voice_brief=local_voice_brief,
            novelty_assets=novelty_assets,
            depth_questions=depth_questions,
            previous_rounds=previous_rounds,
            rewrite_feedback=rewrite_feedback,
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
        observation_brief: dict | None = None,
        local_voice_brief: dict | None = None,
        novelty_assets: list | None = None,
        depth_questions: list | None = None,
        rewrite_feedback: dict | None = None,
    ) -> str:
        """Build the drafting prompt around one central argument."""
        materials_context = self._build_materials_context(materials)
        thesis_context = self._build_thesis_context(thesis)
        observation_context = self._build_observation_context(observation_brief or {})
        local_voice_context = self._build_local_voice_context(local_voice_brief or {})
        novelty_context = self._build_novelty_assets_context(novelty_assets or [])
        depth_question_context = self._build_depth_questions_context(depth_questions or [])

        writing_prompt = f"""请围绕以下主题撰写一篇批判性分析文章：

主题：{topic}

{thesis_context}

{observation_context}

{local_voice_context}

{novelty_context}

{depth_question_context}

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
6. novelty_assets 是文章必须守住的真实新意，不要把它们稀释成泛泛而谈。
7. 如果有人类观察或本地声音，必须把它们转化为具体机制、利益冲突和行动方案，而不是装饰性引用。

【禁止】
- 禁止写成“主题综述式”文章。
- 禁止用并列清单覆盖教育、经济、文化、技术等多个层面却每层浅尝辄止。
- 禁止只解释现象，不追问机制、利益分配和代价转移。

直接输出文章全文，不要包含任何解释或元数据。"""

        if rewrite_feedback:
            writing_prompt += self._build_rewrite_feedback_context(rewrite_feedback)

        if previous_rounds:
            writing_prompt += "\n\n=== 前几轮迭代参考 ===\n"
            for prev in previous_rounds[-2:]:
                if prev.get("writer_output"):
                    writing_prompt += f"\n轮次{prev['round']}产出：\n{prev['writer_output'][:500]}...\n"

        return writing_prompt

    async def _revise(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """根据 Judge 和 Devil Advocate 反馈直接修订正文。"""
        topic = input_data.get("topic", "")
        content = input_data.get("content", "")
        materials = input_data.get("materials", [])
        thesis = input_data.get("thesis", {})
        observation_brief = input_data.get("observation_brief", {})
        local_voice_brief = input_data.get("local_voice_brief", {})
        novelty_assets = input_data.get("novelty_assets", [])
        depth_questions = input_data.get("depth_questions", [])
        judge_feedback = input_data.get("judge_feedback", {})
        criticisms = input_data.get("criticisms", [])

        revision_prompt = self._build_revision_prompt(
            topic=topic,
            content=content,
            thesis=thesis,
            materials=materials,
            observation_brief=observation_brief,
            local_voice_brief=local_voice_brief,
            novelty_assets=novelty_assets,
            depth_questions=depth_questions,
            judge_feedback=judge_feedback,
            criticisms=criticisms,
        )

        messages = [{"role": "user", "content": revision_prompt}]

        response = await self.client.generate(
            messages=messages,
            system_prompt=WRITER_REVISION_PROMPT,
            max_tokens=8192,
            temperature=0.6,
        )

        return {
            "content": response["content"],
            "usage": response["usage"],
            "model": self.model,
        }

    def _build_revision_prompt(
        self,
        *,
        topic: str,
        content: str,
        thesis: dict,
        materials: list,
        judge_feedback: dict,
        criticisms: list,
        observation_brief: dict | None = None,
        local_voice_brief: dict | None = None,
        novelty_assets: list | None = None,
        depth_questions: list | None = None,
    ) -> str:
        """Build a direct article-revision prompt."""
        prompt = f"""请直接修订以下文章，输出修订后的完整正文。

主题：{topic}

{self._build_thesis_context(thesis)}

{self._build_observation_context(observation_brief or {})}

{self._build_local_voice_context(local_voice_brief or {})}

{self._build_novelty_assets_context(novelty_assets or [])}

{self._build_depth_questions_context(depth_questions or [])}

【当前正文】
{content}

{self._build_judge_feedback_context(judge_feedback)}
"""

        if criticisms:
            prompt += "\n【Devil Advocate 质疑】\n"
            for index, criticism in enumerate(criticisms, 1):
                if not isinstance(criticism, dict):
                    continue
                question = criticism.get("question", criticism.get("content", ""))
                analysis = criticism.get("analysis", "")
                consequence = criticism.get("consequence", "")
                prompt += f"{index}. {question}\n"
                if analysis:
                    prompt += f"   分析：{analysis}\n"
                if consequence:
                    prompt += f"   后果：{consequence}\n"

        if materials:
            prompt += f"\n{self._build_materials_context(materials)}"

        prompt += """
【修订要求】
1. 直接输出修订后的完整文章，不要输出修改说明或辩护清单。
2. 优先解决 Judge 标出的 failed_dimensions 和 recommendations。
3. 优先回答 depth_questions 中 missing 或 not_deep_enough 的问题。
4. 继续围绕 core_claim 推进，不要改成主题综述。
5. 保留有效的尖锐判断，同时补强机制、获益者、代价和具体例子。
6. 不得削弱 novelty_assets，不得把真实案例、结构或方案新意写成普通套话。
"""
        return prompt

    def _build_rewrite_feedback_context(self, feedback: dict) -> str:
        """Build feedback context for a new draft after precheck failure."""
        return f"""

【上一轮 Judge 判浅退回】
这不是普通续写，而是重写。上一轮初稿没有通过 Depth Judge，请优先修复以下问题：

{self._build_judge_feedback_context(feedback)}

重写时不要解释“我将如何修改”，直接输出新的完整文章。"""

    def _build_judge_feedback_context(self, feedback: dict) -> str:
        """Build a compact Judge feedback block."""
        if not feedback:
            return "【Judge 判浅反馈】\n（暂无判浅反馈。）\n"

        scores = feedback.get("quality_scores", {})
        failed_dimensions = feedback.get("failed_dimensions", [])
        key_issues = feedback.get("key_issues", [])
        recommendations = feedback.get("recommendations", [])
        depth_questions = feedback.get("depth_questions", [])
        pass_reason = feedback.get("pass_reason", feedback.get("reason", ""))

        text = "【Judge 判浅反馈】\n"
        if pass_reason:
            text += f"- 结果：{pass_reason}\n"
        if scores:
            text += "- 评分：\n"
            for dimension, score in scores.items():
                text += f"  - {dimension}: {score}/10\n"
        if failed_dimensions:
            text += "- 未通过维度：\n"
            for dimension in failed_dimensions:
                text += f"  - {dimension}\n"
        if key_issues:
            text += "- 主要问题：\n"
            for issue in key_issues:
                text += f"  - {issue}\n"
        if recommendations:
            text += "- 修改建议：\n"
            for recommendation in recommendations:
                text += f"  - {recommendation}\n"
        if depth_questions:
            text += "- 必须回答的具体追问：\n"
            for question in depth_questions:
                if not isinstance(question, dict):
                    continue
                text += (
                    f"  - [{question.get('target', '')}/"
                    f"{question.get('status', '')}] {question.get('question', '')}\n"
                )
                if question.get("required_revision"):
                    text += f"    修订要求：{question['required_revision']}\n"
        return text

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

    def _build_observation_context(self, observation_brief: dict) -> str:
        """Build human observation context."""
        if not observation_brief:
            return "【人类观察】\n（用户未提供本地观察；不得编造本地经验。）"

        details = observation_brief.get("must_preserve_details", [])
        if isinstance(details, list):
            details_text = "；".join(str(item) for item in details if str(item).strip())
        else:
            details_text = str(details)

        return f"""【人类观察】
- 反常现象：{observation_brief.get("abnormal_phenomenon", "")}
- 案例差异：{observation_brief.get("case_difference", "")}
- 直觉问题根源：{observation_brief.get("intuitive_root_cause", "")}
- 具体解决方案：{observation_brief.get("concrete_solution", "")}
- 不可丢失细节：{details_text}"""

    def _build_local_voice_context(self, local_voice_brief: dict) -> str:
        """Build local voice context."""
        if not local_voice_brief:
            return "【本地真实声音】\n（没有可用本地声音；不得编造引语。）"

        voices = local_voice_brief.get("voices", [])
        if not voices:
            missing = local_voice_brief.get("missing_reason", "没有可用本地声音。")
            return f"【本地真实声音】\n（{missing} 不得编造引语。）"

        text = "【本地真实声音】\n"
        for index, voice in enumerate(voices[:5], 1):
            if not isinstance(voice, dict):
                continue
            quote = voice.get("direct_quote") or voice.get("paraphrase") or ""
            text += (
                f"{index}. {voice.get('speaker_type', 'unknown')} "
                f"@{voice.get('location', '')}: {quote}\n"
            )
            if voice.get("pain_point"):
                text += f"   痛点：{voice['pain_point']}\n"
            if voice.get("local_specificity"):
                text += f"   地方性：{voice['local_specificity']}\n"
        return text.rstrip()

    def _build_novelty_assets_context(self, novelty_assets: list) -> str:
        """Build real novelty asset context."""
        if not novelty_assets:
            return "【真实新意资产】\n（Novelty Gate 尚未提供资产；写作必须主动守住 case/structure/solution 中至少一种新意。）"

        text = "【真实新意资产】\n"
        for index, asset in enumerate(novelty_assets, 1):
            if not isinstance(asset, dict):
                continue
            text += (
                f"{index}. [{asset.get('type', '')}] {asset.get('claim', '')}\n"
                f"   不同之处：{asset.get('why_different', '')}\n"
                f"   证据方向：{asset.get('evidence_hint', '')}\n"
                f"   必须保留：{asset.get('must_preserve', '')}\n"
            )
        return text.rstrip()

    def _build_depth_questions_context(self, depth_questions: list) -> str:
        """Build concrete depth questions for rewrite."""
        if not depth_questions:
            return "【Depth Judge 具体追问】\n（暂无具体追问。）"

        text = "【Depth Judge 具体追问】\n"
        for index, question in enumerate(depth_questions, 1):
            if not isinstance(question, dict):
                continue
            text += (
                f"{index}. [{question.get('target', '')}/"
                f"{question.get('status', '')}] {question.get('question', '')}\n"
            )
            if question.get("why_it_matters"):
                text += f"   为什么重要：{question['why_it_matters']}\n"
            if question.get("required_revision"):
                text += f"   必须修订：{question['required_revision']}\n"
        return text.rstrip()

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
