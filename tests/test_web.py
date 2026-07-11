from __future__ import annotations

from writeflow.web import build_observation_from_payload, normalize_answers, step_payload


def test_build_observation_from_web_payload():
    observation = build_observation_from_payload(
        {
            "topic": "深圳电动车治理",
            "preset_observation": "我已有的观察",
            "fixed_answers": [
                {
                    "question": "我在本地看到的反常现象是什么？",
                    "answer": "骑手绕开主路检查点",
                },
                {
                    "question": "这个地方/案例和常见讨论有什么不一样？",
                    "answer": "",
                },
            ],
            "followup_answers": [
                {
                    "question": "谁承担代价？",
                    "answer": "小区门口行人和保安",
                }
            ],
        }
    )

    assert "深圳电动车治理" in observation
    assert "我已有的观察" in observation
    assert "骑手绕开主路检查点" in observation
    assert "小区门口行人和保安" in observation


def test_direct_human_observation_wins():
    observation = build_observation_from_payload(
        {
            "topic": "测试主题",
            "human_observation": "直接输入的完整材料",
            "preset_observation": "不应该使用",
        }
    )

    assert observation == "直接输入的完整材料"


def test_normalize_answers_ignores_empty_items():
    answers = normalize_answers(
        [
            {"question": "", "answer": ""},
            {"question": "问题", "answer": "回答"},
            "invalid",
        ],
        kind="fixed",
    )

    assert answers == [
        {
            "kind": "fixed",
            "index": 2,
            "question": "问题",
            "answer": "回答",
        }
    ]


def test_step_payload_has_ordered_steps():
    steps = step_payload()

    assert steps[0]["index"] == 1
    assert steps[0]["step"] == "observation_interviewer"
    assert steps[-1]["step"] == "editor"
