from __future__ import annotations

from writeflow.agents.thesis_architect import (
    REQUIRED_THESIS_FIELDS,
    ThesisArchitectAgent,
)


def test_thesis_architect_parses_required_fields():
    agent = ThesisArchitectAgent.__new__(ThesisArchitectAgent)
    raw = """
    {
      "core_claim": "A sharp claim",
      "conflict_with_common_view": "It conflicts with common view",
      "common_sense_overturned": "It overturns common sense",
      "strongest_evidence": "A strong evidence path",
      "most_dangerous_counterargument": "A dangerous counterargument",
      "novelty_assets": [
        {
          "type": "case",
          "claim": "A concrete case novelty",
          "why_different": "It differs from cliché",
          "evidence_hint": "Evidence path",
          "must_preserve": "A detail"
        }
      ]
    }
    """

    thesis = agent._parse_thesis_result(raw, "topic")

    assert set(REQUIRED_THESIS_FIELDS).issubset(thesis.keys())
    assert thesis["core_claim"] == "A sharp claim"
    assert thesis["novelty_assets"][0]["type"] == "case"


def test_thesis_architect_fills_missing_fields():
    agent = ThesisArchitectAgent.__new__(ThesisArchitectAgent)

    thesis = agent._parse_thesis_result('{"core_claim": "Only claim"}', "topic")

    assert thesis["core_claim"] == "Only claim"
    assert thesis["most_dangerous_counterargument"]
    assert thesis["novelty_assets"] == []
    assert "parse_warning" in thesis


def test_thesis_architect_falls_back_on_invalid_json():
    agent = ThesisArchitectAgent.__new__(ThesisArchitectAgent)

    thesis = agent._parse_thesis_result("not json", "topic")

    assert set(REQUIRED_THESIS_FIELDS).issubset(thesis.keys())
    assert thesis["core_claim"]
    assert "parse_warning" in thesis
