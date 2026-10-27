"""Offline diagnostics for Telegram Bot API connectivity and webhook safety."""
import asyncio
import contextlib
import io
import types
import unittest
from unittest.mock import patch

from re_harness import telegram_bridge as tg


class FakeBot:
    def __init__(self, token, webhook=""):
        self.webhook=webhook
        self.token=token
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def get_me(self):return types.SimpleNamespace(username="re_dragon_control_bot")
    async def get_webhook_info(self):
        return types.SimpleNamespace(url=self.webhook,pending_update_count=0)


class TelegramDoctorTests(unittest.TestCase):
    def test_read_only_probe_reports_owner_bot_and_no_webhook(self):
        b=asyncio.run(tg.telegram_probe(FakeBot,"dummy_not_real"))
        self.assertTrue(b["api_reachable"])
        self.assertEqual(b["bot_username"],"re_dragon_control_bot")
        self.assertFalse(b["webhook_configured"])
        self.assertEqual(b["pending_updates"],0)

    def test_detect_webhook_without_mutating_it(self):
        class WebhookBot(FakeBot):
            def __init__(self,token):
                super().__init__(token,webhook="https://example.invalid/webhook")
        b=asyncio.run(tg.telegram_probe(WebhookBot,"dummy_not_real"))
        self.assertTrue(b["webhook_configured"])

    def test_doctor_redacts_token_from_all_output(self):
        class FakeTelegram:
            class Bot(FakeBot): pass
        with patch.object(tg,"config",return_value={
                "token":"987654321:TOP_SECRET_TEST_TOKEN","user_id":12345
             }), patch("sys.modules",dict(
                telegram=types.SimpleNamespace(Bot=FakeTelegram.Bot),
                **{"telegram.error":types.SimpleNamespace(
                    InvalidToken=ValueError,NetworkError=ConnectionError,
                    TimedOut=TimeoutError)}
             )):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=tg.doctor()
        self.assertEqual(code,0)
        self.assertIn("re_dragon_control_bot",output.getvalue())
        self.assertNotIn("TOP_SECRET_TEST_TOKEN",output.getvalue())


if __name__=="__main__":
    unittest.main()
