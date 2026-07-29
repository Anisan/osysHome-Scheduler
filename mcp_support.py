"""MCP integration helpers for Scheduler plugin."""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.core.lib.crontab import validate_cron_expression
from app.core.lib.mcp_contract import (
    build_plugin_mcp_descriptors,
    revision_from_dict,
    validate_entity_payload,
)
from app.core.models.Tasks import Task

from plugins.Scheduler.services import task_service

PLUGIN_NAME = "Scheduler"
TASKS = "tasks"

_TASK_WRITABLE_FIELDS = ("name", "code", "crontab", "runtime", "expire", "active")
_DATETIME_DESC = "ISO 8601 or 'YYYY-MM-DD HH:MM:SS' (local datetime)"
_CODE_CONTEXT = ["logger", "params"]

_PLUGIN_NOTES = [
    "Tasks run Python code via runCode (same sandbox as object methods).",
    "Cron task: set crontab (croniter syntax, usually 5 fields). runtime/expire are computed on save.",
    "One-shot task: leave crontab empty; set runtime (local datetime). expire defaults to runtime + 30 min.",
    "Use validate_crontab before upsert to preview next_runs.",
    "Use validate_entity_code / run_entity_dry to test task code before saving.",
    "enable_task / disable_task call enableJob/disableJob and refresh the task row.",
    "run_task_now executes stored task code immediately (does not change schedule).",
    "get_pool_stats returns thread-pool monitoring stats from the Scheduler plugin instance.",
    "Field started is set by the scheduler when a cron task is dispatched (read-only via MCP).",
]

_ENTITY_AUTHORING_PROMPT = "osys_scheduler_entity_authoring"


def _plugin_instance():
    try:
        from app.core.main.PluginsHelper import plugins
        return plugins.get(PLUGIN_NAME, {}).get("instance")
    except Exception:
        return None


def mcp_capabilities() -> dict:
    return {
        "mcp_version": 1,
        "entities": True,
        "config_schema": True,
        "notes": list(_PLUGIN_NOTES),
        "collections": [
            {
                "id": TASKS,
                "title": "Scheduled Tasks",
                "binding_mode": "none",
                "writable": True,
                "has_code": True,
                "list_filters": ["query", "active_only", "cron_only", "one_shot_only"],
                "default_sort": "name asc",
                "writable_fields": list(_TASK_WRITABLE_FIELDS),
                "description": (
                    "Scheduler tasks with cron recurrence or one-shot runtime. "
                    "Task name must be unique."
                ),
            },
        ],
        "operations": [
            "enable_task",
            "disable_task",
            "validate_crontab",
            "run_task_now",
            "get_pool_stats",
        ],
        "operation_schemas": {
            "enable_task": {
                "description": "Enable a scheduled task (enableJob)",
                "params": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer", "description": "Task id"},
                        "name": {"type": "string", "description": "Unique task name"},
                    },
                },
            },
            "disable_task": {
                "description": "Disable a scheduled task (disableJob)",
                "params": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer", "description": "Task id"},
                        "name": {"type": "string", "description": "Unique task name"},
                    },
                },
            },
            "validate_crontab": {
                "description": "Validate cron expression and preview next run times (local timezone)",
                "params": {
                    "type": "object",
                    "properties": {
                        "crontab": {"type": "string", "description": "Cron expression"},
                        "preview_count": {
                            "type": "integer",
                            "default": 3,
                            "minimum": 1,
                            "maximum": 10,
                            "description": "Number of upcoming runs to preview",
                        },
                    },
                    "required": ["crontab"],
                },
            },
            "run_task_now": {
                "description": "Run stored task Python code immediately (out of band from schedule)",
                "params": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer", "description": "Task id"},
                        "name": {"type": "string", "description": "Unique task name"},
                        "params": {
                            "type": "object",
                            "description": "Optional dict passed to runCode as args",
                        },
                    },
                },
            },
            "get_pool_stats": {
                "description": "Thread-pool monitoring stats (queue, active tasks, execution times)",
                "params": {"type": "object", "properties": {}},
            },
        },
    }


def mcp_config_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "level_logging": {
                "type": "string",
                "description": "Plugin logger level (DEBUG, INFO, WARNING, ERROR)",
            },
        },
    }


def _collection_meta(collection: str) -> dict:
    for item in mcp_capabilities()["collections"]:
        if item["id"] == collection:
            return item
    raise ValueError(f"Unsupported collection: {collection}")


def _merge_task_payload(payload: dict, entity_id=None) -> dict:
    merged = dict(payload or {})
    if entity_id in (None, ""):
        return merged
    try:
        current = mcp_get_entity(TASKS, entity_id)
    except ValueError:
        return merged
    for field in _TASK_WRITABLE_FIELDS:
        if field not in merged and field in current:
            merged[field] = current[field]
    return merged


def mcp_entity_schema(collection: str) -> dict:
    _collection_meta(collection)
    if collection == TASKS:
        return {
            "type": "object",
            "description": "Scheduler task. Cron recurrence or one-shot by runtime.",
            "properties": {
                "id": {
                    "type": "integer",
                    "readOnly": True,
                    "description": "Task id (set by server on create)",
                },
                "name": {
                    "type": "string",
                    "description": "Unique task name (used as job id in enableJob/disableJob)",
                },
                "code": {
                    "type": "string",
                    "description": "Python code executed by the task",
                    "x-code-language": "python",
                    "x-code-context": _CODE_CONTEXT,
                },
                "crontab": {
                    "type": ["string", "null"],
                    "description": (
                        "Cron expression (croniter). Empty/null for one-shot task. "
                        "When set, runtime/expire are recalculated on save."
                    ),
                },
                "runtime": {
                    "type": ["string", "null"],
                    "description": f"Next run time for one-shot tasks. {_DATETIME_DESC}",
                },
                "expire": {
                    "type": ["string", "null"],
                    "description": (
                        f"Expiration for one-shot tasks (deleted after expire). {_DATETIME_DESC}"
                    ),
                },
                "started": {
                    "type": ["string", "null"],
                    "readOnly": True,
                    "description": f"Last dispatch time for cron tasks. {_DATETIME_DESC}",
                },
                "active": {
                    "type": "boolean",
                    "default": True,
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
    cron_only: Optional[bool] = None,
    one_shot_only: Optional[bool] = None,
) -> List[dict]:
    if collection != TASKS:
        raise ValueError(f"Unsupported collection: {collection}")
    return task_service.list_tasks(
        query=query,
        limit=limit,
        active_only=active_only is True,
        cron_only=cron_only is True,
        one_shot_only=one_shot_only is True,
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
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    clean_payload = dict(payload)
    clean_payload.pop("id", None)
    clean_payload.pop("started", None)
    validation = mcp_validate_entity(collection, clean_payload, entity_id=entity_id)
    if not validation.get("ok"):
        raise ValueError(f"validation failed: {validation}")
    task = task_service.save_task(clean_payload, entity_id=entity_id)
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
    if operation == "run_task_now":
        run_params = params.get("params") if isinstance(params.get("params"), dict) else {}
        result = task_service.run_task_now(
            task_id=params.get("task_id"),
            name=params.get("name"),
            params=run_params,
        )
        return {"ok": True, "operation": operation, **result}
    if operation == "get_pool_stats":
        instance = _plugin_instance()
        if instance is None:
            raise ValueError("Scheduler plugin not loaded")
        pool = getattr(instance, "poolThread", None)
        if pool is None:
            raise ValueError("Scheduler thread pool is not initialized")
        return {
            "ok": True,
            "operation": operation,
            "stats": pool.get_monitoring_stats(),
        }
    raise ValueError(f"Unsupported operation: {operation}")


def mcp_descriptors() -> Tuple[list, list, list]:
    return build_plugin_mcp_descriptors(PLUGIN_NAME, mcp_capabilities())


def mcp_get_prompt(name: str, arguments: dict = None) -> dict:
    arguments = arguments or {}
    if name != _ENTITY_AUTHORING_PROMPT:
        raise ValueError(f"Unsupported prompt: {name}")
    task = str(arguments.get("task") or "").strip()
    collection = str(arguments.get("collection") or TASKS).strip()
    if not task:
        raise ValueError("task is required")
    notes_block = "\n".join(f"- {note}" for note in _PLUGIN_NOTES)
    prompt_text = (
        "Create Scheduler plugin entity payload by schema.\n"
        f"Plugin: {PLUGIN_NAME}\nCollection: {collection}\nTask: {task}\n\n"
        f"Plugin notes:\n{notes_block}\n\n"
        "Flow: osys_plugin_entity_schema -> validate_entity_code -> validate_crontab "
        "(if cron) -> validate_entity -> upsert_entity.\n"
        "Output fields: name, code, crontab (optional), runtime (optional), expire (optional), active.\n"
    )
    return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}


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
    if not isinstance(payload, dict):
        return {"ok": False, "errors": [{"field": "_", "message": "payload must be an object"}]}

    merged = _merge_task_payload(payload, entity_id=entity_id)
    schema = mcp_entity_schema(collection)
    result = validate_entity_payload(merged, schema)
    if not result.get("ok"):
        return result

    errors = list(result.get("errors") or [])
    warnings: List[dict] = []

    disallowed = [key for key in payload if key in ("id", "started")]
    if disallowed:
        return {
            "ok": False,
            "errors": [{"field": disallowed[0], "message": "field is read-only"}],
        }

    name = str(merged.get("name") or "").strip()
    if name:
        duplicate = Task.query.filter(Task.name == name).one_or_none()
        if duplicate is not None and (entity_id in (None, "") or duplicate.id != int(entity_id)):
            if entity_id in (None, ""):
                warnings.append({
                    "field": "name",
                    "message": (
                        f"task name already exists: {name}; "
                        f"upsert without entity_id will update id={duplicate.id}"
                    ),
                })
            else:
                errors.append({"field": "name", "message": f"task name already exists: {name}"})

    code = str(merged.get("code") or "")
    if code:
        code_validation = mcp_validate_entity_code(collection, code)
        if not code_validation.get("ok"):
            code_errors = code_validation.get("errors") or [{"message": "invalid code"}]
            for item in code_errors:
                errors.append({
                    "field": "code",
                    "message": item.get("message", "invalid code"),
                })

    crontab = merged.get("crontab")
    if crontab not in (None, ""):
        validation = validate_cron_expression(str(crontab))
        if not validation.get("ok"):
            message = (validation.get("errors") or [{}])[0].get("message", "invalid crontab")
            errors.append({"field": "crontab", "message": message})
    elif entity_id in (None, "") and merged.get("runtime") in (None, ""):
        warnings.append({
            "field": "runtime",
            "message": "one-shot task without runtime will run on next scheduler cycle",
        })

    if entity_id not in (None, ""):
        try:
            mcp_get_entity(collection, entity_id)
        except ValueError as ex:
            errors.append({"field": "id", "message": str(ex)})

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    response = {"ok": True, "errors": []}
    if warnings:
        response["warnings"] = warnings
    return response
