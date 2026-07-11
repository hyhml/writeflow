from __future__ import annotations

import asyncio

import pytest

from writeflow import config
from writeflow.agents.local_voice_collector import LocalVoiceCollectorAgent
from writeflow.agents.observation_interviewer import ObservationInterviewerAgent
from writeflow.agents.real_novelty_gate import RealNoveltyGateAgent


@pytest.fixture(autouse=True)
def reset_config_cache():
    config.reset_settings_cache()
    yield
    config.reset_settings_cache()


def test_observation_interviewer_missing_observation_returns_questions():
    agent = ObservationInterviewerAgent.__new__(ObservationInterviewerAgent)

    result = agent._missing_observation_result("深圳电动车治理")

    assert result["missing_observation"] is True
    assert result["observation_brief"] == {}
    assert "你在本地看到的反常现象是什么？" in result["observation_questions"]


def test_observation_interviewer_normalizes_user_observation():
    agent = ObservationInterviewerAgent.__new__(ObservationInterviewerAgent)

    result = agent._normalize_observation(
        {
            "observation_brief": {
                "abnormal_phenomenon": "交通节点冲突",
                "case_difference": "深圳狭长地形",
                "intuitive_root_cause": "路权分配",
                "concrete_solution": "划转车道",
                "must_preserve_details": ["禁摩节点", "东西向通勤"],
                "user_requirements": ["不要写成治理综述"],
            }
        },
        "深圳电动车治理",
        human_observation="原始要求：文章必须保留现场愤怒感。",
    )

    assert result["missing_observation"] is False
    assert result["source_status"] == "user_provided"
    assert result["observation_brief"]["concrete_solution"] == "划转车道"
    assert result["observation_brief"]["raw_human_observation"] == "原始要求：文章必须保留现场愤怒感。"
    assert "不要写成治理综述" in result["must_preserve"]


def test_local_voice_collector_without_search_does_not_fabricate_quotes(monkeypatch):
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "fake-key")
    monkeypatch.setenv("WRITEFLOW_SEARCH_PROVIDER", "none")
    config.reset_settings_cache()
    monkeypatch.setattr(config, "_dotenv_loaded", True)

    agent = LocalVoiceCollectorAgent()
    result = asyncio.run(agent.process({"topic": "深圳电动车治理"}))

    assert result["source_status"] == "not_configured"
    assert result["voices"] == []
    assert result["local_voice_brief"]["voices"] == []


def test_local_voice_collector_normalizes_context_search_results(monkeypatch):
    monkeypatch.setenv("WRITEFLOW_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "fake-key")
    config.reset_settings_cache()
    monkeypatch.setattr(config, "_dotenv_loaded", True)

    agent = LocalVoiceCollectorAgent()
    result = asyncio.run(
        agent.process(
            {
                "topic": "深圳电动车治理",
                "search_results": [
                    {
                        "speaker_type": "通勤者",
                        "location": "深圳",
                        "quote": "这段路每天都堵。",
                        "pain_point": "通勤节点拥堵",
                        "source_url": "https://example.com",
                    }
                ],
            }
        )
    )

    assert result["source_status"] == "from_context"
    assert result["voices"][0]["direct_quote"] == "这段路每天都堵。"


def test_real_novelty_gate_passes_with_one_valid_asset():
    agent = RealNoveltyGateAgent.__new__(RealNoveltyGateAgent)

    result = agent._normalize_gate_result(
        {
            "passed": True,
            "novelty_assets": [
                {
                    "type": "solution",
                    "claim": "把交通节点的一条车道划给非机动车",
                    "why_different": "不是微更新",
                    "evidence_hint": "路权重分配",
                    "must_preserve": "车道划转",
                }
            ],
        }
    )

    assert result["passed"] is True
    assert result["pass_reason"] == "real_novelty_present"


def test_real_novelty_gate_fails_without_case_structure_or_solution():
    agent = RealNoveltyGateAgent.__new__(RealNoveltyGateAgent)

    result = agent._normalize_gate_result(
        {
            "passed": True,
            "novelty_assets": [
                {"type": "attitude", "claim": "应该重视底层困境"}
            ],
        }
    )

    assert result["passed"] is False
    assert result["pass_reason"] == "no_real_novelty"
