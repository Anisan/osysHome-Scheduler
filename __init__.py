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
from app.database import session_scope, convert_local_to_utc, convert_utc_to_local, get_now_to_utc
from app.core.main.BasePlugin import BasePlugin
from app.core.models.Tasks import Task
from app.core.lib.common import runCode, clearTimeout, addCronJob, addNotify, CategoryNotify
from plugins.Scheduler.forms.TaskForm import TaskForm
from app.core.lib.crontab import nextStartCronJob
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
        self.version = "0.6"

        from plugins.Scheduler.api import create_api_ns
        api_ns = create_api_ns(self)
        api.add_namespace(api_ns, path="/Scheduler")

    def initialization(self):
        self.poolThread = MonitoredThreadPool(thread_name_prefix=self.name)
        # Настройка мониторинга
        self.poolThread.set_monitoring_callbacks(
            on_start=lambda task_id, _: self.logger.debug(f"Starting task '{task_id}'"),
            on_complete=lambda task_id, exec_time: self.logger.debug(f"Completed task '{task_id}' in {exec_time:.2f}s"),
            on_error=lambda task_id, error: self.logger.error(f"Task '{task_id}' failed: {error}"),
            on_pool_reset=lambda: addNotify("Pool reset", "Pool reset: read logs thread_pools", CategoryNotify.Warning, self.name)
        )

    def admin(self, request):
        op = request.args.get("op", None)
        tab = request.args.get("tab", "")
        if tab == "monitoring":
            stats = self.poolThread.get_monitoring_stats()
            return self.render("monitoring.html", {"stats": stats, "tab":tab})

        if op == "delete":
            tid = int(request.args.get("task", 0))
            with session_scope() as session:
                qry = delete(Task).where(Task.id == tid)
                session.execute(qry)
                session.commit()
            return redirect("Scheduler")
        elif op == "add":
            form = TaskForm()
            if form.validate_on_submit():
                tsk = Task()
                form.populate_obj(tsk)
                if form.crontab.data == "":
                    tsk.crontab = None
                    if not form.runtime.data:
                        tsk.runtime = get_now_to_utc()
                    else:
                        tsk.runtime = convert_local_to_utc(form.runtime.data)
                    if not form.expire.data:
                        tsk.expire = get_now_to_utc() + datetime.timedelta(1800)
                    else:
                        tsk.expire = convert_local_to_utc(form.expire.data)
                else:
                    dt = nextStartCronJob(tsk.crontab)
                    utc_dt = convert_local_to_utc(dt)
                    tsk.runtime = utc_dt
                    tsk.expire = utc_dt + datetime.timedelta(1800)
                with session_scope() as session:
                    session.add(tsk)
                    session.commit()
                return redirect("Scheduler")
            return self.render("task.html", {"form": form})
        elif op == "edit":
            tid = int(request.args.get("task"))
            with session_scope() as session:
                tsk = session.get(Task, tid)
                form = TaskForm(obj=tsk)
                if form.validate_on_submit():
                    form.populate_obj(tsk)
                    if form.crontab.data == "":
                        tsk.crontab = None
                        if not form.runtime.data:
                            tsk.runtime = get_now_to_utc()
                        else:
                            tsk.runtime = convert_local_to_utc(form.runtime.data)
                        if not form.expire.data:
                            tsk.expire = get_now_to_utc() + datetime.timedelta(1800)
                        else:
                            tsk.expire = convert_local_to_utc(form.expire.data)
                    else:
                        dt = nextStartCronJob(tsk.crontab)
                        utc_dt = convert_local_to_utc(dt)
                        tsk.runtime = utc_dt
                        tsk.expire = utc_dt + datetime.timedelta(1800)
                    session.commit()
                    return redirect("Scheduler")
                if form.runtime.data:
                    form.runtime.data = convert_utc_to_local(form.runtime.data)
                if form.expire.data:
                    form.expire.data = convert_utc_to_local(form.expire.data)
            return self.render("task.html", {"form": form})

        return self.render("tasks.html", {"tab":tab})

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
        if hasattr(self, '_active_tasks'):
            content['monitoring'] = self.poolThread.get_monitoring_stats()
        return render_template("widget_scheduler.html",**content)

    def cyclic_task(self):
        with session_scope() as session:
            sql = delete(Task).where(Task.expire < get_now_to_utc())
            session.execute(sql)
            session.commit()

            tasks = (
                session.query(Task)
                .filter(Task.runtime <= get_now_to_utc())
                .all()
            )
            for task in tasks:
                self.logger.debug('Running task %s', task.name)
                task.started = get_now_to_utc()
                session.commit()
                if not task.crontab:
                    clearTimeout(task.name)
                else:
                    addCronJob(task.name, task.code, task.crontab)

                def task_wrapper(code):
                    def wrapper():
                        res, success = runCode(code)
                        if not success:
                            self.logger.error(res)
                        else:
                            if res:
                                self.logger.debug(res)
                    return wrapper

                self.poolThread.submit(task_wrapper(task.code), task_id=task.name)

        self.event.wait(1.0)
