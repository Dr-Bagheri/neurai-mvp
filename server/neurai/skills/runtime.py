"""Skill Runtime (D7): the trust boundary.

Five rules, all enforced here in deterministic code, never delegated to the
LLM:

1. Skills run as the requesting user — every execution carries a
   SkillContext with the user's id, and skill implementations must scope
   every query with it (the data layer has no unscoped accessors for
   user-facing content).
2. Retrieved content is data, not authority — side-effectful skills require
   an explicit human confirmation (`ctx.confirmed`), set only by a UI click,
   never by the model or by tool-loop content.
3. Least privilege by manifest — a skill declares its permissions; the
   runtime hands it only matching capabilities (e.g. no `llm:*` permission →
   no harness handle at all).
4. Cloud consent propagates — `ctx.allow_cloud` flows from the meeting/
   workspace flag through the loop into every LLM call a skill makes.
5. Everything is audited — every invocation is appended to audit_log
   (who, skill, resource, ok/error, local/cloud); there is no update/delete
   path for that table in this codebase.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from neurai.db import get_db

# -- manifest -----------------------------------------------------------------

KNOWN_PERMISSIONS = {
    "read:meetings", "read:transcripts", "read:documents", "read:action_items",
    "write:action_items", "read:notes", "export:files", "llm:local", "llm:cloud",
}


@dataclass(frozen=True)
class SkillManifest:
    name: str
    description: str            # shown to the model as the tool description
    parameters: dict[str, Any]  # JSON-schema (object) for arguments
    permissions: frozenset[str]
    side_effect: bool = False   # True → requires ctx.confirmed (rule 2)

    def __post_init__(self):
        unknown = self.permissions - KNOWN_PERMISSIONS
        if unknown:
            raise ValueError(f"skill {self.name}: unknown permissions {unknown}")


@dataclass
class SkillContext:
    user_id: int
    username: str
    is_admin: bool = False
    allow_cloud: bool = False   # consent flag, propagated (rule 4)
    confirmed: bool = False     # set by an explicit UI click only (rule 2)


Handler = Callable[[SkillContext, dict[str, Any]], Awaitable[dict[str, Any]]]


class SkillError(Exception):
    pass


# -- minimal JSON-schema validation (type/required/enum) ------------------------

def _validate_params(schema: dict[str, Any], params: dict[str, Any]) -> str | None:
    """Returns an error string or None. Small on purpose: enough to bounce a
    malformed local-model call back for its one retry (D7 two-tier note)."""
    if not isinstance(params, dict):
        return "arguments must be an object"
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in params:
            return f"missing required parameter: {key}"
    type_map = {"string": str, "integer": int, "number": (int, float),
                "boolean": bool, "array": list, "object": dict}
    for key, value in params.items():
        spec = props.get(key)
        if spec is None:
            return f"unknown parameter: {key}"
        expected = spec.get("type")
        if expected and not isinstance(value, type_map.get(expected, object)):
            return f"parameter '{key}' must be {expected}"
        if "enum" in spec and value not in spec["enum"]:
            return f"parameter '{key}' must be one of {spec['enum']}"
    return None


# -- runtime --------------------------------------------------------------------

@dataclass
class _Registered:
    manifest: SkillManifest
    handler: Handler


class SkillRuntime:
    def __init__(self) -> None:
        self._skills: dict[str, _Registered] = {}

    def register(self, manifest: SkillManifest, handler: Handler) -> None:
        self._skills[manifest.name] = _Registered(manifest, handler)

    def manifests(self) -> list[SkillManifest]:
        return [r.manifest for r in self._skills.values()]

    def tool_schemas(self) -> list[dict[str, Any]]:
        """Tool definitions for the harness tool-use loop (Ollama/OpenAI format)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": r.manifest.name,
                    "description": r.manifest.description,
                    "parameters": r.manifest.parameters,
                },
            }
            for r in self._skills.values()
        ]

    def _audit(self, ctx: SkillContext, name: str, params: dict[str, Any],
               resource: str, ok: bool, error: str = "") -> None:
        get_db().execute(
            "INSERT INTO audit_log(user_id, skill, params, resource, source, ok, error) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                ctx.user_id, name,
                json.dumps(params, ensure_ascii=False)[:4000],
                resource,
                "cloud" if ctx.allow_cloud else "local",
                1 if ok else 0,
                error[:2000],
            ),
        )

    async def execute(self, name: str, params: dict[str, Any], ctx: SkillContext) -> dict[str, Any]:
        reg = self._skills.get(name)
        if reg is None:
            self._audit(ctx, name, params, "", False, "unknown skill")
            return {"error": f"unknown skill: {name}"}

        err = _validate_params(reg.manifest.parameters, params)
        if err:
            self._audit(ctx, name, params, "", False, f"invalid params: {err}")
            return {"error": f"invalid parameters: {err}"}

        # Rule 2: side effects require a human click, every time.
        if reg.manifest.side_effect and not ctx.confirmed:
            self._audit(ctx, name, params, "", False, "confirmation required")
            return {
                "confirmation_required": True,
                "skill": name,
                "params": params,
                "message_fa": "این عملیات نیاز به تأیید شما دارد.",
            }

        try:
            result = await reg.handler(ctx, params)
            self._audit(ctx, name, params, str(result.get("resource", "")), True)
            return result
        except SkillError as e:
            self._audit(ctx, name, params, "", False, str(e))
            return {"error": str(e)}
        except Exception as e:
            self._audit(ctx, name, params, "", False, f"internal: {e}")
            return {"error": "skill failed"}


_runtime: SkillRuntime | None = None


def get_skill_runtime() -> SkillRuntime:
    global _runtime
    if _runtime is None:
        _runtime = SkillRuntime()
        from .builtin import register_builtin_skills

        register_builtin_skills(_runtime)
    return _runtime


def set_skill_runtime(rt: SkillRuntime | None) -> None:
    global _runtime
    _runtime = rt
