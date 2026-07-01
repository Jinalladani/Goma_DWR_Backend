from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.models.worker import Worker
from app.middleware.role_required import role_required
from app.utils.query_options import apply_sort, get_search, paginate_query


worker_bp = Blueprint("workers", __name__, url_prefix="/api/workers")


@worker_bp.route("", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def get_workers():
    current_user = _current_user()
    query = Worker.query
    search = get_search()

    assigned_employee_id = request.args.get("assigned_employee_id")
    # worker_type = request.args.get("worker_type")
    is_active = request.args.get("is_active")

    if assigned_employee_id:
        query = query.filter(Worker.assigned_employee_id == assigned_employee_id)

    # if worker_type:
    #     query = query.filter(Worker.worker_type == worker_type)

    if is_active is not None:
        query = query.filter(Worker.is_active == (is_active.lower() == "true"))

    if search:
        pattern = f"%{search}%"
        query = query.join(
            User,
            Worker.assigned_employee_id == User.id
        ).filter(
            db.or_(
                Worker.full_name.ilike(pattern),
                Worker.phone.ilike(pattern),
                # Worker.worker_type.ilike(pattern),
                User.full_name.ilike(pattern)
            )
        )

    query = apply_sort(
        query,
        {
            "id": Worker.id,
            "full_name": Worker.full_name,
            # "worker_type": Worker.worker_type,
            "created_at": Worker.created_at,
            "is_active": Worker.is_active
        },
        "created_at"
    )
    workers, pagination = paginate_query(query)

    return {
        "success": True,
        "workers": [serialize_worker(worker) for worker in workers],
        "pagination": pagination
    }, 200


@worker_bp.route("", methods=["POST"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def create_worker():
    current_user = _current_user()
    data = request.get_json() or {}

    full_name = (data.get("full_name") or "").strip()
    # worker_type = (data.get("worker_type") or "").strip()

    # if not full_name:
    #     return {
    #         "success": False,
    #         "message": "Full name and worker type are required"
    #     }, 400

    phone = data.get("phone")

    if phone:
        existing_phone = Worker.query.filter_by(phone=phone).first()

        if existing_phone:
            return {
                "success": False,
                "message": "Phone number already exists"
            }, 409

    assigned_employee_id = data.get("assigned_employee_id")

    if current_user.role.name == "EMPLOYEE":
        assigned_employee_id = current_user.id
    elif not assigned_employee_id:
        return {
            "success": False,
            "message": "Assigned employee is required"
        }, 400

    employee = User.query.filter_by(id=assigned_employee_id).first()

    if not employee:
        return {"success": False, "message": "Employee not found"}, 404

    worker = Worker(
        full_name=full_name,
        phone=phone,
        # worker_type=worker_type,
        assigned_employee_id=assigned_employee_id,
        is_active=data.get("is_active", True),
        created_by=current_user.id
    )

    db.session.add(worker)
    db.session.commit()

    return {
        "success": True,
        "message": "Worker created successfully",
        "worker": serialize_worker(worker)
    }, 201


@worker_bp.route("/<int:worker_id>", methods=["PUT"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def update_worker(worker_id):
    current_user = _current_user()
    worker = _visible_worker(worker_id, current_user)

    if not worker:
        return {"success": False, "message": "Worker not found"}, 404

    data = request.get_json() or {}

    if "full_name" in data:
        full_name = (data.get("full_name") or "").strip()
        if not full_name:
            return {"success": False, "message": "Full name is required"}, 400
        worker.full_name = full_name

    if "phone" in data:
        phone = data.get("phone")

        if phone:
            existing_phone = Worker.query.filter(
                Worker.phone == phone,
                Worker.id != worker.id
            ).first()

            if existing_phone:
                return {
                    "success": False,
                    "message": "Phone number already exists"
                }, 409

        worker.phone = phone

    # if "worker_type" in data:
    #     worker_type = (data.get("worker_type") or "").strip()
    #     if not worker_type:
    #         return {"success": False, "message": "Worker type is required"}, 400
    #     worker.worker_type = worker_type

    if "assigned_employee_id" in data:
        if current_user.role.name == "EMPLOYEE":
            worker.assigned_employee_id = current_user.id
        else:
            employee = User.query.filter_by(
                id=data.get("assigned_employee_id")
            ).first()

            if not employee:
                return {"success": False, "message": "Employee not found"}, 404

            worker.assigned_employee_id = data.get("assigned_employee_id")

    if "is_active" in data:
        worker.is_active = bool(data.get("is_active"))

    db.session.commit()

    return {
        "success": True,
        "message": "Worker updated successfully",
        "worker": serialize_worker(worker)
    }, 200


@worker_bp.route("/<int:worker_id>/status", methods=["PATCH"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def update_worker_status(worker_id):
    current_user = _current_user()
    worker = _visible_worker(worker_id, current_user)

    if not worker:
        return {"success": False, "message": "Worker not found"}, 404

    data = request.get_json() or {}
    is_active = data.get("is_active")

    if is_active is None:
        return {"success": False, "message": "is_active is required"}, 400

    worker.is_active = bool(is_active)
    db.session.commit()

    return {
        "success": True,
        "message": (
            "Worker activated successfully"
            if worker.is_active else
            "Worker deactivated successfully"
        ),
        "worker": serialize_worker(worker)
    }, 200


@worker_bp.route("/<int:worker_id>", methods=["DELETE"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def delete_worker(worker_id):
    current_user = _current_user()
    worker = _visible_worker(worker_id, current_user)

    if not worker:
        return {"success": False, "message": "Worker not found"}, 404

    worker.is_active = False
    db.session.commit()

    return {
        "success": True,
        "message": "Worker deactivated successfully"
    }, 200


def _current_user():
    return User.query.filter_by(id=int(get_jwt_identity())).first()


def _visible_worker(worker_id, current_user):
    query = Worker.query.filter_by(id=worker_id)

    return query.first()


def serialize_worker(worker):
    return {
        "id": worker.id,
        "full_name": worker.full_name,
        "phone": worker.phone,
        # "worker_type": worker.worker_type,
        "assigned_employee_id": worker.assigned_employee_id,
        "assigned_employee_name": (
            worker.assigned_employee.full_name
            if worker.assigned_employee else None
        ),
        "is_active": worker.is_active,
        "created_by": worker.created_by,
        "created_at": worker.created_at.isoformat()
        if worker.created_at else None,
        "updated_at": worker.updated_at.isoformat()
        if worker.updated_at else None
    }
