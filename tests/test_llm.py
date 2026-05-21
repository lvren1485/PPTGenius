"""Tests for LLM abstraction layer."""

from agent.llm import MockLLMClient, LLMResponse, LLMMessage


def test_mock_chat():
    client = MockLLMClient()
    resp = client.chat(system="test", messages=["hello"])
    assert isinstance(resp, LLMResponse)
    assert resp.text == "[Mock LLM response]"
    assert resp.model == "mock"


def test_mock_structured():
    client = MockLLMClient()
    from pydantic import BaseModel

    class TestModel(BaseModel):
        name: str = "default"

    result, raw = client.chat_structured(response_model=TestModel)
    assert isinstance(result, TestModel)
    assert result.name == "default"


def test_llm_message():
    msg = LLMMessage(role="user", content="hello")
    d = msg.to_dict()
    assert d["role"] == "user"
    assert d["content"] == "hello"
