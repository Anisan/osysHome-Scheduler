"""
# Sheduler plugin

Plugin for completing tasks on time

Supports:

- cyclical execution of tasks
- add,edit,delete tasks
- Cron syntax
- second-by-second execution
- global search

"""
import datetime
from flask import redirect, render_template
from sqlalchemy import delete, or_
from app.database import session_scope, get_now_to_utc, get_user_timezone
from app.core.main.BasePlugin import BasePlugin
from app.core.models.Tasks import Task
from app.core.lib.common import (
    runCode,
    clearTimeout,
    addCronJob,
    addNotify,
    CategoryNotify,
    writeSystemStatsMetric,
    incrementSystemStatsMetric,
)
from app.core.lib.constants import PropertyType
from plugins.Scheduler.forms.TaskForm import TaskForm
from plugins.Scheduler.services import task_service
from app.api import api
from app.core.MonitoredThreadPool import MonitoredThreadPool

class Scheduler(BasePlugin):

    def __init__(self, app):
        super().__init__(app, __name__)
        self.title = "Scheduler"
        self.description = """This is a scheduler"""
        self.system = True
        self.actions = ['cycle','search','widget']
        self.category = "System"
        self.version = "0.10"

        from plugins.Scheduler.api import create_api_ns
        api_ns = create_api_ns(self)
        api.add_namespace(api_ns, path="/Scheduler")

    def initialization(self):
        self.poolThread = MonitoredThreadPool(thread_name_prefix=self.name)
        self.poolThread.set_monitoring_callbacks(
            on_start=self._on_pool_task_start,
            on_complete=self._on_pool_task_complete,
            on_error=self._on_pool_task_error,
            on_pool_reset=self._on_pool_reset,
        )

    def _on_pool_task_start(self, task_id, _):
        self.logger.debug("Starting task '%s'", task_id)
        incrementSystemStatsMetric(self.name, "tasks_started_total", 1)

    def _on_pool_task_complete(self, task_id, exec_time):
        self.logger.debug("Completed task '%s' in %.2fs", task_id, exec_time)
        incrementSystemStatsMetric(self.name, "tasks_completed_total", 1)
        writeSystemStatsMetric(
            self.name,
            "last_task_duration_sec",
            round(exec_time, 3),
            prop_type=PropertyType.Float,
        )

    def _on_pool_task_error(self, task_id, error):
        self.logger.error("Task '%s' failed: %s", task_id, error)
        incrementSystemStatsMetric(self.name, "tasks_failed_total", 1)

    def _on_pool_reset(self):
        addNotify("Pool reset", "Pool reset: read logs thread_pools", CategoryNotify.Warning, self.name)
        incrementSystemStatsMetric(self.name, "pool_resets_total", 1)

    def _publish_pool_stats(self):
        try:
            stats = self.poolThread.get_monitoring_stats()
            tp = stats.get("thread_pool", {})
            et = stats.get("execution_time", {})
            plugin = self.name
            writeSystemStatsMetric(plugin, "pool_queue_size", tp.get("queue_size", 0), prop_type=PropertyType.Integer)
            writeSystemStatsMetric(
                plugin,
                "pool_active_tasks",
                len(tp.get("active_tasks") or {}),
                prop_type=PropertyType.Integer,
            )
            writeSystemStatsMetric(
                plugin,
                "pool_utilization_pct",
                round(float(tp.get("pool_utilization") or 0), 2),
                prop_type=PropertyType.Float,
            )
            writeSystemStatsMetric(
                plugin,
                "pool_completed_tasks",
                int(tp.get("completed_tasks") or 0),
                prop_type=PropertyType.Integer,
            )
            writeSystemStatsMetric(
                plugin,
                "pool_failed_tasks",
                int(tp.get("failed_tasks") or 0),
                prop_type=PropertyType.Integer,
            )
            writeSystemStatsMetric(
                plugin,
                "pool_rejected_tasks",
                int(tp.get("rejected_tasks") or 0),
                prop_type=PropertyType.Integer,
            )
            writeSystemStatsMetric(
                plugin,
                "pool_avg_execution_sec",
                round(float(et.get("avg_execution_time") or 0), 3),
                prop_type=PropertyType.Float,
            )
        except Exception as ex:
            self.logger.debug("SystemStats pool publish failed: %s", ex)

    def _publish_task_inventory(self, session):
        try:
            plugin = self.name
            writeSystemStatsMetric(
                plugin,
                "tasks_total",
                session.query(Task).count(),
                prop_type=PropertyType.Integer,
            )
            writeSystemStatsMetric(
                plugin,
                "tasks_active",
                session.query(Task).filter(or_(Task.active == True, Task.active.is_(None))).count(),
                prop_type=PropertyType.Integer,
            )
            writeSystemStatsMetric(
                plugin,
                "tasks_cron",
                session.query(Task).filter(Task.crontab.isnot(None), Task.crontab != "").count(),
                prop_type=PropertyType.Integer,
            )
        except Exception as ex:
            self.logger.debug("SystemStats task inventory failed: %s", ex)

    def admin(self, request):
        op = request.args.get("op", None)
        tab = request.args.get("tab", "")
        if tab == "monitoring":
            stats = self.poolThread.get_monitoring_stats()
            return self.render("monitoring.html", {"stats": stats, "tab":tab})

        if op == "delete":
            tid = int(request.args.get("task", 0))
            task_service.delete_task(tid)
            return redirect("Scheduler")
        elif op == "add":
            form = TaskForm()
            if form.validate_on_submit():
                task_service.save_task({
                    "name": form.name.data,
                    "code": form.code.data,
                    "crontab": form.crontab.data or "",
                    "runtime": form.runtime.data,
                    "expire": form.expire.data,
                    "active": form.active.data,
                })
                return redirect("Scheduler")
            return self.render("task.html", {"form": form})
        elif op == "edit":
            tid = int(request.args.get("task"))
            tsk = Task.query.get(tid)
            if tsk is None:
                return redirect("Scheduler")
            form = TaskForm(obj=tsk)
            # Convert UTC→local only on the form (do not dirty the ORM row).
            if not form.is_submitted():
                task_service.populate_task_form_datetimes(form, tsk)
            if form.validate_on_submit():
                task_service.save_task({
                    "name": form.name.data,
                    "code": form.code.data,
                    "crontab": form.crontab.data or "",
                    "runtime": form.runtime.data,
                    "expire": form.expire.data,
                    "active": form.active.data,
                }, entity_id=tid)
                return redirect("Scheduler")
            return self.render("task.html", {"form": form})

        return self.render("tasks.html", {"tab": tab, "display_timezone": get_user_timezone()})

    def search(self, query: str) -> list:
        res = []
        tasks = Task.query.filter(or_(Task.name.contains(query),Task.code.contains(query))).all()
        for task in tasks:
            res.append({"url":f'Scheduler?op=edit&task={task.id}', "title": f'{task.name}', "tags": [{"name":"Task","color":"info"}]})
        return res

    def widget(self):
        content = {}
        with session_scope() as session:
            content['crontab'] = session.query(Task).filter(Task.crontab is not None, Task.crontab != '').count()
            content['count'] = session.query(Task).count()
            content['active'] = session.query(Task).filter(or_(Task.active == True, Task.active.is_(None))).count()
        if hasattr(self, '_active_tasks'):
            content['monitoring'] = self.poolThread.get_monitoring_stats()
        return render_template("widget_scheduler.html",**content)

    def cyclic_task(self):
        incrementSystemStatsMetric(self.name, "cycle_runs_total", 1)
        plugin = self.name
        with session_scope() as session:
            sql = delete(Task).where(Task.expire < get_now_to_utc(), or_(Task.active == True, Task.active.is_(None)))
            expired_result = session.execute(sql)
            expired_count = expired_result.rowcount or 0
            if expired_count:
                incrementSystemStatsMetric(plugin, "tasks_expired_deleted_total", expired_count)
            session.commit()
            session.expire_all()

            tasks = (
                session.query(Task)
                .filter(Task.runtime <= get_now_to_utc())
                .filter(or_(Task.active == True, Task.active.is_(None)))
                .all()
            )
            writeSystemStatsMetric(plugin, "tasks_due_count", len(tasks), prop_type=PropertyType.Integer)
            for task in tasks:
                task_name = None
                try:
                    task_name = task.name
                    task_code = task.code
                    task_crontab = task.crontab

                    self.logger.debug('Running task %s', task_name)
                    incrementSystemStatsMetric(plugin, "tasks_dispatched_total", 1)

                    if task_crontab:
                        task.started = get_now_to_utc()
                        session.commit()
                        addCronJob(task_name, task_code, task_crontab)
                    else:
                        clearTimeout(task_name)
                        session.expire_all()

                    def task_wrapper(code):
                        def wrapper():
                            res, success = runCode(code)
                            if not success:
                                self.logger.error(res)
                                incrementSystemStatsMetric(plugin, "task_script_errors_total", 1)
                            else:
                                if res:
                                    self.logger.debug(res)
                        return wrapper

                    self.poolThread.submit(task_wrapper(task_code), task_id=task_name)
                except RuntimeError as ex:
                    if "queue size" in str(ex).lower():
                        incrementSystemStatsMetric(plugin, "tasks_rejected_total", 1)
                    if not task_name:
                        try:
                            task_name = task.name
                        except Exception:
                            task_name = '(unknown)'
                    self.logger.error(
                        'Error processing task %s: %s',
                        task_name,
                        ex,
                        exc_info=True,
                    )
                except Exception as ex:
                    incrementSystemStatsMetric(plugin, "dispatch_errors_total", 1)
                    if not task_name:
                        try:
                            task_name = task.name
                        except Exception:
                            task_name = '(unknown)'
                    self.logger.error(
                        'Error processing task %s: %s',
                        task_name,
                        ex,
                        exc_info=True,
                    )

            self._publish_task_inventory(session)

        self._publish_pool_stats()
        self.event.wait(1.0)

    # --- MCP integration ---

    def mcp_capabilities(self):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_capabilities()

    def mcp_config_schema(self):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_config_schema()

    def mcp_entity_schema(self, collection: str):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_entity_schema(collection)

    def mcp_list_entities(
        self,
        collection: str,
        query: str = None,
        limit: int = 100,
        active_only=None,
        cron_only=None,
        one_shot_only=None,
    ):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_list_entities(
            collection,
            query=query,
            limit=limit,
            active_only=active_only,
            cron_only=cron_only,
            one_shot_only=one_shot_only,
        )

    def mcp_get_entity(self, collection: str, entity_id):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_get_entity(collection, entity_id)

    def mcp_upsert_entity(self, collection: str, payload: dict, entity_id=None):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_upsert_entity(collection, payload, entity_id=entity_id)

    def mcp_delete_entity(self, collection: str, entity_id):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_delete_entity(collection, entity_id)

    def mcp_validate_entity_code(self, collection: str, code: str):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_validate_entity_code(collection, code)

    def mcp_run_entity_dry(self, collection: str, code: str, context: dict = None):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_run_entity_dry(collection, code, context=context)

    def mcp_invoke(self, operation: str, params: dict = None):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_invoke(operation, params or {})

    def mcp_entity_revision(self, collection: str, entity_id):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_entity_revision(collection, entity_id)

    def mcp_validate_entity(self, collection: str, payload: dict, entity_id=None):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_validate_entity(collection, payload, entity_id=entity_id)

    def mcp_tools(self):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_descriptors()[0]

    def mcp_resources(self):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_descriptors()[1]

    def mcp_prompts(self):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_descriptors()[2]

    def mcp_get_prompt(self, name: str, arguments: dict = None):
        from plugins.Scheduler import mcp_support
        return mcp_support.mcp_get_prompt(name, arguments or {})
