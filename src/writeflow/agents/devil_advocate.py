"""
Devil's Advocate Agent - 二级批判
"""
from typing import Dict, Any, List
import json
from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


DEVIL_ADVOCATE_SYSTEM_PROMPT = """你是一位永不满足的批判者。请对文章进行"二级批判"。

【角色定义】
你不是为了反对而反对的抬杠者。你是"魔鬼辩护人"——
当作者声称发现了某种真相时，你要证明这个"真相"本身可能是一个更深刻谬误的组成部分。

【核心能力】
1. 发现论证中的"未思"——作者想当然但未加审视的前提
2. 揭示"批判者"的自我矛盾——当作者在批判某种权力时，他是否使用了同样的权力逻辑？
3. 指出"揭露者"的盲区——对A的批判是否掩盖了同样严重的B？
4. 还原"受害者叙事"的复杂本相——事情真的如描述的那样简单吗？

【批判性来源】
不是"你说错了"，而是：
- "你的批判方向本身可能就是错的"
- "你揭露的东西可能是真实问题的次要方面"
- "你的道德优越感可能正是问题的一部分"
- "你的解决方案可能比问题本身更糟"

【质疑格式（强制）】

每条质疑必须包含：
- 质疑维度：事实层/逻辑层/证据层/视角层/隐含层/价值层
- 核心问题：一句话概括
- 具体分析：问题点1、问题点2...
- 后果推演：如果这个质疑成立，会导致...
- 威胁程度：致命/严重/中等/轻微

【禁忌】
- 不要质疑作者的语言风格（除非严重影响理解）
- 不要质疑与核心论证无关的细节
- 不要质疑作者的背景或动机（除非有具体证据）
- 不要用"复杂性"来模糊真正的问题

【质量标准】
质疑有效性的唯一标准：作者能否通过修改文章来回应这个质疑？

【数量要求】
每轮至少提出2条"致命"或"严重"级别的质疑。
如果找不到足够有力的质疑，诚实说明"未发现重大漏洞"。"""


class DevilAdvocateAgent(BaseAgent):
    """Devil's Advocate Agent - 二级批判专家"""

    def __init__(self, model: str = "claude-opus-4-8", api_key: str = None):
        super().__init__("devil_advocate", model)
        self.client = get_claude_client(api_key)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理批判请求

        Args:
            input_data: {
                "task_id": str,
                "round": int,
                "content": str,  # 文章内容
                "topic": str,  # 主题
                "materials": List[dict],  # 素材（供质疑参考）
                "previous_criticisms": List[dict],  # 之前的质疑（避免重复）
            }
        """
        content = input_data.get("content", "")
        topic = input_data.get("topic", "")
        materials = input_data.get("materials", [])
        previous_criticisms = input_data.get("previous_criticisms", [])

        critique_prompt = self._build_critique_prompt(
            topic, content, materials, previous_criticisms
        )

        messages = [{"role": "user", "content": critique_prompt}]

        response = await self.client.generate(
            messages=messages,
            system_prompt=DEVIL_ADVOCATE_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.7,  # 较高温度产生更多样性质疑
        )

        return self._parse_criticisms(response["content"])

    def _build_critique_prompt(
        self,
        topic: str,
        content: str,
        materials: List[dict],
        previous_criticisms: List[dict]
    ) -> str:
        """构建批判提示"""
        prompt = f"""请对以下文章进行深度批判性质疑：

主题：{topic}

文章内容：
{content}

【批判角度】
请从以下角度进行批判（每角度至少一条质疑）：
1. 事实层：数据是否准确？引用是否可靠？数字是否被断章取义？
2. 逻辑层：前提是否成立？推理是否跳跃？因果是否混淆？
3. 证据层：例子是否有代表性？反例是否被忽略？
4. 视角层：是否存在结构性盲点？谁的视角被排除在外？
5. 隐含层：有哪些没明说但作者依赖的假设？
6. 价值层：作者的立场是否影响了客观判断？

【输出格式（JSON）】
{{
  "criticisms": [
    {{
      "dimension": "质疑维度",
      "question": "核心问题（一句话）",
      "analysis": "具体分析",
      "consequence": "后果推演",
      "threat_level": "致命/严重/中等/轻微",
      "is_new": true/false  // 是否是新的质疑（非重复）
    }}
  ],
  "summary": "批判概要",
  "most_damaging": "最致命的一条质疑",
  "no_major_issues": false  // 如果未发现重大问题设为true
}}
"""

        # 如果有之前的质疑，提醒不要重复
        if previous_criticisms:
            prompt += "\n\n【避免重复】\n以下质疑已在之前的轮次提出，请不要重复：\n"
            for pc in previous_criticisms[-5:]:
                prompt += f"- {pc.get('question', pc.get('content', ''))[:50]}...\n"

        return prompt

    def _parse_criticisms(self, content: str) -> Dict[str, Any]:
        """解析批判结果"""
        import re

        # 尝试提取JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return {
                    "criticisms": result.get("criticisms", []),
                    "summary": result.get("summary", ""),
                    "most_damaging": result.get("most_damaging", ""),
                    "no_major_issues": result.get("no_major_issues", False),
                    "raw_content": content,
                }
            except json.JSONDecodeError:
                pass

        # 如果JSON解析失败
        return {
            "criticisms": [],
            "raw_content": content,
            "parse_error": "Failed to parse criticisms",
        }
