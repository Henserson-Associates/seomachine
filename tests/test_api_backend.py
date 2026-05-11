import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api_backend import (
    PROJECT_ROOT,
    analyze_website,
    available_actions,
    call_openai,
    clean_model_output,
    build_shopify_image_prompts,
    build_topic_agent_prompt,
    insert_shopify_images,
    normalize_action,
    optimized_url_slug,
    output_path_for_action,
    parse_article_plan,
    parse_topic_choices,
    resolve_shopify_image_count,
    run_action,
    run_shopify_with_images,
    run_write_10_articles,
    shopify_gcs_prefix,
    slugify,
)
from api_server import (
    ActionRequest,
    Write10ArticlesRequest,
    download_shopify_html,
    shopify_with_images,
    write_10_articles,
)


class ApiBackendTests(unittest.TestCase):
    def test_available_actions_includes_core_blog_workflows(self):
        actions = available_actions()

        self.assertIn("research", actions)
        self.assertIn("shopify", actions)
        self.assertIn("shopify-with-images", actions)
        self.assertIn("write-10-articles", actions)
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

    def test_optimized_url_slug_shortens_title(self):
        self.assertEqual(
            optimized_url_slug("Home Theater Seating Layout Guide: Row Spacing, Sightlines, and Comfort"),
            "home-theater-seating-layout-guide",
        )

    def test_shopify_gcs_prefix_uses_wellness_and_optimized_title(self):
        html = "<h1>Home Theater Seating Layout Guide: Row Spacing and Comfort</h1>"

        with patch.dict("os.environ", {}, clear=True):
            prefix = shopify_gcs_prefix(html, "Fallback Topic")

        self.assertEqual(prefix, "shopify/wellness/home-theater-seating-layout-guide")

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

    def test_output_path_for_write_10_articles_uses_output_folder(self):
        path = output_path_for_action("write-10-articles", "Valencia Theater Seating")

        self.assertEqual(path.parent, PROJECT_ROOT / "output")
        self.assertTrue(path.name.startswith("write-10-articles-valencia-theater-seating-"))

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

    def test_build_topic_agent_prompt_mentions_valencia(self):
        prompt = build_topic_agent_prompt("Valencia Theater Seating", article_count=10)

        self.assertIn("Valencia Theater Seating", prompt)
        self.assertIn("Choose exactly 10", prompt)
        self.assertIn("Return JSON only", prompt)

    def test_build_topic_agent_prompt_auto_count_mentions_range(self):
        prompt = build_topic_agent_prompt(
            "https://valenciatheaterseating.com/",
            article_count=None,
            website_context="Homepage content",
            min_articles=5,
            max_articles=20,
        )

        self.assertIn("Choose between 5 and 20", prompt)
        self.assertIn('"article_count": number', prompt)
        self.assertIn("Homepage content", prompt)

    def test_parse_topic_choices_extracts_json_fence(self):
        response = """```json
        [
          {
            "topic": "Best Home Theater Seating Ideas",
            "primary_keyword": "home theater seating ideas",
            "angle": "Design guide",
            "reason": "Relevant to Valencia buyers"
          }
        ]
        ```"""

        topics = parse_topic_choices(response, article_count=1)

        self.assertEqual(topics[0].topic, "Best Home Theater Seating Ideas")
        self.assertEqual(topics[0].primary_keyword, "home theater seating ideas")

    def test_parse_article_plan_reads_selected_count(self):
        response = """{
          "article_count": 5,
          "topics": [
            {
              "topic": "Best Home Theater Seating Ideas",
              "primary_keyword": "home theater seating ideas",
              "angle": "Design guide",
              "reason": "Relevant to Valencia buyers"
            },
            {
              "topic": "Home Theater Recliner Buying Guide",
              "primary_keyword": "home theater recliner buying guide",
              "angle": "Buyer guide",
              "reason": "Relevant to Valencia buyers"
            },
            {
              "topic": "Media Room Seating Layouts",
              "primary_keyword": "media room seating layout",
              "angle": "Planning guide",
              "reason": "Relevant to Valencia buyers"
            },
            {
              "topic": "Leather Theater Seating Care",
              "primary_keyword": "leather theater seating care",
              "angle": "Maintenance guide",
              "reason": "Relevant to Valencia buyers"
            },
            {
              "topic": "Curved vs Straight Theater Seating",
              "primary_keyword": "curved theater seating",
              "angle": "Comparison",
              "reason": "Relevant to Valencia buyers"
            }
          ]
        }"""

        selected_count, topics = parse_article_plan(response)

        self.assertEqual(selected_count, 5)
        self.assertEqual(len(topics), 5)

    @patch("requests.get")
    def test_analyze_website_extracts_homepage_signals(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            raise_for_status=lambda: None,
            text="""
            <html><head><title>Valencia Home Theater Seating</title></head>
            <body>
              <h1>Valencia Home Theater Seating</h1>
              <h2>Home Theater Seating</h2>
              <a href="/home-theater-seating">Home Theater Seating</a>
              <p>Premium theater recliners and media room seating.</p>
            </body></html>
            """,
        )

        snapshot = analyze_website("https://valenciatheaterseating.com/", max_pages=1)

        self.assertIn("Valencia Home Theater Seating", snapshot)
        self.assertIn("Premium theater recliners", snapshot)

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

    def test_build_shopify_image_prompts_supports_custom_count(self):
        html = """
        <div class="article-in-this-article"></div>
        <h1>Massage Chair Buying Guide</h1>
        <p>Find the right massage chair.</p>
        <h2>Zero gravity</h2>
        <h2>Track types</h2>
        """

        prompts = build_shopify_image_prompts(html, "massage chair buying guide", image_count=3)

        self.assertEqual(len(prompts), 3)
        self.assertIn("Additional in-article image 3", prompts[2])

    def test_insert_shopify_images_adds_all_img_tags(self):
        html = """
        <div class="article-in-this-article"></div>
        <h1>BMW Dealerships Toronto</h1>
        <p>Intro paragraph.</p>
        <h2>First section</h2>
        <h2>Second section</h2>
        """

        result = insert_shopify_images(
            html,
            [
                "https://example.com/1.png",
                "https://example.com/2.png",
                "https://example.com/3.png",
            ],
        )

        self.assertIn('<img alt="" src="https://example.com/1.png"/>', result)
        self.assertIn('<img alt="" src="https://example.com/2.png"/>', result)
        self.assertIn('<img alt="" src="https://example.com/3.png"/>', result)

    def test_resolve_shopify_image_count_uses_env_default(self):
        with patch.dict("os.environ", {"OPENAI_IMAGE_COUNT": "4"}, clear=False):
            with patch("api_backend.load_environment"):
                self.assertEqual(resolve_shopify_image_count(), 4)

    def test_resolve_shopify_image_count_rejects_out_of_range(self):
        with self.assertRaisesRegex(Exception, "image_count must be between"):
            resolve_shopify_image_count(7)

    def test_run_shopify_with_images_dry_run_does_not_generate_images(self):
        result = run_shopify_with_images("bmw dealerships toronto", dry_run=True, image_count=3)

        self.assertEqual(result.action, "shopify-with-images")
        self.assertTrue(result.dry_run)
        self.assertEqual(result.image_assets, [])
        self.assertEqual(len(result.image_prompts), 3)

    def test_run_write_10_articles_dry_run_returns_topic_prompt(self):
        result = run_write_10_articles(
            company_context="Valencia Theater Seating",
            dry_run=True,
        )

        self.assertEqual(result.action, "write-10-articles")
        self.assertTrue(result.dry_run)
        self.assertEqual(result.selected_count, 5)
        self.assertEqual(result.topics, [])
        self.assertEqual(result.articles, [])
        self.assertIn("Choose between 5 and 20", result.topic_prompt)

    def test_write_10_articles_request_defaults_to_website_and_auto_count(self):
        request = Write10ArticlesRequest()

        self.assertEqual(request.input, "https://valenciatheaterseating.com/")
        self.assertIsNone(request.article_count)
        self.assertIsNone(request.image_count)

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

        response = shopify_with_images(ActionRequest(input="test", save=True, image_count=3))

        self.assertEqual(response.action, "/shopify-with-images")
        self.assertEqual(response.image_assets[0].public_url, asset.public_url)
        self.assertEqual(mock_run.call_args.kwargs["image_count"], 3)

    @patch("api_server.run_write_10_articles")
    def test_write_10_articles_route_returns_topics(self, mock_run):
        topic = SimpleNamespace(
            topic="Best Home Theater Seating Ideas",
            primary_keyword="home theater seating ideas",
            angle="Design guide",
            reason="Relevant to Valencia buyers",
        )
        mock_run.return_value = SimpleNamespace(
            action="write-10-articles",
            company_context="Valencia Theater Seating",
            dry_run=True,
            selected_count=5,
            topics=[topic],
            articles=[],
            topic_prompt="prompt",
        )

        response = write_10_articles(
            Write10ArticlesRequest(
                input="Valencia Theater Seating",
                dry_run=True,
                include_prompt=True,
                image_count=4,
            )
        )

        self.assertEqual(response.action, "/write-10-articles")
        self.assertEqual(response.topics[0].topic, topic.topic)
        self.assertEqual(response.prompt, "prompt")
        self.assertEqual(mock_run.call_args.kwargs["image_count"], 4)


if __name__ == "__main__":
    unittest.main()
