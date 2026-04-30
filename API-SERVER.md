# SEO Machine API Server

Use this backend when you want HTTP requests to generate research briefs, drafts,
optimization reports, and rewrites instead of typing slash commands in Claude Code.

## Setup

Install dependencies:

```bash
pip install -r data_sources/requirements.txt
```

Set your LLM provider and API key. For OpenAI:

```bash
export SEO_MACHINE_LLM_PROVIDER="openai"
export OPENAI_API_KEY="your_api_key"
export OPENAI_MODEL="gpt-5.2"
```

For Anthropic:

```bash
export SEO_MACHINE_LLM_PROVIDER="anthropic"
export ANTHROPIC_API_KEY="your_api_key"
```

Optional model settings:

```bash
export SEO_MACHINE_MAX_TOKENS="12000"
```

Start the server:

```bash
uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

## Available Actions

```bash
curl http://127.0.0.1:8000/actions
```

Actions come from `.claude/commands/*.md`, so adding a new command file makes it
available through the API.

## Run an Action

Generic endpoint:

```bash
curl -X POST http://127.0.0.1:8000/actions/run \
  -H "Content-Type: application/json" \
  -d '{
    "action": "/research",
    "input": "podcast advertising guide for 2026",
    "save": true
  }'
```

Slash-style endpoint:

```bash
curl -X POST http://127.0.0.1:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "input": "podcast advertising guide for 2026",
    "save": true
  }'
```

Write from a topic:

```bash
curl -X POST http://127.0.0.1:8000/write \
  -H "Content-Type: application/json" \
  -d '{
    "input": "podcast advertising guide for 2026",
    "extra_instructions": "Use the most recent research brief if relevant.",
    "save": true
  }'
```

Optimize a local draft:

```bash
curl -X POST http://127.0.0.1:8000/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "input": "drafts/podcast-advertising-guide-2026.md",
    "save": true
  }'
```

Analyze an existing URL:

```bash
curl -X POST http://127.0.0.1:8000/analyze-existing \
  -H "Content-Type: application/json" \
  -d '{
    "input": "https://example.com/blog/podcast-advertising-guide",
    "save": true
  }'
```

## Dry Run

Use `dry_run` to inspect the prompt without calling the LLM:

```bash
curl -X POST http://127.0.0.1:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "input": "podcast advertising guide for 2026",
    "dry_run": true,
    "save": false
  }'
```

## Response Shape

```json
{
  "action": "/research",
  "input": "podcast advertising guide for 2026",
  "dry_run": false,
  "artifact_path": "/Users/xinyaoyin/Desktop/seomachine/research/brief-podcast-advertising-guide-for-2026-2026-04-30.md",
  "content": "# Research Brief..."
}
```

## Output Locations

- `/research` saves to `research/brief-[slug]-[date].md`
- `/write` and `/article` save to `drafts/[slug]-[date].md`
- `/rewrite` saves to `rewrites/[slug]-rewrite-[date].md`
- `/optimize` saves to `drafts/optimization-report-[slug]-[date].md`
- Other commands save to the closest existing workflow folder.
