import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api_backend import (
    PROJECT_ROOT,
    available_actions,
    call_openai,
    clean_model_output,
    build_shopify_image_prompts,
    insert_shopify_images,
    normalize_action,
    output_path_for_action,
    run_action,
    run_shopify_with_images,
    slugify,
)
from api_server import ActionRequest, download_shopify_html, shopify_with_images


class ApiBackendTests(unittest.TestCase):
    def test_available_actions_includes_core_blog_workflows(self):
        actions = available_actions()

        self.assertIn("research", actions)
        self.assertIn("shopify", actions)
        self.assertIn("shopify-with-images", actions)
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

    def test_output_path_for_shopify_uses_html_extension(self):
        shopify_path = output_path_for_action("shopify", "Podcast Ads")

        self.assertEqual(shopify_path.parent, PROJECT_ROOT / "output")
        self.assertTrue(shopify_path.name.startswith("shopify-podcast-ads-"))
        self.assertEqual(shopify_path.suffix, ".html")

    def test_output_path_for_shopify_with_images_uses_html_extension(self):
        path = output_path_for_action("shopify-with-images", "Podcast Ads")

        self.assertEqual(path.parent, PROJECT_ROOT / "output")
        self.assertTrue(path.name.startswith("shopify-with-images-podcast-ads-"))
        self.assertEqual(path.suffix, ".html")

    def test_clean_model_output_removes_shopify_html_fence(self):
        content = "```html\n<div class=\"article-in-this-article\"></div>\n```"

        cleaned = clean_model_output("shopify", content)

        self.assertEqual(cleaned, '<div class="article-in-this-article"></div>')

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

    def test_build_shopify_image_prompts_returns_two_relevant_prompts(self):
        html = """
        <div class="article-in-this-article"></div>
        <h1>BMW Dealerships Toronto</h1>
        <p>Find the right BMW dealer in Toronto.</p>
        <h2>Compare dealership locations</h2>
        <h2>Service and financing</h2>
        """

        prompts = build_shopify_image_prompts(html, "bmw dealerships toronto")

        self.assertEqual(len(prompts), 2)
        self.assertIn("BMW Dealerships Toronto", prompts[0])
        self.assertIn("Service and financing", prompts[1])

    def test_insert_shopify_images_adds_two_img_tags(self):
        html = """
        <div class="article-in-this-article"></div>
        <h1>BMW Dealerships Toronto</h1>
        <p>Intro paragraph.</p>
        <h2>First section</h2>
        <h2>Second section</h2>
        """

        result = insert_shopify_images(html, ["https://example.com/1.png", "https://example.com/2.png"])

        self.assertIn('<img alt="" src="https://example.com/1.png"/>', result)
        self.assertIn('<img alt="" src="https://example.com/2.png"/>', result)

    def test_run_shopify_with_images_dry_run_does_not_generate_images(self):
        result = run_shopify_with_images("bmw dealerships toronto", dry_run=True)

        self.assertEqual(result.action, "shopify-with-images")
        self.assertTrue(result.dry_run)
        self.assertEqual(result.image_assets, [])
        self.assertEqual(len(result.image_prompts), 2)

    @patch("api_server.run_action")
    def test_download_shopify_html_returns_attachment(self, mock_run_action):
        mock_run_action.return_value = SimpleNamespace(
            content='<div class="article-in-this-article"></div>',
            artifact_path=PROJECT_ROOT / "output" / "shopify-test.html",
        )

        response = download_shopify_html(
            ActionRequest(input="test", dry_run=True, save=True)
        )

        self.assertEqual(response.media_type, "text/html; charset=utf-8")
        self.assertIn(
            'attachment; filename="shopify-test.html"',
            response.headers["content-disposition"],
        )

    @patch("api_server.run_shopify_with_images")
    def test_shopify_with_images_route_serializes_uploads(self, mock_run):
        asset = SimpleNamespace(
            local_path=PROJECT_ROOT / "output" / "image-1.png",
            gcs_uri="gs://bucket/image-1.png",
            public_url="https://storage.googleapis.com/bucket/image-1.png",
            content_type="image/png",
        )
        mock_run.return_value = SimpleNamespace(
            action="shopify-with-images",
            target="test",
            dry_run=False,
            artifact_path=PROJECT_ROOT / "output" / "article.html",
            html_asset=SimpleNamespace(
                local_path=PROJECT_ROOT / "output" / "article.html",
                gcs_uri="gs://bucket/article.html",
                public_url="https://storage.googleapis.com/bucket/article.html",
                content_type="text/html; charset=utf-8",
            ),
            image_assets=[asset],
            image_prompts=["prompt one", "prompt two"],
            content="<div></div>",
            prompt="prompt",
        )

        response = shopify_with_images(ActionRequest(input="test", save=True))

        self.assertEqual(response.action, "/shopify-with-images")
        self.assertEqual(response.image_assets[0].public_url, asset.public_url)


if __name__ == "__main__":
    unittest.main()
