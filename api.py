from flask import request
from flask_restx import Namespace, Resource
from sqlalchemy import delete
from app.api.decorators import api_key_required
from app.authentication.handlers import handle_admin_required
from app.api.models import model_404, model_result
from app.core.models.Tasks import Task
from app.database import row2dict, session_scope, convert_local_to_utc
from plugins.Scheduler import Scheduler

_api_ns = Namespace(name="Scheduler", description="Scheduler namespace", validate=True)

response_result = _api_ns.model("Result", model_result)
response_404 = _api_ns.model("Error", model_404)

_instance: Scheduler = None

def create_api_ns(instance:Scheduler):
    global _instance
    _instance = instance
    return _api_ns


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
            result = [row2dict(task) for task in tasks]
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
                result = row2dict(task)
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
            task.started = convert_local_to_utc(data['started'])
            task.crontab = convert_local_to_utc(data['crontab'])
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

@_api_ns.route("/monitoring", endpoint="scheduler_monitoring")  
class GetMonitoring(Resource):  
    @api_key_required  
    @handle_admin_required  
    @_api_ns.doc(security="apikey")  
    @_api_ns.response(200, "Monitoring stats", response_result)  
    def get(self):  
        """Получение статистики мониторинга"""  
        stats = _instance.get_monitoring_stats()  
        return {"success": True, "result": stats}, 200  
