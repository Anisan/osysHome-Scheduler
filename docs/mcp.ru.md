# MCP — Scheduler

## Collections

| ID | binding_mode | has_code | Описание |
|----|--------------|----------|----------|
| `tasks` | `none` | yes | Задачи планировщика (cron или одноразовый запуск) |

## Cron

Поддерживается синтаксис **croniter** (обычно 5 полей: `минута час день месяц день_недели`, также поддерживаются расширенные форматы с секундами — зависит от версии `croniter`).

Проверка выражения:

```json
{
  "plugin": "Scheduler",
  "action": "invoke",
  "args": {
    "operation": "validate_crontab",
    "params": {
      "crontab": "0 8 * * *",
      "preview_count": 3
    }
  }
}
```

## Примеры

### Создать cron-задачу

```json
{
  "plugin": "Scheduler",
  "action": "upsert_entity",
  "args": {
    "collection": "tasks",
    "payload": {
      "name": "daily_backup",
      "crontab": "0 3 * * *",
      "code": "say('Backup started')",
      "active": true
    }
  }
}
```

### Проверить Python-код перед сохранением

```json
{
  "plugin": "Scheduler",
  "action": "validate_entity_code",
  "args": {
    "collection": "tasks",
    "code": "say('hello')"
  }
}
```

### Dry-run кода (выполнение в песочнице runCode)

```json
{
  "plugin": "Scheduler",
  "action": "run_entity_dry",
  "args": {
    "collection": "tasks",
    "code": "say('test')",
    "context": {
      "crontab": "*/5 * * * *",
      "params": {}
    }
  }
}
```

### Отключить задачу

```json
{
  "plugin": "Scheduler",
  "action": "invoke",
  "args": {
    "operation": "disable_task",
    "params": {"task_id": 12}
  }
}
```

### Включить задачу

```json
{
  "plugin": "Scheduler",
  "action": "invoke",
  "args": {
    "operation": "enable_task",
    "params": {"name": "daily_backup"}
  }
}
```

### Только активные задачи

```json
{
  "plugin": "Scheduler",
  "action": "list_entities",
  "args": {
    "collection": "tasks",
    "active_only": true
  }
}
```
