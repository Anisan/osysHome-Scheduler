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
import time
import threading
import datetime
from flask import redirect, render_template
from sqlalchemy import delete, or_
from app.database import db, session_scope, row2dict
from app.core.main.BasePlugin import BasePlugin
from app.core.models.Tasks import Task
from app.core.lib.common import runCode, clearTimeout
from plugins.Scheduler.forms.TaskForm import TaskForm
from app.core.lib.crontab import nextStartCronJob


class Scheduler(BasePlugin):

    def __init__(self, app):
        super().__init__(app, __name__)
        self.title = "Sheduler"
        self.description = """This is a scheduler"""
        self.system = True
        self.actions = ['cycle','search']
        self.category = "System"
        self.version = "0.4"

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
                    tsk.cronjob = None
                    if not form.runtime.data:
                        tsk.runtime = datetime.datetime.now()
                    if not form.expire.data:
                        tsk.expire = datetime.datetime.now() + datetime.timedelta(1800)
                else:
                    dt = nextStartCronJob(tsk.crontab)
                    tsk.runtime = dt
                    tsk.expire = dt + datetime.timedelta(1800)
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
                        tsk.cronjob = None
                        if not form.runtime.data:
                            tsk.runtime = datetime.datetime.now()
                        if not form.expire.data:
                            tsk.expire = datetime.datetime.now() + datetime.timedelta(1800)
                    else:
                        dt = nextStartCronJob(tsk.crontab)
                        tsk.runtime = dt
                        tsk.expire = dt + datetime.timedelta(1800)
                    session.commit()
                    return redirect("Scheduler")
            return self.render("task.html", {"form": form})
        res = []
        with session_scope() as session:
            tasks = session.query(Task).order_by(Task.runtime).all()
            for tsk in tasks:
                res.append(row2dict(tsk))
        return render_template("tasks.html", tasks=res)

    def search(self, query: str) -> list:
        res = []
        tasks = Task.query.filter(or_(Task.name.contains(query),Task.code.contains(query))).all()
        for task in tasks:
            res.append({"url":f'Scheduler?op=edit&task={task.id}', "title":f'{task.name}', "tags":[{"name":"Task","color":"info"}]})
        return res

    def cyclic_task(self):

        sql = delete(Task).where(Task.expire < datetime.datetime.now())
        self.session.execute(sql)
        self.session.commit()

        tasks = (
            self.session.query(Task)
            .filter(Task.runtime <= datetime.datetime.now())
            .all()
        )
        for task in tasks:
            self.logger.debug('Running task %s',task.name)
            code = task.code
            task.started = datetime.datetime.now()
            self.session.commit()
            if not task.crontab:
                clearTimeout(task.name)
            else:
                dt = nextStartCronJob(task.crontab)
                task.runtime = dt
                task.expire = dt + datetime.timedelta(1800)
                self.session.commit()

            def wrapper():
                runCode(code)

            thread = threading.Thread(target=wrapper)
            thread.start()

        time.sleep(1)
