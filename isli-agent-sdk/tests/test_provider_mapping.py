import pytest
from isli_agent.runner import _normalize_provider

def test_normalize_provider_google():
    assert _normalize_provider("google") == "gemini"
    assert _normalize_provider("GOOGLE") == "gemini"

def test_normalize_provider_vertex():
    assert _normalize_provider("vertex") == "vertex_ai"

def test_normalize_provider_passthrough():
    assert _normalize_provider("openai") == "openai"
    assert _normalize_provider("anthropic") == "anthropic"
    assert _normalize_provider("ollama") == "ollama"

def test_normalize_provider_idempotent():
    # If someone already passed the correct LiteLLM prefix
    assert _normalize_provider("gemini") == "gemini"
    assert _normalize_provider("vertex_ai") == "vertex_ai"

def test_normalize_provider_empty():
    assert _normalize_provider("") == ""
