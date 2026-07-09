"""
Judge Agent - 质量评估
"""
from typing import Dict, Any, List
import json
from writeflow.agents.base import BaseAgent
from writeflow.agents.claude_client import get_claude_client


# 7维质量评估标准
QUALITY_DIMENSIONS = {
    "批判锋芒": {
        "weight": 0.20,
        "description": "识别矛盾、暴露问题、挑战权威的能力",
        "levels": {
            "10": "颠覆性视角，挑战权威性认知，经得起严格反驳",
            "8-9": "挑战主流假设，论证严密，有层次感",
            "6-7": "有一定批判性，论证基本自洽",
            "4-5": "批判浮于表面，缺乏深度",
            "1-3": "为批判而批判，或缺乏真正的批判性",
        },
    },
    "理论深度": {
        "weight": 0.15,
        "description": "理论框架的运用深度与原创性",
        "levels": {
            "10": "理论功底深厚，有原创性理论贡献",
            "8-9": "理论支撑有力，引用恰当",
            "6-7": "有一定理论支撑",
            "4-5": "理论支撑不足",
            "1-3": "缺乏理论支撑或理论运用错误",
        },
    },
    "洞察力度": {
        "weight": 0.15,
        "description": "看到常人忽视的关联与本质",
        "levels": {
            "10": "揭示深层机制，有非显而易见的因果解释",
            "8-9": "有独到见解，论证有深度",
            "6-7": "有一定洞察力",
            "4-5": "停留于表面现象",
            "1-3": "缺乏洞察，止于描述",
        },
    },
    "论证严谨性": {
        "weight": 0.20,
        "description": "逻辑自洽、证据充分、预判反驳",
        "levels": {
            "10": "逻辑严密，无懈可击",
            "8-9": "逻辑严谨，论证完整",
            "6-7": "逻辑基本自洽",
            "4-5": "存在逻辑漏洞",
            "1-3": "逻辑混乱，前后矛盾",
        },
    },
    "社会关联度": {
        "weight": 0.10,
        "description": "与现实问题的连接强度",
        "levels": {
            "10": "深刻揭示社会问题，具有现实意义",
            "8-9": "与现实紧密相关",
            "6-7": "有一定社会关联",
            "4-5": "脱离现实，纯粹抽象",
            "1-3": "与现实毫无关联",
        },
    },
    "文字穿透力": {
        "weight": 0.10,
        "description": "表达的精准度与感染力",
        "levels": {
            "10": "语言精炼，极具感染力",
            "8-9": "语言流畅，有感染力",
            "6-7": "语言通顺",
            "4-5": "表达不清",
            "1-3": "语言混乱",
        },
    },
    "学术规范性": {
        "weight": 0.10,
        "description": "引用、论证格式、概念使用",
        "levels": {
            "10": "引用精准，格式规范，概念准确",
            "8-9": "引用恰当，格式规范",
            "6-7": "基本规范",
            "4-5": "引用不规范",
            "1-3": "存在引用错误或概念混淆",
        },
    },
}


JUDGE_SYSTEM_PROMPT = """你是一位公正的质量裁判，负责评估批判性文章的7个维度质量。

【评估维度及权重】
- 批判锋芒 (20%): 识别矛盾、挑战权威的能力
- 理论深度 (15%): 理论框架的运用深度
- 洞察力度 (15%): 看到常人忽视的关联
- 论证严谨性 (20%): 逻辑自洽、证据充分
- 社会关联度 (10%): 与现实问题的连接
- 文字穿透力 (10%): 表达的精准度
- 学术规范性 (10%): 引用、格式规范

【评分标准】
每维度1-10分：
- 8-10分：超出期望，有显著贡献
- 6-7分：满足期望，达到基本标准
- 4-5分：低于期望，有明显不足
- 1-3分：严重不足，致命缺陷

【通过条件】
- 无任何维度 < 4分（否决项）
- 至少2个维度 ≥ 8分，或总分 ≥ 56分（满分80分的70%）
- 或5个维度全部 ≥ 6分（全面发展）

【输出格式（JSON）】
{
  "quality_scores": {
    "批判锋芒": 8,
    "理论深度": 7,
    "洞察力度": 8,
    "论证严谨性": 7,
    "社会关联度": 6,
    "文字穿透力": 7,
    "学术规范性": 7
  },
  "total_score": 50,
  "passed": true/false,
  "pass_reason": "excellent_dimensions/total_score/all_developed",
  "failed_dimensions": [],  // <4分的维度
  "excellent_dimensions": [],  // ≥8分的维度
  "verdict": "通过/需要修改/拒绝",
  "key_issues": ["主要问题1", "主要问题2"],
  "recommendations": ["修改建议1", "修改建议2"]
}"""


class JudgeAgent(BaseAgent):
    """Judge Agent - 质量评估专家"""

    def __init__(self, model: str = "claude-opus-4-8"):
        super().__init__("judge", model)
        self.client = get_claude_client()
        self.dimensions = QUALITY_DIMENSIONS

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理质量评估请求

        Args:
            input_data: {
                "task_id": str,
                "content": str,  # 文章内容
                "topic": str,  # 主题
                "criticisms": List[dict],  # 质疑列表
                "defenses": str,  # 辩护回应
                "materials": List[dict],  # 素材
            }
        """
        content = input_data.get("content", "")
        topic = input_data.get("topic", "")
        criticisms = input_data.get("criticisms", [])
        defenses = input_data.get("defenses", "")
        materials = input_data.get("materials", [])

        evaluation_prompt = self._build_evaluation_prompt(
            topic, content, criticisms, defenses, materials
        )

        messages = [{"role": "user", "content": evaluation_prompt}]

        response = await self.client.generate(
            messages=messages,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.3,  # 评估用低温保证稳定性
        )

        return self._parse_evaluation(response["content"])

    def _build_evaluation_prompt(
        self,
        topic: str,
        content: str,
        criticisms: List[dict],
        defenses: str,
        materials: List[dict]
    ) -> str:
        """构建评估提示"""
        prompt = f"""请评估以下批判性文章的7维质量：

主题：{topic}

文章内容：
{content[:3000]}...

"""

        if criticisms:
            prompt += "\n【质疑摘要】\n"
            for i, c in enumerate(criticisms[:5], 1):
                prompt += f"{i}. {c.get('question', c.get('content', ''))} ({c.get('threat_level', '')}级)\n"

        if defenses:
            prompt += f"\n【作者辩护回应】\n{defenses[:500]}...\n"

        prompt += """
请按7个维度进行评分，并给出通过/需要修改/拒绝的判定。
以JSON格式输出评估结果。"""

        return prompt

    def _parse_evaluation(self, content: str) -> Dict[str, Any]:
        """解析评估结果"""
        import re

        # 尝试提取JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())

                # 计算总分
                scores = result.get("quality_scores", {})
                if isinstance(scores, dict):
                    total = sum(scores.values()) if scores else 0
                    result["total_score"] = total

                    # 检查通过条件
                    failed = [k for k, v in scores.items() if v < 4]
                    excellent = [k for k, v in scores.items() if v >= 8]

                    result["failed_dimensions"] = failed
                    result["excellent_dimensions"] = excellent

                    # 判断通过
                    if not failed:  # 无否决项
                        if len(excellent) >= 2 or total >= 56:
                            result["passed"] = True
                            result["pass_reason"] = "excellent_dimensions" if len(excellent) >= 2 else "total_score"
                        elif all(v >= 6 for v in scores.values()):
                            result["passed"] = True
                            result["pass_reason"] = "all_developed"
                        else:
                            result["passed"] = False
                            result["pass_reason"] = "not_meets_threshold"
                    else:
                        result["passed"] = False
                        result["pass_reason"] = "failed_dimensions"

                return result
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "quality_scores": {},
            "total_score": 0,
            "passed": False,
            "parse_error": "Failed to parse evaluation",
        }

    def calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """计算加权总分"""
        total = 0
        for dim, weight_dim in self.dimensions.items():
            if dim in scores:
                # 将10分制转换为加权分数
                total += (scores[dim] / 10) * weight_dim["weight"]

        return total * 100  # 转换为百分制
