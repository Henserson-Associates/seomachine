"""
FastAPI server for SEO Machine actions.

Run with:
    uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from api_backend import (
    ActionError,
    available_actions,
    run_action,
    run_shopify_with_images,
    run_write_10_articles,
)


app = FastAPI(
    title="SEO Machine API",
    description="HTTP API for running SEO Machine actions such as /research and /write.",
    version="1.0.0",
)


class ActionRequest(BaseModel):
    action: Optional[str] = Field(
        default=None,
        description="Slash action such as /research or /write. Optional when using POST /research.",
    )
    input: str = Field(..., description="Topic, URL, or local file path for the action.")
    extra_instructions: str = Field(
        default="",
        description="Additional constraints for this run.",
    )
    context_files: Optional[List[str]] = Field(
        default=None,
        description="Optional subset of context/*.md files to include.",
    )
    dry_run: bool = Field(
        default=False,
        description="Return and optionally save the generated prompt instead of calling the LLM.",
    )
    save: bool = Field(
        default=True,
        description="Save the generated artifact into the repo's workflow folders.",
    )
    include_prompt: bool = Field(
        default=False,
        description="Include the full prompt in the API response.",
    )
    image_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=6,
        description="Optional number of generated images for /shopify-with-images. Defaults to OPENAI_IMAGE_COUNT or 2.",
    )


class ActionResponse(BaseModel):
    action: str
    input: str
    dry_run: bool
    artifact_path: Optional[str]
    content: str
    prompt: Optional[str] = None


class UploadedAssetResponse(BaseModel):
    local_path: str
    gcs_uri: str
    public_url: str
    content_type: str


class ShopifyWithImagesResponse(BaseModel):
    action: str
    input: str
    dry_run: bool
    artifact_path: Optional[str]
    html_asset: Optional[UploadedAssetResponse]
    image_assets: List[UploadedAssetResponse]
    image_prompts: List[str]
    content: str
    prompt: Optional[str] = None


class Write10ArticlesRequest(BaseModel):
    input: str = Field(
        default="https://valenciatheaterseating.com/",
        description="Optional company website URL, company context, campaign brief, or content focus for the topic agent.",
    )
    extra_instructions: str = Field(
        default="",
        description="Additional constraints for topic selection and article generation.",
    )
    context_files: Optional[List[str]] = Field(
        default=None,
        description="Optional subset of context/*.md files to include.",
    )
    dry_run: bool = Field(
        default=False,
        description="Return the topic-agent prompt without generating articles.",
    )
    save: bool = Field(
        default=True,
        description="Save local artifacts while uploading generated assets to GCS.",
    )
    include_prompt: bool = Field(
        default=False,
        description="Include the topic-agent prompt in the response.",
    )
    article_count: Optional[int] = Field(
        default=None,
        ge=5,
        le=20,
        description="Optional fixed article count. If omitted, the agent chooses between 5 and 20.",
    )
    continue_on_error: bool = Field(
        default=True,
        description="Continue generating remaining articles if one topic fails.",
    )
    image_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=6,
        description="Optional number of generated images per article. Defaults to OPENAI_IMAGE_COUNT or 2.",
    )


class TopicChoiceResponse(BaseModel):
    topic: str
    primary_keyword: str
    angle: str
    reason: str


class BatchArticleResponse(BaseModel):
    topic: TopicChoiceResponse
    error: Optional[str]
    artifact_path: Optional[str]
    html_asset: Optional[UploadedAssetResponse]
    image_assets: List[UploadedAssetResponse]


class Write10ArticlesResponse(BaseModel):
    action: str
    input: str
    dry_run: bool
    selected_count: int
    topics: List[TopicChoiceResponse]
    articles: List[BatchArticleResponse]
    prompt: Optional[str] = None


def serialize_asset(asset) -> UploadedAssetResponse:
    return UploadedAssetResponse(
        local_path=str(asset.local_path),
        gcs_uri=asset.gcs_uri,
        public_url=asset.public_url,
        content_type=asset.content_type,
    )


def serialize_topic(topic) -> TopicChoiceResponse:
    return TopicChoiceResponse(
        topic=topic.topic,
        primary_keyword=topic.primary_keyword,
        angle=topic.angle,
        reason=topic.reason,
    )


def serialize_batch_article(article) -> BatchArticleResponse:
    result = article.result
    return BatchArticleResponse(
        topic=serialize_topic(article.topic),
        error=article.error,
        artifact_path=str(result.artifact_path) if result and result.artifact_path else None,
        html_asset=serialize_asset(result.html_asset) if result and result.html_asset else None,
        image_assets=[serialize_asset(asset) for asset in result.image_assets] if result else [],
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/actions")
def list_actions() -> dict:
    return {"actions": [f"/{action}" for action in available_actions()]}


def execute_action(request: ActionRequest, route_action: Optional[str] = None) -> ActionResponse:
    action = route_action or request.action
    if not action:
        raise HTTPException(status_code=400, detail="Action is required.")

    try:
        result = run_action(
            action=action,
            target=request.input,
            extra_instructions=request.extra_instructions,
            context_files=request.context_files,
            dry_run=request.dry_run,
            save=request.save,
        )
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ActionResponse(
        action=f"/{result.action}",
        input=result.target,
        dry_run=result.dry_run,
        artifact_path=str(result.artifact_path) if result.artifact_path else None,
        content=result.content,
        prompt=result.prompt if request.include_prompt else None,
    )


@app.post("/actions/run", response_model=ActionResponse)
def run_named_action(request: ActionRequest) -> ActionResponse:
    return execute_action(request)


@app.post("/actions/{action_name}", response_model=ActionResponse)
def run_action_route(action_name: str, request: ActionRequest) -> ActionResponse:
    return execute_action(request, route_action=action_name)


@app.post("/shopify/download")
def download_shopify_html(request: ActionRequest) -> Response:
    try:
        result = run_action(
            action="shopify",
            target=request.input,
            extra_instructions=request.extra_instructions,
            context_files=request.context_files,
            dry_run=request.dry_run,
            save=request.save,
        )
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = (
        result.artifact_path.name
        if result.artifact_path
        else "shopify-article.html"
    )

    return Response(
        content=result.content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/shopify-with-images", response_model=ShopifyWithImagesResponse)
def shopify_with_images(request: ActionRequest) -> ShopifyWithImagesResponse:
    try:
        result = run_shopify_with_images(
            target=request.input,
            extra_instructions=request.extra_instructions,
            context_files=request.context_files,
            dry_run=request.dry_run,
            save=request.save,
            image_count=request.image_count,
        )
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ShopifyWithImagesResponse(
        action=f"/{result.action}",
        input=result.target,
        dry_run=result.dry_run,
        artifact_path=str(result.artifact_path) if result.artifact_path else None,
        html_asset=serialize_asset(result.html_asset) if result.html_asset else None,
        image_assets=[serialize_asset(asset) for asset in result.image_assets],
        image_prompts=result.image_prompts,
        content=result.content,
        prompt=result.prompt if request.include_prompt else None,
    )


@app.post("/write-10-articles", response_model=Write10ArticlesResponse)
def write_10_articles(request: Write10ArticlesRequest) -> Write10ArticlesResponse:
    try:
        result = run_write_10_articles(
            company_context=request.input,
            extra_instructions=request.extra_instructions,
            context_files=request.context_files,
            dry_run=request.dry_run,
            save=request.save,
            article_count=request.article_count,
            image_count=request.image_count,
            continue_on_error=request.continue_on_error,
        )
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Write10ArticlesResponse(
        action=f"/{result.action}",
        input=result.company_context,
        dry_run=result.dry_run,
        selected_count=result.selected_count,
        topics=[serialize_topic(topic) for topic in result.topics],
        articles=[serialize_batch_article(article) for article in result.articles],
        prompt=result.topic_prompt if request.include_prompt else None,
    )


@app.post("/{action_name}", response_model=ActionResponse)
def run_slash_style_action(action_name: str, request: ActionRequest) -> ActionResponse:
    return execute_action(request, route_action=action_name)
