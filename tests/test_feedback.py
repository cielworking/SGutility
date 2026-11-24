import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FeedbackTests(unittest.TestCase):
    def test_theme_js_registers_feedback_header_footer_and_modal(self):
        src = (ROOT / "theme.js").read_text(encoding="utf-8")
        for token in (
            "initFeedbackWidget",
            "sga-fb-trigger",
            "sga-fb-footer-prompt",
            "https://sgalerts.com/api/feedback",
            "sga-fb-hp",
        ):
            self.assertIn(token, src)

    def test_feedback_worker_requires_admin_auth_for_reads_and_supports_telegram(self):
        src = (ROOT / "workers" / "sgalerts-feedback.js").read_text(encoding="utf-8")
        for token in (
            "FEEDBACK_ADMIN_KEY",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
            "isAuthorized(request, env)",
            "Unauthorized",
            "RATE_LIMIT_MAX",
        ):
            self.assertIn(token, src)

    def test_feedback_admin_page_is_noindex(self):
        html = (ROOT / "feedback-admin.html").read_text(encoding="utf-8")
        self.assertIn('content="noindex, nofollow"', html)
        self.assertIn('data-no-feedback="1"', html)
