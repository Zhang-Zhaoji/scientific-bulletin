"""Prevent the API default from overriding an explicitly non-thinking curation run."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LLM_eval'))
from call_API import LLM_process
from pydantic import BaseModel


class Response(BaseModel):
    value: int


class RequestModeTests(unittest.TestCase):
    def capture(self, thinking):
        requests = []

        def create(**kwargs):
            requests.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"value": 1}'))])

        client = LLM_process('test-placeholder', thinking=thinking, provider='DeepSeek')
        client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        self.assertEqual(client.completion('System', 'User', Response).value, 1)
        return requests[0]

    def test_nonthinking_is_explicit(self):
        request = self.capture(False)
        self.assertEqual(request['extra_body'], {'thinking': {'type': 'disabled'}})

    def test_thinking_is_explicit(self):
        request = self.capture(True)
        self.assertEqual(request['extra_body'], {'thinking': {'type': 'enabled'}})


if __name__ == '__main__':
    unittest.main()
