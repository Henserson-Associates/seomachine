"""
HTTP backend helpers for running SEO Machine actions.

The Claude slash commands in .claude/commands are instruction documents. This
module turns those command files plus local context into prompts that an API
server can send to an LLM provider.
"""

from __future__ import annotations

import os
import re
import base64
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent
COMMANDS_DIR = PROJECT_ROOT / ".claude" / "commands"
CONTEXT_DIR = PROJECT_ROOT / "context"

DEFAULT_CONTEXT_FILES = [
    "brand-voice.md",
    "style-guide.md",
    "seo-guidelines.md",
    "internal-links-map.md",
    "features.md",
    "target-keywords.md",
    "competitor-analysis.md",
    "cro-best-practices.md",
    "ai-citation-targets.md",
    "reddit-strategy.md",
    "writing-examples.md",
]

OUTPUT_DIR_BY_ACTION = {
    "research": "research",
    "research-serp": "research",
    "research-gaps": "research",
    "research-performance": "research",
    "research-topics": "research",
    "research-trending": "research",
    "research-ai-citations": "research",
    "analyze-existing": "research",
    "performance-review": "research",
    "priorities": "research",
    "cluster": "research",
    "content-calendar": "research",
    "write": "drafts",
    "article": "drafts",
    "optimize": "drafts",
    "rewrite": "rewrites",
    "scrub": "rewrites",
    "shopify": "output",
    "shopify-with-images": "output",
    "repurpose": "published",
    "publish-draft": "published",
    "landing-write": "drafts",
    "landing-audit": "research",
    "landing-research": "research",
    "landing-competitor": "research",
    "landing-publish": "published",
}


@dataclass
class ActionResult:
    action: str
    target: str
    content: str
    artifact_path: Optional[Path]
    prompt: str
    dry_run: bool


@dataclass
class UploadedAsset:
    local_path: Path
    gcs_uri: str
    public_url: str
    content_type: str


@dataclass
class ShopifyWithImagesResult:
    action: str
    target: str
    content: str
    artifact_path: Optional[Path]
    html_asset: Optional[UploadedAsset]
    image_assets: List[UploadedAsset]
    image_prompts: List[str]
    prompt: str
    dry_run: bool


class ActionError(ValueError):
    """Raised when an action request cannot be prepared or executed."""


def load_environment() -> None:
    """Load repo-level environment files when python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "data_sources" / "config" / ".env")


def available_actions() -> List[str]:
    """Return all slash command actions available in .claude/commands."""
    if not COMMANDS_DIR.exists():
        return []
    return sorted(path.stem for path in COMMANDS_DIR.glob("*.md"))


def normalize_action(action: str) -> str:
    """Normalize '/research' or 'research' into a command file stem."""
    normalized = action.strip().lstrip("/").lower()
    normalized = re.sub(r"[^a-z0-9-]", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")

    if not normalized:
        raise ActionError("Action is required.")

    if normalized not in available_actions():
        raise ActionError(
            f"Unknown action '{action}'. Available actions: "
            + ", ".join(f"/{name}" for name in available_actions())
        )

    return normalized


def slugify(value: str, fallback: str = "request") -> str:
    """Create a filesystem-safe slug."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        value = parsed.path.strip("/") or parsed.netloc

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:80] or fallback


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_command(action: str) -> str:
    command_path = COMMANDS_DIR / f"{action}.md"
    if not command_path.exists():
        raise ActionError(f"Command file not found: {command_path}")
    return read_text_file(command_path)


def load_context(
    context_files: Optional[Iterable[str]] = None,
    max_chars: int = 80000,
) -> str:
    """Load configured context files, bounded by max_chars."""
    files = list(context_files or DEFAULT_CONTEXT_FILES)
    parts: List[str] = []
    used = 0

    for filename in files:
        path = CONTEXT_DIR / filename
        if not path.exists():
            continue

        content = read_text_file(path).strip()
        if not content:
            continue

        section = f"\n\n## context/{filename}\n\n{content}"
        remaining = max_chars - used
        if remaining <= 0:
            break

        if len(section) > remaining:
            section = section[:remaining] + "\n\n[Context truncated]"

        parts.append(section)
        used += len(section)

    return "".join(parts).strip()


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _load_url_content(url: str, max_chars: int) -> str:
    import requests
    from bs4 import BeautifulSoup

    response = requests.get(url, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else url
    body = soup.get_text("\n", strip=True)
    content = f"# Fetched URL: {title}\n\nSource: {url}\n\n{body}"
    return content[:max_chars]


def load_target_content(target: str, max_chars: int = 100000) -> Tuple[str, Optional[str]]:
    """Load target content when target is a local file or URL."""
    if not target:
        return "", None

    possible_path = PROJECT_ROOT / target
    if possible_path.exists() and possible_path.is_file():
        return read_text_file(possible_path)[:max_chars], str(possible_path.relative_to(PROJECT_ROOT))

    absolute_path = Path(target).expanduser()
    if absolute_path.exists() and absolute_path.is_file():
        return read_text_file(absolute_path)[:max_chars], str(absolute_path)

    if _looks_like_url(target):
        return _load_url_content(target, max_chars), target

    return "", None


def build_prompt(
    action: str,
    target: str,
    extra_instructions: str = "",
    context_files: Optional[Iterable[str]] = None,
    max_context_chars: int = 80000,
) -> str:
    command = load_command(action)
    context = load_context(context_files=context_files, max_chars=max_context_chars)
    target_content, target_source = load_target_content(target)

    target_block = target
    if target_content:
        target_block = (
            f"{target}\n\nLoaded source: {target_source}\n\n"
            f"### Target Content\n\n{target_content}"
        )

    return f"""You are SEO Machine running as an API backend.

Run the action exactly as defined by the command file. Produce the final artifact
content only. If the command says to save a file, include the full Markdown body
that should be saved. Do not mention that you are an API.

# Requested Action
/{action}

# User Input
{target_block}

# Action Definition
{command}

# Project Context
{context}

# Extra Instructions
{extra_instructions or "None"}
""".strip()


def output_path_for_action(action: str, target: str) -> Path:
    date = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(target, fallback=action)
    output_dir = PROJECT_ROOT / OUTPUT_DIR_BY_ACTION.get(action, "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    if action == "research":
        filename = f"brief-{slug}-{date}.md"
    elif action == "analyze-existing":
        filename = f"analysis-{slug}-{date}.md"
    elif action == "optimize":
        filename = f"optimization-report-{slug}-{date}.md"
    elif action == "rewrite":
        filename = f"{slug}-rewrite-{date}.md"
    elif action in {"write", "article"}:
        filename = f"{slug}-{date}.md"
    elif action in {"shopify", "shopify-with-images"}:
        filename = f"{action}-{slug}-{date}.html"
    else:
        filename = f"{action}-{slug}-{date}.md"

    return output_dir / filename


def clean_model_output(action: str, content: str) -> str:
    """Clean provider output for actions with strict artifact formats."""
    if action not in {"shopify", "shopify-with-images"}:
        return content.strip()

    cleaned = content.strip()
    fence_match = re.fullmatch(r"```(?:html)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    return cleaned


def call_anthropic(prompt: str) -> str:
    load_environment()

    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise ActionError(
            "The anthropic package is not installed. Run "
            "'pip install -r data_sources/requirements.txt'."
        ) from exc

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ActionError("ANTHROPIC_API_KEY is required unless dry_run=true.")

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    max_tokens = int(os.getenv("SEO_MACHINE_MAX_TOKENS", "12000"))

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    chunks = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def call_openai(prompt: str) -> str:
    load_environment()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ActionError(
            "The openai package is not installed. Run "
            "'pip install -r data_sources/requirements.txt'."
        ) from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ActionError("OPENAI_API_KEY is required unless dry_run=true.")

    model = os.getenv("OPENAI_MODEL", "gpt-5.2")
    max_tokens = int(os.getenv("SEO_MACHINE_MAX_TOKENS", "12000"))

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=max_tokens,
    )

    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)

    return "\n".join(chunks).strip()


def extract_shopify_article_signals(html: str) -> Dict[str, List[str] | str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    h2s = [tag.get_text(" ", strip=True) for tag in soup.find_all("h2")]
    paragraphs = [tag.get_text(" ", strip=True) for tag in soup.find_all("p")]

    return {
        "title": h1.get_text(" ", strip=True) if h1 else "Shopify article",
        "sections": h2s[:8],
        "summary": " ".join(paragraphs[:4])[:1200],
    }


def build_shopify_image_prompts(html: str, target: str) -> List[str]:
    signals = extract_shopify_article_signals(html)
    title = str(signals["title"])
    sections = "; ".join(signals["sections"]) if signals["sections"] else target
    summary = str(signals["summary"])

    base_style = (
        "Create a polished editorial blog image for a Shopify article. "
        "Photorealistic, premium ecommerce publication style, natural lighting, "
        "clean composition, no visible text, no watermarks, no logos, no UI mockups. "
        "The image must be directly relevant to the article."
    )

    return [
        (
            f"{base_style} Hero image for an article titled '{title}'. "
            f"Article topic: {target}. Context: {summary}"
        ),
        (
            f"{base_style} Supporting in-article image illustrating these sections: "
            f"{sections}. Article topic: {target}. Make it visually distinct from the hero image."
        ),
    ]


def call_openai_image(prompt: str) -> bytes:
    load_environment()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ActionError(
            "The openai package is not installed. Run "
            "'pip install -r data_sources/requirements.txt'."
        ) from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ActionError("OPENAI_API_KEY is required for image generation.")

    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1.5")
    size = os.getenv("OPENAI_IMAGE_SIZE", "1536x1024")
    quality = os.getenv("OPENAI_IMAGE_QUALITY", "medium")

    client = OpenAI(api_key=api_key)
    response = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        n=1,
    )

    if not response.data:
        raise ActionError("OpenAI image generation returned no image data.")

    image_base64 = getattr(response.data[0], "b64_json", None)
    if not image_base64:
        raise ActionError("OpenAI image generation did not return base64 image data.")

    return base64.b64decode(image_base64)


def upload_file_to_gcs(local_path: Path, object_name: str, content_type: str) -> UploadedAsset:
    load_environment()

    bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET") or os.getenv("GCS_BUCKET")
    if not bucket_name:
        raise ActionError("GOOGLE_CLOUD_STORAGE_BUCKET is required for /shopify-with-images.")

    try:
        from google.cloud import storage
    except ImportError as exc:
        raise ActionError(
            "The google-cloud-storage package is not installed. Run "
            "'pip install -r data_sources/requirements.txt'."
        ) from exc

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_filename(str(local_path), content_type=content_type)

    return UploadedAsset(
        local_path=local_path,
        gcs_uri=f"gs://{bucket_name}/{object_name}",
        public_url=f"https://storage.googleapis.com/{bucket_name}/{object_name}",
        content_type=content_type,
    )


def insert_shopify_images(html: str, image_urls: List[str]) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    insertion_points = []
    if h1:
        first_p_after_h1 = h1.find_next("p")
        if first_p_after_h1:
            insertion_points.append(first_p_after_h1)

    h2s = soup.find_all("h2")
    if len(h2s) >= 2:
        insertion_points.append(h2s[1])
    elif h2s:
        insertion_points.append(h2s[0])

    for index, image_url in enumerate(image_urls[:2]):
        img_p = soup.new_tag("p")
        img = soup.new_tag("img", src=image_url, alt="")
        img_p.append(img)

        if index < len(insertion_points):
            insertion_points[index].insert_after(img_p)
        else:
            soup.append(img_p)

    return str(soup)


def run_shopify_with_images(
    target: str,
    extra_instructions: str = "",
    context_files: Optional[Iterable[str]] = None,
    dry_run: bool = False,
    save: bool = True,
) -> ShopifyWithImagesResult:
    action = "shopify-with-images"
    prompt = build_prompt(
        action="shopify",
        target=target,
        extra_instructions=(
            f"{extra_instructions}\n\n"
            "Generate Shopify HTML first. The backend will generate and insert two "
            "relevant images after the HTML is produced."
        ).strip(),
        context_files=context_files,
    )

    if dry_run:
        image_prompts = [
            "Dry run: hero image prompt will be based on generated Shopify HTML.",
            "Dry run: supporting image prompt will be based on generated Shopify HTML.",
        ]
        return ShopifyWithImagesResult(
            action=action,
            target=target,
            content=prompt,
            artifact_path=None,
            html_asset=None,
            image_assets=[],
            image_prompts=image_prompts,
            prompt=prompt,
            dry_run=True,
        )

    shopify_result = run_action(
        "shopify",
        target,
        extra_instructions=extra_instructions,
        context_files=context_files,
        dry_run=False,
        save=False,
    )

    html = clean_model_output(action, shopify_result.content)
    image_prompts = build_shopify_image_prompts(html, target)
    slug = slugify(target, fallback="shopify")
    date = datetime.now().strftime("%Y-%m-%d")
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    image_assets = []
    image_urls = []
    image_extension = os.getenv("OPENAI_IMAGE_EXTENSION", "png").lstrip(".")

    for index, image_prompt in enumerate(image_prompts, 1):
        image_bytes = call_openai_image(image_prompt)
        image_path = output_dir / f"shopify-{slug}-{date}-image-{index}.{image_extension}"
        image_path.write_bytes(image_bytes)
        image_object = f"shopify/{slug}/{date}/image-{index}.{image_extension}"
        image_asset = upload_file_to_gcs(
            image_path,
            image_object,
            f"image/{image_extension}",
        )
        image_assets.append(image_asset)
        image_urls.append(image_asset.public_url)

    html_with_images = insert_shopify_images(html, image_urls)
    artifact_path = output_path_for_action(action, target)
    artifact_path.write_text(html_with_images + "\n", encoding="utf-8")

    html_asset = upload_file_to_gcs(
        artifact_path,
        f"shopify/{slug}/{date}/{artifact_path.name}",
        "text/html; charset=utf-8",
    )

    return ShopifyWithImagesResult(
        action=action,
        target=target,
        content=html_with_images,
        artifact_path=artifact_path,
        html_asset=html_asset,
        image_assets=image_assets,
        image_prompts=image_prompts,
        prompt=prompt,
        dry_run=False,
    )


def run_action(
    action: str,
    target: str,
    extra_instructions: str = "",
    context_files: Optional[Iterable[str]] = None,
    dry_run: bool = False,
    save: bool = True,
) -> ActionResult:
    normalized_action = normalize_action(action)
    prompt = build_prompt(
        action=normalized_action,
        target=target,
        extra_instructions=extra_instructions,
        context_files=context_files,
    )

    if dry_run:
        content = prompt
    else:
        load_environment()
        provider = os.getenv("SEO_MACHINE_LLM_PROVIDER", "openai").lower()
        if provider == "anthropic":
            content = call_anthropic(prompt)
        elif provider == "openai":
            content = call_openai(prompt)
        else:
            raise ActionError(
                f"Unsupported LLM provider: {provider}. "
                "Supported providers: anthropic, openai."
            )

    content = clean_model_output(normalized_action, content)

    artifact_path = None
    if save and content:
        artifact_path = output_path_for_action(normalized_action, target)
        artifact_path.write_text(content + "\n", encoding="utf-8")

    return ActionResult(
        action=normalized_action,
        target=target,
        content=content,
        artifact_path=artifact_path,
        prompt=prompt,
        dry_run=dry_run,
    )
