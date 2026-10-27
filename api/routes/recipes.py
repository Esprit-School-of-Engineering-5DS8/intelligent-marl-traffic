"""Agent recipe catalogue and validation.

A recipe is the single composable agent definition: policy knobs, runtime overlays and
optional LLM settings. Legacy files in ``configs/agents`` are listed as presets.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cotraffic import recipes

router = APIRouter(tags=["recipes"])


class RecipeBody(BaseModel):
    name: str | None = None
    recipe: dict[str, Any] | None = None
    overwrite: bool = True


class ValidateBody(BaseModel):
    recipe: dict[str, Any] = Field(default_factory=dict)


@router.get("/api/recipe-schema")
def recipe_schema() -> dict[str, Any]:
    return recipes.recipe_schema()


@router.get("/api/recipes")
def list_recipes() -> list[dict[str, Any]]:
    return recipes.list_recipes()


@router.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: str) -> dict[str, Any]:
    try:
        cfg = recipes.load_recipe(recipe_id)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(404, str(error)) from error
    return {"id": recipe_id, "hash": recipes.recipe_hash(cfg), "config": cfg}


@router.post("/api/recipes/validate")
def validate_recipe(body: ValidateBody) -> dict[str, Any]:
    try:
        cfg = recipes.normalize_recipe(body.recipe)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"ok": True, "hash": recipes.recipe_hash(cfg), "recipe": cfg}


@router.post("/api/recipes", status_code=201)
def create_recipe(body: RecipeBody) -> dict[str, Any]:
    raw = dict(body.recipe or {})
    if body.name:
        raw["name"] = body.name
    if not raw.get("name"):
        raise HTTPException(422, "recipe.name is required")
    try:
        path = recipes.save_recipe(raw, overwrite=body.overwrite)
        cfg = recipes.load_recipe(path.stem)
    except (ValueError, FileExistsError) as error:
        raise HTTPException(422, str(error)) from error
    return {"id": path.stem, "path": str(path), "hash": recipes.recipe_hash(cfg), "config": cfg}


@router.delete("/api/recipes/{recipe_id}")
def delete_recipe(recipe_id: str) -> dict[str, Any]:
    path = recipes.RECIPE_DIR / f"{recipe_id}.yaml"
    if not path.is_file():
        raise HTTPException(404, f"recipe {recipe_id!r} not found")
    path.unlink()
    return {"ok": True, "id": recipe_id}
