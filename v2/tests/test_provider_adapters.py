from __future__ import annotations

import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, "v2")

from agent.providers.base import LLMCompletionRequest, LLMProviderError
from agent.providers.local_adapter import LocalLemonadeAdapter
from agent.providers.openai_adapter import OpenAIAdapter


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            req = httpx.Request("POST", "https://example.com")
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("error", request=req, response=resp)

    def json(self) -> dict:
        return self._payload


class ProviderAdapterTests(unittest.TestCase):
    def test_local_adapter_parses_response(self) -> None:
        adapter = LocalLemonadeAdapter()
        req = LLMCompletionRequest(messages=[{"role": "user", "content": "hi"}], temperature=0.1, max_tokens=64)
        payload = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"total_tokens": 3}}
        with patch("agent.providers.local_adapter.httpx.post", return_value=FakeResponse(200, payload)):
            out = adapter.complete(req)
        self.assertEqual(out.content, "ok")
        self.assertEqual(out.provider_name, "local")

    def test_openai_adapter_missing_choices_raises(self) -> None:
        adapter = OpenAIAdapter()
        req = LLMCompletionRequest(messages=[{"role": "user", "content": "hi"}], temperature=0.1, max_tokens=64)
        with patch("agent.providers.openai_adapter.httpx.post", return_value=FakeResponse(200, {"x": 1})):
            with self.assertRaises(LLMProviderError):
                adapter.complete(req)


if __name__ == "__main__":
    unittest.main()
