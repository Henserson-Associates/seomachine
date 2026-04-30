"""
FastAPI server for SEO Machine actions.

Run with:
    uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from api_backend import ActionError, available_actions, run_action


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


class ActionResponse(BaseModel):
    action: str
    input: str
    dry_run: bool
    artifact_path: Optional[str]
    content: str
    prompt: Optional[str] = None


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


@app.post("/{action_name}", response_model=ActionResponse)
def run_slash_style_action(action_name: str, request: ActionRequest) -> ActionResponse:
    return execute_action(request, route_action=action_name)
