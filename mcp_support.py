"""MCP integration helpers for Scheduler plugin."""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.core.lib.crontab import validate_cron_expression
from app.core.lib.mcp_contract import (
    build_plugin_mcp_descriptors,
    revision_from_dict,
    validate_entity_payload,
)
from plugins.Scheduler.services import task_service

TASKS = "tasks"


def mcp_capabilities() -> dict:
    return {
        "mcp_version": 1,
        "entities": True,
        "config_schema": True,
        "collections": [
            {
                "id": TASKS,
                "title": "Scheduled Tasks",
                "binding_mode": "none",
                "writable": True,
                "has_code": True,
            },
        ],
        "operations": [
            "enable_task",
            "disable_task",
            "validate_crontab",
        ],
    }


def mcp_config_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "level_logging": {"type": "string"},
        },
    }


def _collection_meta(collection: str) -> dict:
    for item in mcp_capabilities()["collections"]:
        if item["id"] == collection:
            return item
    raise ValueError(f"Unsupported collection: {collection}")


def mcp_entity_schema(collection: str) -> dict:
    _collection_meta(collection)
    if collection == TASKS:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique task name",
                },
                "code": {
                    "type": "string",
                    "description": "Python code executed by the task",
                },
                "crontab": {
                    "type": ["string", "null"],
                    "description": "Cron expression (croniter). Empty/null for one-shot task.",
                },
                "runtime": {
                    "type": ["string", "null"],
                    "description": "One-shot run time (local ISO datetime) when crontab is empty",
                },
                "expire": {
                    "type": ["string", "null"],
                    "description": "Task expiration (local ISO datetime) for one-shot tasks",
                },
                "active": {
                    "type": "boolean",
                    "description": "Whether the task is enabled",
                },
            },
            "required": ["name", "code"],
        }
    raise ValueError(f"Unsupported collection: {collection}")


def mcp_list_entities(
    collection: str,
    query: str = None,
    limit: int = 100,
    active_only: Optional[bool] = None,
) -> List[dict]:
    if collection != TASKS:
        raise ValueError(f"Unsupported collection: {collection}")
    return task_service.list_tasks(
        query=query,
        limit=limit,
        active_only=bool(active_only),
    )


def mcp_get_entity(collection: str, entity_id) -> dict:
    if collection != TASKS:
        raise ValueError(f"Unsupported collection: {collection}")
    return task_service.task_to_dict(task_service.get_task(entity_id))


def mcp_upsert_entity(collection: str, payload: dict, entity_id=None) -> dict:
    meta = _collection_meta(collection)
    if not meta.get("writable"):
        raise ValueError(f"Collection '{collection}' is read-only")
    if collection != TASKS:
        raise ValueError(f"Unsupported collection: {collection}")
    task = task_service.save_task(payload, entity_id=entity_id)
    return task_service.task_to_dict(task)


def mcp_delete_entity(collection: str, entity_id) -> bool:
    meta = _collection_meta(collection)
    if not meta.get("writable"):
        raise ValueError(f"Collection '{collection}' is read-only")
    if collection != TASKS:
        raise ValueError(f"Unsupported collection: {collection}")
    return task_service.delete_task(int(entity_id))


def mcp_validate_entity_code(collection: str, code: str) -> dict:
    if collection != TASKS:
        raise ValueError(f"Collection '{collection}' does not support code validation")
    return task_service.validate_task_code(code)


def mcp_run_entity_dry(collection: str, code: str, context: dict = None) -> dict:
    if collection != TASKS:
        raise ValueError(f"Collection '{collection}' does not support dry-run code")
    context = context or {}
    params = context.get("params") if isinstance(context.get("params"), dict) else {}
    result = task_service.run_task_code_dry(code, params=params)
    crontab = context.get("crontab")
    if crontab not in (None, ""):
        preview_count = context.get("preview_count", 3)
        result["crontab"] = validate_cron_expression(crontab, preview_count)
    return result


def mcp_invoke(operation: str, params: dict = None) -> dict:
    params = params or {}
    if operation == "enable_task":
        task = task_service.set_task_active(
            task_id=params.get("task_id"),
            name=params.get("name"),
            active=True,
        )
        return {"ok": True, "operation": operation, "task": task_service.task_to_dict(task)}
    if operation == "disable_task":
        task = task_service.set_task_active(
            task_id=params.get("task_id"),
            name=params.get("name"),
            active=False,
        )
        return {"ok": True, "operation": operation, "task": task_service.task_to_dict(task)}
    if operation == "validate_crontab":
        crontab = str(params.get("crontab") or "").strip()
        if not crontab:
            raise ValueError("crontab is required")
        preview_count = params.get("preview_count", 3)
        return {"ok": True, "operation": operation, **validate_cron_expression(crontab, preview_count)}
    raise ValueError(f"Unsupported operation: {operation}")


def mcp_descriptors() -> Tuple[list, list, list]:
    return build_plugin_mcp_descriptors("Scheduler", mcp_capabilities())


def mcp_entity_revision(collection: str, entity_id) -> str:
    if collection != TASKS:
        raise ValueError(f"Unsupported collection: {collection}")
    entity = mcp_get_entity(collection, entity_id)
    return revision_from_dict(
        entity,
        keys=["id", "name", "code", "crontab", "runtime", "expire", "started", "active"],
    )


def mcp_validate_entity(collection: str, payload: dict, entity_id=None) -> dict:
    if collection != TASKS:
        raise ValueError(f"Unsupported collection: {collection}")
    schema = mcp_entity_schema(collection)
    result = validate_entity_payload(payload, schema)
    if not result.get("ok"):
        return result

    code = str(payload.get("code") or "")
    code_validation = mcp_validate_entity_code(collection, code)
    if not code_validation.get("ok"):
        return {"ok": False, "errors": code_validation.get("errors") or [{"field": "code", "message": "invalid code"}]}

    crontab = payload.get("crontab")
    if crontab not in (None, ""):
        validation = validate_cron_expression(str(crontab))
        if not validation.get("ok"):
            message = (validation.get("errors") or [{}])[0].get("message", "invalid crontab")
            return {"ok": False, "errors": [{"field": "crontab", "message": message}]}

    if entity_id not in (None, ""):
        try:
            mcp_get_entity(collection, entity_id)
        except ValueError as ex:
            return {"ok": False, "errors": [{"field": "id", "message": str(ex)}]}

    return {"ok": True, "errors": []}
