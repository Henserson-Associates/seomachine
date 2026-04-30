"""
HTTP backend helpers for running SEO Machine actions.

The Claude slash commands in .claude/commands are instruction documents. This
module turns those command files plus local context into prompts that an API
server can send to an LLM provider.
"""

from __future__ import annotations

import os
import re
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
    elif action == "shopify":
        filename = f"shopify-{slug}-{date}.html"
    else:
        filename = f"{action}-{slug}-{date}.md"

    return output_dir / filename


def clean_model_output(action: str, content: str) -> str:
    """Clean provider output for actions with strict artifact formats."""
    if action != "shopify":
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
