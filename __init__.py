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
import threading
import datetime
from flask import redirect, render_template
from sqlalchemy import delete, or_
from app.database import session_scope, convert_local_to_utc, convert_utc_to_local
from app.core.main.BasePlugin import BasePlugin
from app.core.models.Tasks import Task
from app.core.lib.common import runCode, clearTimeout
from plugins.Scheduler.forms.TaskForm import TaskForm
from app.core.lib.crontab import nextStartCronJob
from app.api import api


class Scheduler(BasePlugin):

    def __init__(self, app):
        super().__init__(app, __name__)
        self.title = "Sheduler"
        self.description = """This is a scheduler"""
        self.system = True
        self.actions = ['cycle','search','widget']
        self.category = "System"
        self.version = "0.4"
        
        from plugins.Scheduler.api import create_api_ns
        api_ns = create_api_ns()
        api.add_namespace(api_ns, path="/Scheduler")

    def initialization(self):
        pass

    def admin(self, request):
        op = request.args.get("op", None)
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
                        tsk.runtime = datetime.datetime.now(datetime.timezone.utc)
                    else:
                        tsk.runtime = convert_local_to_utc(form.runtime.data)
                    if not form.expire.data:
                        tsk.expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(1800)
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
                            tsk.runtime = datetime.datetime.now(datetime.timezone.utc)
                        else:
                            tsk.runtime = convert_local_to_utc(form.runtime.data)
                        if not form.expire.data:
                            tsk.expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(1800)
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

        return render_template("tasks.html")

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
        return render_template("widget_scheduler.html",**content)

    def cyclic_task(self):
        with session_scope() as session:
            sql = delete(Task).where(Task.expire < datetime.datetime.now(datetime.timezone.utc))
            session.execute(sql)
            session.commit()

            tasks = (
                session.query(Task)
                .filter(Task.runtime <= datetime.datetime.now(datetime.timezone.utc))
                .all()
            )
            for task in tasks:
                self.logger.debug('Running task %s', task.name)
                code = task.code
                task.started = datetime.datetime.now(datetime.timezone.utc)
                session.commit()
                if not task.crontab:
                    clearTimeout(task.name)
                else:
                    dt = nextStartCronJob(task.crontab)
                    utc_dt = convert_local_to_utc(dt)
                    task.runtime = utc_dt
                    task.expire = utc_dt + datetime.timedelta(1800)
                    session.commit()

                def wrapper():
                    res, success = runCode(code)
                    if not success:
                        self.logger.error(res)

                thread = threading.Thread(target=wrapper)
                thread.start()

        self.event.wait(1.0)
