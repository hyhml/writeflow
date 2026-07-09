from __future__ import annotations

import io
import json
import urllib.error

import pytest

from writeflow.agents.llm_client import ModelClient, ModelClientError
from writeflow.config import Settings


def make_settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "provider": "minimax",
        "model": "MiniMax-M1",
        "api_key": "test-key",
        "base_url": "https://api.example/v1",
        "max_tokens": 100,
        "temperature": 0.2,
        "request_timeout": 5.0,
        "max_retries": 0,
        "max_rounds": 2,
        "min_rounds": 1,
        "quality_depth_threshold": 6.0,
    }
    values.update(overrides)
    return Settings(**values)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_openai_compatible_request_includes_system_prompt(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            {
                "model": "MiniMax-M1",
                "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = ModelClient(settings=make_settings())

    result = client._generate_openai_compatible(
        [{"role": "user", "content": "topic"}],
        "system",
        None,
        None,
    )

    assert captured["url"] == "https://api.example/v1/chat/completions"
    assert captured["timeout"] == 5.0
    assert captured["payload"]["messages"][0] == {"role": "system", "content": "system"}
    assert result["content"] == "hello"
    assert result["usage"]["input_tokens"] == 3
    assert result["usage"]["output_tokens"] == 2


def test_parse_flat_compatible_response():
    client = ModelClient(settings=make_settings())

    result = client._parse_openai_response({"reply": "flat reply", "usage": {}})

    assert result["content"] == "flat reply"
    assert result["provider"] == "minimax"


def test_empty_response_raises_model_client_error():
    client = ModelClient(settings=make_settings())

    with pytest.raises(ModelClientError, match="空内容"):
        client._parse_openai_response({"choices": [{"message": {"content": ""}}]})


def test_http_401_has_readable_hint(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"bad key"),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = ModelClient(settings=make_settings())

    with pytest.raises(ModelClientError, match="API Key"):
        client._generate_openai_compatible(
            [{"role": "user", "content": "topic"}],
            None,
            None,
            None,
        )


def test_missing_base_url_for_openai_compatible_raises():
    client = ModelClient(settings=make_settings(provider="openai_compatible", base_url=""))

    with pytest.raises(ModelClientError, match="Base URL"):
        client._chat_completions_url()
