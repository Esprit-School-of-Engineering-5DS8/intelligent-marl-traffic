"""``GET/PUT /api/policy``: the active control policy (RL, LLM or baseline)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import api.policy as policy

router = APIRouter(tags=["policy"])


class PolicyRequest(BaseModel):
    method: str
    network: str | None = None


@router.get("/api/policy")
def read_policy() -> dict[str, Any]:
    return policy.current()


@router.put("/api/policy")
def write_policy(req: PolicyRequest) -> dict[str, Any]:
    try:
        return policy.update(req.method, req.network)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
