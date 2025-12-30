from flask import request
from flask_restx import Namespace, Resource
from sqlalchemy import delete
from app.api.decorators import api_key_required
from app.authentication.handlers import handle_admin_required
from app.api.models import model_404, model_result
from app.core.models.Tasks import Task
from app.database import row2dict, session_scope, convert_local_to_utc
from app.core.lib.common import enableJob, disableJob
from plugins.Scheduler import Scheduler

_api_ns = Namespace(name="Scheduler", description="Scheduler namespace", validate=True)

response_result = _api_ns.model("Result", model_result)
response_404 = _api_ns.model("Error", model_404)

_instance: Scheduler = None

def create_api_ns(instance:Scheduler):
    global _instance
    _instance = instance
    return _api_ns


def normalize_task_data(task_dict):
    """Normalize task data: convert active=None to True"""
    if task_dict.get('active') is None:
        task_dict['active'] = True
    return task_dict


@_api_ns.route("/tasks", endpoint="scheduer_tasks")
class GetTasks(Resource):
    @api_key_required
    @handle_admin_required
    @_api_ns.doc(security="apikey")
    @_api_ns.response(200, "List tasks", response_result)
    def get(self):
        """
        Get tasks
        """
        with session_scope() as session:
            tasks = session.query(Task).all()
            result = [normalize_task_data(row2dict(task)) for task in tasks]
            return {"success": True, "result": result}, 200


@_api_ns.route("/task/<task_id>", endpoint="scheduer_task")
class EndpointTask(Resource):
    @api_key_required
    @handle_admin_required
    def get(self,task_id: int):
        """ Get task """
        with session_scope() as session:
            task = session.query(Task).filter(Task.id == task_id).one_or_none()
            if task:
                result = normalize_task_data(row2dict(task))
                return {"success": True, "result": result}, 200
            return {"success": False, "msg": "Task not found"}, 404
    @api_key_required
    @handle_admin_required
    def post(self,task_id):
        """ Create/update task """
        with session_scope() as session:
            data = request.get_json()
            if data["id"]:
                task = session.query(Task).filter(Task.id == task_id).one()
            else:
                task = Task()
                session.add(task)
            task.name = data['name']
            task.code = data['code']
            task.expire = data['expire']
            task.runtime = convert_local_to_utc(data['runtime'])
            if data.get('started'):
                task.started = convert_local_to_utc(data['started'])
            task.crontab = data.get('crontab')
            task.active = data.get('active', True) if 'active' in data else True
            session.commit()
            return {"success": True}, 200
    @api_key_required
    @handle_admin_required
    def delete(self,task_id):
        """ Delete task """
        with session_scope() as session:
            sql = delete(Task).where(Task.id == task_id)
            session.execute(sql)
            session.commit()
            return {"success": True}, 200

@_api_ns.route("/task/<task_id>/enable", endpoint="scheduler_task_enable")
class EnableTask(Resource):
    @api_key_required
    @handle_admin_required
    @_api_ns.doc(security="apikey")
    @_api_ns.response(200, "Task enabled", response_result)
    def post(self, task_id: int):
        """Enable task"""
        with session_scope() as session:
            task = session.query(Task).filter(Task.id == task_id).one_or_none()
            if task:
                if enableJob(task.name):
                    return {"success": True, "msg": "Task enabled"}, 200
                return {"success": False, "msg": "Failed to enable task"}, 500
            return {"success": False, "msg": "Task not found"}, 404


@_api_ns.route("/task/<task_id>/disable", endpoint="scheduler_task_disable")
class DisableTask(Resource):
    @api_key_required
    @handle_admin_required
    @_api_ns.doc(security="apikey")
    @_api_ns.response(200, "Task disabled", response_result)
    def post(self, task_id: int):
        """Disable task"""
        with session_scope() as session:
            task = session.query(Task).filter(Task.id == task_id).one_or_none()
            if task:
                if disableJob(task.name):
                    return {"success": True, "msg": "Task disabled"}, 200
                return {"success": False, "msg": "Failed to disable task"}, 500
            return {"success": False, "msg": "Task not found"}, 404


@_api_ns.route("/monitoring", endpoint="scheduler_monitoring")
class GetMonitoring(Resource):
    @api_key_required
    @handle_admin_required
    @_api_ns.doc(security="apikey")
    @_api_ns.response(200, "Monitoring stats", response_result)
    def get(self):
        """Получение статистики мониторинга"""
        stats = _instance.poolThread.get_monitoring_stats()
        return {"success": True, "result": stats}, 200
