from flask import request
from flask_restx import Namespace, Resource
from app.api.decorators import api_key_required
from app.authentication.handlers import handle_admin_required
from app.api.models import model_404, model_result
from plugins.Scheduler.services import task_service
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
        result = task_service.list_tasks()
        return {"success": True, "result": result}, 200


@_api_ns.route("/task/<task_id>", endpoint="scheduer_task")
class EndpointTask(Resource):
    @api_key_required
    @handle_admin_required
    def get(self,task_id: int):
        """ Get task """
        try:
            task = task_service.get_task(int(task_id))
            return {"success": True, "result": task_service.task_to_dict(task)}, 200
        except ValueError:
            return {"success": False, "msg": "Task not found"}, 404
    @api_key_required
    @handle_admin_required
    def post(self,task_id):
        """ Create/update task """
        data = request.get_json() or {}
        entity_id = int(task_id) if data.get("id") else None
        task = task_service.save_task(data, entity_id=entity_id)
        return {"success": True, "result": task_service.task_to_dict(task)}, 200
    @api_key_required
    @handle_admin_required
    def delete(self,task_id):
        """ Delete task """
        task_service.delete_task(int(task_id))
        return {"success": True}, 200

@_api_ns.route("/task/<task_id>/enable", endpoint="scheduler_task_enable")
class EnableTask(Resource):
    @api_key_required
    @handle_admin_required
    @_api_ns.doc(security="apikey")
    @_api_ns.response(200, "Task enabled", response_result)
    def post(self, task_id: int):
        """Enable task"""
        try:
            task = task_service.set_task_active(task_id=task_id, active=True)
            return {"success": True, "msg": "Task enabled", "result": task_service.task_to_dict(task)}, 200
        except ValueError as ex:
            if "not found" in str(ex).lower():
                return {"success": False, "msg": "Task not found"}, 404
            return {"success": False, "msg": str(ex)}, 500


@_api_ns.route("/task/<task_id>/disable", endpoint="scheduler_task_disable")
class DisableTask(Resource):
    @api_key_required
    @handle_admin_required
    @_api_ns.doc(security="apikey")
    @_api_ns.response(200, "Task disabled", response_result)
    def post(self, task_id: int):
        """Disable task"""
        try:
            task = task_service.set_task_active(task_id=task_id, active=False)
            return {"success": True, "msg": "Task disabled", "result": task_service.task_to_dict(task)}, 200
        except ValueError as ex:
            if "not found" in str(ex).lower():
                return {"success": False, "msg": "Task not found"}, 404
            return {"success": False, "msg": str(ex)}, 500


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
