"""Scheduler task persistence and helpers."""

from __future__ import annotations

import ast
import datetime
from typing import Any, Dict, Optional

from sqlalchemy import delete, or_

from app.core.lib.common import disableJob, enableJob, runCode
from app.core.lib.crontab import nextStartCronJob, validate_cron_expression
from app.core.models.Tasks import Task
from app.database import (
    convert_local_to_utc,
    convert_utc_to_local,
    db,
    get_default_timezone,
    get_now_to_utc,
    get_user_timezone,
    row2dict,
)


def _parse_datetime(value) -> Optional[datetime.datetime]:
    if value in (None, "", False):
        return None
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def _normalize_crontab(value) -> Optional[str]:
    if value in (None, "", False):
        return None
    text = str(value).strip()
    return text or None


def _serialize_datetime(value) -> Optional[str]:
    """Serialize DB UTC naive datetime as ISO-8601 with Z (UTC)."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        # Always emit UTC marker so JS Date / clients don't treat naive stamp as local.
        text = value.isoformat(sep="T", timespec="seconds")
        if value.tzinfo is not None:
            utc = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            text = utc.isoformat(sep="T", timespec="seconds")
        return text + "Z"
    return str(value)


def task_to_dict(task: Task) -> Dict[str, Any]:
    data = row2dict(task)
    # Always serialize raw UTC from the ORM (row2dict may already localize).
    for field in ("runtime", "expire", "started"):
        data[field] = _serialize_datetime(getattr(task, field, None))
    if data.get("active") is None:
        data["active"] = True
    return data


def validate_task_code(code: str) -> dict:
    errors = []
    try:
        ast.parse(code or "")
    except SyntaxError as ex:
        errors.append({"message": str(ex), "line": ex.lineno, "column": ex.offset})
    return {"ok": len(errors) == 0, "errors": errors}


def apply_schedule_fields(task: Task, payload: Dict[str, Any]) -> None:
    crontab = _normalize_crontab(payload.get("crontab", task.crontab))
    if crontab:
        validation = validate_cron_expression(crontab)
        if not validation.get("ok"):
            message = validation.get("errors", [{}])[0].get("message", "Invalid crontab")
            raise ValueError(f"Invalid crontab: {message}")
        task.crontab = crontab
        next_local = nextStartCronJob(crontab)
        # Cron is computed in server TZ; persist UTC (do not reinterpret as user TZ).
        task.runtime = convert_local_to_utc(next_local, timezone=get_default_timezone())
        task.expire = task.runtime + datetime.timedelta(seconds=1800)
        return

    task.crontab = None
    user_tz = get_user_timezone()
    runtime = _parse_datetime(payload.get("runtime"))
    if runtime is not None:
        task.runtime = convert_local_to_utc(runtime, timezone=user_tz)
    elif task.runtime is None:
        task.runtime = get_now_to_utc()

    expire = _parse_datetime(payload.get("expire"))
    if expire is not None:
        task.expire = convert_local_to_utc(expire, timezone=user_tz)
    elif task.expire is None:
        task.expire = task.runtime + datetime.timedelta(seconds=1800)


def save_task(payload: Dict[str, Any], entity_id: Optional[int] = None) -> Task:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    code = payload.get("code")
    if code is None or str(code).strip() == "":
        raise ValueError("code is required")

    code_text = str(code)
    validation = validate_task_code(code_text)
    if not validation.get("ok"):
        message = validation.get("errors", [{}])[0].get("message", "Invalid code")
        raise ValueError(f"Invalid code: {message}")

    if entity_id is not None:
        task = Task.query.get(entity_id)
        if task is None:
            raise ValueError(f"Task not found: {entity_id}")
        existing = Task.query.filter(Task.name == name, Task.id != int(entity_id)).one_or_none()
        if existing is not None:
            raise ValueError(f"Task name already exists: {name}")
    else:
        task = Task.query.filter(Task.name == name).one_or_none()
        if task is None:
            task = Task()
            db.session.add(task)

    task.name = name
    task.code = code_text
    if "active" in payload:
        task.active = bool(payload.get("active"))
    elif task.active is None:
        task.active = True

    apply_schedule_fields(task, payload)
    db.session.commit()
    db.session.refresh(task)
    return task


def delete_task(entity_id: int) -> bool:
    task = Task.query.get(entity_id)
    if task is None:
        return False
    db.session.execute(delete(Task).where(Task.id == entity_id))
    db.session.commit()
    return True


def get_task(entity_id: int) -> Task:
    task = Task.query.get(entity_id)
    if task is None:
        raise ValueError(f"Task not found: {entity_id}")
    return task


def resolve_task(task_id=None, name: str = None) -> Task:
    if task_id not in (None, ""):
        return get_task(int(task_id))
    task_name = str(name or "").strip()
    if not task_name:
        raise ValueError("task_id or name is required")
    task = Task.query.filter(Task.name == task_name).one_or_none()
    if task is None:
        raise ValueError(f"Task not found: {task_name}")
    return task


def set_task_active(task_id=None, name: str = None, active: bool = True) -> Task:
    task = resolve_task(task_id=task_id, name=name)
    ok = enableJob(task.name) if active else disableJob(task.name)
    if not ok:
        raise ValueError(f"Failed to {'enable' if active else 'disable'} task: {task.name}")
    refreshed = Task.query.get(task.id)
    if refreshed is None:
        raise ValueError(f"Task not found: {task.id}")
    # Re-arm cron next run on enable (inactive tasks keep a stale runtime).
    if active and _normalize_crontab(refreshed.crontab):
        apply_schedule_fields(refreshed, {"crontab": refreshed.crontab})
        db.session.commit()
        db.session.refresh(refreshed)
    return refreshed


def run_task_code_dry(code: str, params: Optional[dict] = None) -> dict:
    validation = validate_task_code(code)
    if not validation.get("ok"):
        return {"ok": False, "validation": validation, "output": None, "success": False}
    output, success = runCode(code, args=params or {})
    return {
        "ok": success,
        "validation": validation,
        "output": output,
        "success": bool(success),
    }


def list_tasks(
    query: str = None,
    limit: int = 500,
    active_only: bool = False,
    cron_only: bool = False,
    one_shot_only: bool = False,
) -> list[dict]:
    limit = max(1, min(int(limit or 100), 5000))
    q = Task.query
    if active_only:
        q = q.filter(or_(Task.active == True, Task.active.is_(None)))  # noqa: E712
    if cron_only:
        q = q.filter(Task.crontab.isnot(None), Task.crontab != "")
    if one_shot_only:
        q = q.filter(or_(Task.crontab.is_(None), Task.crontab == ""))
    if query:
        like = f"%{query}%"
        q = q.filter(or_(Task.name.ilike(like), Task.code.ilike(like), Task.crontab.ilike(like)))
    rows = q.order_by(Task.name).limit(limit).all()
    return [task_to_dict(row) for row in rows]


def run_task_now(task_id=None, name: str = None, params: Optional[dict] = None) -> dict:
    task = resolve_task(task_id=task_id, name=name)
    result = run_task_code_dry(task.code, params=params)
    return {
        "task_id": task.id,
        "name": task.name,
        "success": bool(result.get("success")),
        "output": result.get("output"),
        "validation": result.get("validation"),
    }


def populate_task_form_datetimes(form, task: Task) -> None:
    """Fill form datetime fields from UTC DB values without mutating the ORM row.

    Mutating task.runtime/expire in-place inside session_scope() used to commit
    local wall times back into the DB as if they were UTC.
    """
    user_tz = get_user_timezone()
    if task.runtime:
        form.runtime.data = convert_utc_to_local(task.runtime, timezone=user_tz)
    if task.expire:
        form.expire.data = convert_utc_to_local(task.expire, timezone=user_tz)


def task_to_form_runtime(task: Task) -> Task:
    """Deprecated: mutates ORM. Prefer populate_task_form_datetimes()."""
    if task.runtime:
        task.runtime = convert_utc_to_local(task.runtime)
    if task.expire:
        task.expire = convert_utc_to_local(task.expire)
    return task
