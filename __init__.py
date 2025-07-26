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
import concurrent.futures
from threading import Lock
import datetime
from flask import redirect, render_template
from sqlalchemy import delete, or_
from app.database import session_scope, convert_local_to_utc, convert_utc_to_local, get_now_to_utc
from app.core.main.BasePlugin import BasePlugin
from app.core.models.Tasks import Task
from app.core.lib.common import runCode, clearTimeout
from plugins.Scheduler.forms.TaskForm import TaskForm
from app.core.lib.crontab import nextStartCronJob
from app.api import api
from collections import deque


class Scheduler(BasePlugin):

    def __init__(self, app):
        super().__init__(app, __name__)
        self.title = "Scheduler"
        self.description = """This is a scheduler"""
        self.system = True
        self.actions = ['cycle','search','widget']
        self.category = "System"
        self.version = "0.5"

        from plugins.Scheduler.api import create_api_ns
        api_ns = create_api_ns(self)
        api.add_namespace(api_ns, path="/Scheduler")

    def initialization(self):
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)
        self._executor_lock = Lock()
        # Мониторинг пула потоков
        self._active_tasks = 0
        self._completed_tasks = 0
        self._failed_tasks = 0
        self._max_concurrent_tasks = 0

        # Мониторинг времени выполнения
        self._execution_times = deque(maxlen=100)
        self._total_execution_time = 0
        self._avg_execution_time = 0
        self._min_execution_time = float('inf')
        self._max_execution_time = 0

        # История для графиков (последние 100 записей)
        self._execution_history = []
        self._task_count_history = []

    def admin(self, request):
        op = request.args.get("op", None)
        tab = request.args.get("tab", "")
        if tab == "monitoring":
            stats = self.get_monitoring_stats()
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
            content['monitoring'] = self.get_monitoring_stats()
        return render_template("widget_scheduler.html",**content)

    def get_monitoring_stats(self):
        """Получение полной статистики мониторинга"""
        with self._executor_lock:
            return {
                'thread_pool': {
                    'max_workers': self._executor._max_workers,
                    'active_tasks': self._active_tasks,
                    'completed_tasks': self._completed_tasks,
                    'failed_tasks': self._failed_tasks,
                    'max_concurrent_tasks': self._max_concurrent_tasks,
                    'queue_size': len(self._executor._work_queue.queue) if hasattr(self._executor._work_queue, 'queue') else 0
                },
                'execution_time': {
                    'avg_execution_time': round(self._avg_execution_time, 3) if self._avg_execution_time else 0,
                    'min_execution_time': round(self._min_execution_time, 3) if self._min_execution_time != float('inf') else 0,
                    'max_execution_time': round(self._max_execution_time, 3),
                    'total_execution_time': round(self._total_execution_time, 3)
                },
                'history': {
                    'execution_times': self._execution_history,
                    'task_counts': self._task_count_history
                }
            }

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
                code = task.code
                task_name = task.name
                task.started = get_now_to_utc()
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
                    import time
                    start_time = time.time()

                    # Увеличиваем счетчик активных задач
                    with self._executor_lock:
                        self._active_tasks += 1
                        if self._active_tasks > self._max_concurrent_tasks:
                            self._max_concurrent_tasks = self._active_tasks

                    try:
                        res, success = runCode(code)
                        execution_time = time.time() - start_time

                        # Обновляем статистику времени выполнения
                        with self._executor_lock:
                            if len(self._execution_times) == 100:  
                                self._total_execution_time -= self._execution_times[0]  

                            self._execution_times.append(execution_time)  
                            self._total_execution_time += execution_time  

                            if self._execution_times:  
                                self._min_execution_time = min(self._execution_times)  
                                self._max_execution_time = max(self._execution_times)  
                                self._avg_execution_time = self._total_execution_time / len(self._execution_times)
                            
                            # Добавляем в историю для графиков
                            self._execution_history.append({
                                'time': time.time(),
                                'duration': execution_time,
                                'task_name': task_name,
                                'success': success
                            })

                            if success:
                                self._completed_tasks += 1
                            else:
                                self._failed_tasks += 1

                        if not success:
                            self.logger.error('Task "%s" failed after %.3f seconds: %s',
                                            task_name, execution_time, res)
                        else:
                            self.logger.info('Task "%s" completed in %.3f seconds',
                                        task_name, execution_time)

                    except Exception as e:
                        execution_time = time.time() - start_time
                        with self._executor_lock:
                            self._failed_tasks += 1
                        self.logger.error('Task "%s" crashed after %.3f seconds: %s',
                                        task_name, execution_time, str(e))
                    finally:
                        # Уменьшаем счетчик активных задач
                        with self._executor_lock:
                            self._active_tasks -= 1

                with self._executor_lock:
                    self._executor.submit(wrapper)

        self.event.wait(1.0)
