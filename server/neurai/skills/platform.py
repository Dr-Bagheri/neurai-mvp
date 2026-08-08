"""Platform-control skills (D7 amendment): the assistant administers the
platform ONLY through these — thin wrappers over neurai/platform_ops, the
same core functions the REST admin API calls, so checks and D12 chain
logging are identical on both surfaces.

Security posture:
- `admin=True` manifests → the runtime enforces ctx.is_admin (denial is
  shaped like "unknown skill" so capabilities aren't probeable).
- Every mutating skill is `side_effect=True` → the rule-2 human-confirmation
  card, every time; a transcript can never auto-trigger one.
- get_status is the only read-only skill here (mirrors GET /api/admin/status).
"""
from __future__ import annotations

from typing import Any

from neurai import platform_ops
from neurai.platform_ops import OperationError

from .runtime import SkillContext, SkillError, SkillManifest, SkillRuntime


async def get_status(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    return {"status": platform_ops.platform_status(), "resource": "platform"}


async def delete_meeting(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    try:
        result = platform_ops.remove_meeting(int(params["meeting_id"]), actor=ctx.username)
    except (LookupError, OperationError) as e:
        raise SkillError(str(e))
    return {"deleted": True, **result, "resource": f"meeting:{params['meeting_id']}"}


async def delete_document(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    try:
        result = platform_ops.remove_document(
            int(params["document_id"]), actor=ctx.username,
            requester_user_id=ctx.user_id, is_admin=ctx.is_admin,
        )
    except LookupError as e:
        raise SkillError(str(e))
    return {"deleted": True, **result, "resource": f"document:{params['document_id']}"}


async def set_setting(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    key, value = params["key"], params["value"]
    try:
        platform_ops.apply_settings({key: value}, actor=ctx.username)
    except OperationError as e:
        raise SkillError(str(e))
    return {"updated": {key: value}, "resource": f"settings:{key}"}


async def trigger_backup(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    try:
        job_id = platform_ops.trigger_backup(actor=ctx.username)
    except OperationError as e:
        raise SkillError(str(e))
    return {"job_id": job_id, "resource": "backup"}


def register_platform_skills(rt: SkillRuntime) -> None:
    def obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {"type": "object", "properties": props, "required": required}

    rt.register(SkillManifest(
        "get_status", "وضعیت سامانه: پروفایل اتصال، وضعیت ابر، جلسه زنده، صف کارها",
        obj({}, []),
        frozenset(), admin=True), get_status)
    rt.register(SkillManifest(
        "delete_meeting", "حذف کامل یک جلسه از پایگاه داده (رونوشت، صوت، ایندکس) — مدیر",
        obj({"meeting_id": {"type": "integer", "description": "شناسه جلسه"}}, ["meeting_id"]),
        frozenset(), side_effect=True, admin=True), delete_meeting)
    rt.register(SkillManifest(
        "delete_document", "حذف یک سند بارگذاری‌شده و ایندکس آن",
        obj({"document_id": {"type": "integer", "description": "شناسه سند"}}, ["document_id"]),
        frozenset({"read:documents"}), side_effect=True), delete_document)
    rt.register(SkillManifest(
        "set_setting", "تغییر یکی از تنظیمات سامانه — مدیر",
        obj({
            "key": {"type": "string", "enum": sorted(platform_ops.MUTABLE_SETTINGS)},
            "value": {"type": "string"},
        }, ["key", "value"]),
        frozenset(), side_effect=True, admin=True), set_setting)
    rt.register(SkillManifest(
        "trigger_backup", "گرفتن نسخه پشتیبان رمزنگاری‌شده و ارسال به فضای ابری — مدیر",
        obj({}, []),
        frozenset(), side_effect=True, admin=True), trigger_backup)
