# sinan/api/routes/admin_skills.py
"""Skill 管理路由。

对齐参考 page/api/routes/admin_skills.py 的五个端点与响应壳 {"code":0,"data":...}：
  GET    /api/page/admin/skills
  POST   /api/page/admin/skills/install
  PATCH  /api/page/admin/skills/{skill_key}/status
  PATCH  /api/page/admin/skills/{skill_key}
  DELETE /api/page/admin/skills/{skill_key}

差异：install 的请求体从 {"url": "<BOS zip>"} 改为 {"skill_key": "<本地包目录名>"}，
另外多一个 GET /local 用于查看「本地有哪些包还没入库」。认证按 Step 3 结论跳过。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from sinan.services import skill_package
from sinan.services.skill_registry import skill_registry

router = APIRouter(prefix="/api/page/admin/skills", tags=["admin-skills"])
logger = logging.getLogger(__name__)


class SkillInstallRequest(BaseModel):
    """从本地 skills 目录安装一个包。"""

    skill_key: str = Field(..., min_length=1, max_length=128)


class SkillStatusRequest(BaseModel):
    """启用 / 停用。"""

    status: str = Field(..., pattern="^(enabled|disabled)$")


class SkillUpdateRequest(BaseModel):
    """更新元信息。"""

    output_type: str | None = Field(None, pattern="^(data|html)$")
    name: str | None = None
    description: str | None = None


@router.get("")
async def list_skills(status: str | None = None, visibility: str | None = None):
    """列出已入库的 Skill（不返回 content）。"""
    skills = await skill_registry.list_skills(status=status, visibility=visibility)
    return {"code": 0, "data": skills}


@router.get("/local")
async def list_local_skills():
    """列出本地 skills 目录下的包目录名，标注是否已入库。"""
    installed = {s["skill_key"] for s in await skill_registry.list_skills()}
    keys = skill_package.list_local_packages()
    return {
        "code": 0,
        "data": {
            "skills_dir": str(skill_package.skills_root()),
            "packages": [{"skill_key": k, "installed": k in installed} for k in keys],
        },
    }


@router.post("/install")
async def install_skill(body: SkillInstallRequest,
                        x_user: str | None = Header(default=None, alias="X-User")):
    """从本地目录安装 / 重新安装一个 Skill。"""
    try:
        skill = await skill_registry.install_skill(body.skill_key, x_user or "system")
    except ValueError as e:
        return JSONResponse(status_code=400, content={"code": 400, "message": str(e)})
    if skill is None:
        return JSONResponse(
            status_code=404,
            content={"code": 404,
                     "message": f"本地包不存在或缺少 SKILL.md: {body.skill_key}"},
        )
    return {"code": 0, "data": skill}


@router.patch("/{skill_key}/status")
async def update_skill_status(skill_key: str, body: SkillStatusRequest,
                              x_user: str | None = Header(default=None, alias="X-User")):
    """启用 / 停用一个已安装的 Skill。"""
    skill = await skill_registry.update_skill_status(skill_key, body.status, x_user or "")
    if not skill:
        return JSONResponse(status_code=404, content={"code": 404, "message": "Skill not found"})
    return {"code": 0, "data": skill}


@router.patch("/{skill_key}")
async def update_skill(skill_key: str, body: SkillUpdateRequest,
                       x_user: str | None = Header(default=None, alias="X-User")):
    """更新 output_type / name / description。"""
    if await skill_registry.get_skill(skill_key, include_content=False) is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "Skill not found"})
    data: dict = {"skill_key": skill_key}
    if body.output_type is not None:
        data["output_type"] = body.output_type
    if body.name is not None:
        data["name"] = body.name
    if body.description is not None:
        data["description"] = body.description
    skill = await skill_registry.create_or_update_skill(data, x_user or "")
    return {"code": 0, "data": skill}


@router.delete("/{skill_key}")
async def delete_skill(skill_key: str):
    """删除表记录（不删本地包目录）。"""
    if not await skill_registry.delete_skill(skill_key):
        return JSONResponse(status_code=404, content={"code": 404, "message": "Skill not found"})
    return {"code": 0, "data": {"skill_key": skill_key}}