import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api_backend import (
    PROJECT_ROOT,
    available_actions,
    call_openai,
    normalize_action,
    output_path_for_action,
    run_action,
    slugify,
)


class ApiBackendTests(unittest.TestCase):
    def test_available_actions_includes_core_blog_workflows(self):
        actions = available_actions()

        self.assertIn("research", actions)
        self.assertIn("write", actions)
        self.assertIn("optimize", actions)

    def test_normalize_action_accepts_slash_prefix(self):
        self.assertEqual(normalize_action("/research"), "research")
        self.assertEqual(normalize_action("write"), "write")

    def test_slugify_handles_url_and_topic(self):
        self.assertEqual(slugify("Podcast Ads Guide 2026"), "podcast-ads-guide-2026")
        self.assertEqual(
            slugify("https://example.com/blog/podcast-ads/?utm=1"),
            "blog-podcast-ads",
        )

    def test_output_path_uses_existing_workflow_folders(self):
        research_path = output_path_for_action("research", "Podcast Ads")
        write_path = output_path_for_action("write", "Podcast Ads")

        self.assertEqual(research_path.parent, PROJECT_ROOT / "research")
        self.assertEqual(write_path.parent, PROJECT_ROOT / "drafts")
        self.assertTrue(research_path.name.startswith("brief-podcast-ads-"))

    @patch("api_backend.call_openai", return_value="# OpenAI result")
    def test_run_action_uses_openai_provider(self, mock_call_openai):
        with patch.dict(
            "os.environ",
            {"SEO_MACHINE_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"},
            clear=False,
        ):
            result = run_action(
                "/research",
                "Podcast Ads",
                dry_run=False,
                save=False,
            )

        self.assertEqual(result.content, "# OpenAI result")
        mock_call_openai.assert_called_once()

    @patch("api_backend.call_openai", return_value="# OpenAI default result")
    def test_run_action_defaults_to_openai_provider(self, mock_call_openai):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch("api_backend.load_environment"):
                with patch.dict("os.environ", {}, clear=True):
                    result = run_action(
                        "/research",
                        "Podcast Ads",
                        dry_run=False,
                        save=False,
                    )

        self.assertEqual(result.content, "# OpenAI default result")
        mock_call_openai.assert_called_once()

    def test_call_openai_returns_output_text(self):
        mock_openai_class = Mock()
        mock_client = mock_openai_class.return_value
        mock_client.responses.create.return_value = SimpleNamespace(
            output_text="# Generated research"
        )
        fake_openai_module = SimpleNamespace(OpenAI=mock_openai_class)

        with patch.dict("sys.modules", {"openai": fake_openai_module}):
            with patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "test-key",
                    "OPENAI_MODEL": "gpt-test",
                    "SEO_MACHINE_MAX_TOKENS": "100",
                },
                clear=False,
            ):
                content = call_openai("prompt")

        self.assertEqual(content, "# Generated research")
        mock_client.responses.create.assert_called_once_with(
            model="gpt-test",
            input="prompt",
            max_output_tokens=100,
        )


if __name__ == "__main__":
    unittest.main()
