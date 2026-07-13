# MCP — Scheduler

Плагин выполняет Python-код по расписанию (cron или одноразовый запуск). Для runtime-операций используйте `invoke`.

## Plugin notes

- Код задач выполняется через `runCode` (та же песочница, что у методов объектов).
- **Cron-задача:** задайте `crontab` (синтаксис croniter, обычно 5 полей). `runtime`/`expire` пересчитываются при сохранении.
- **Одноразовая задача:** оставьте `crontab` пустым; задайте `runtime` (локальное время). `expire` по умолчанию = runtime + 30 мин.
- Перед upsert проверяйте cron через `validate_crontab` (preview `next_runs`).
- Перед сохранением тестируйте код: `validate_entity_code` и `run_entity_dry`.
- `enable_task` / `disable_task` вызывают `enableJob`/`disableJob`.
- `run_task_now` — немедленный запуск кода без изменения расписания.
- `get_pool_stats` — статистика пула потоков планировщика.
- Поле `started` выставляется при dispatch cron-задачи (**read-only** через MCP).

## Collections

| ID | binding_mode | has_code | Описание |
|----|--------------|----------|----------|
| `tasks` | `none` | yes | Задачи планировщика (cron или одноразовый запуск) |

### Фильтры list_entities

| Параметр | Описание |
|----------|----------|
| `query` | Поиск по name, code, crontab |
| `active_only` | Только активные задачи |
| `cron_only` | Только задачи с crontab |
| `one_shot_only` | Только одноразовые задачи (без crontab) |

## Операции (invoke)

| operation | Описание |
|-----------|----------|
| `enable_task` | Включить задачу (`task_id` или `name`) |
| `disable_task` | Отключить задачу |
| `validate_crontab` | Проверить cron и показать ближайшие запуски |
| `run_task_now` | Немедленно выполнить сохранённый Python-код задачи |
| `get_pool_stats` | Статистика пула потоков планировщика |

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

### Немедленно выполнить задачу

```json
{
  "plugin": "Scheduler",
  "action": "invoke",
  "args": {
    "operation": "run_task_now",
    "params": {"name": "daily_backup", "params": {}}
  }
}
```

### Статистика пула потоков

```json
{
  "plugin": "Scheduler",
  "action": "invoke",
  "args": {
    "operation": "get_pool_stats",
    "params": {}
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

### Только активные cron-задачи

```json
{
  "plugin": "Scheduler",
  "action": "list_entities",
  "args": {
    "collection": "tasks",
    "active_only": true,
    "cron_only": true
  }
}
```
