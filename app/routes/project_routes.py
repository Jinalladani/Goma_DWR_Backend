from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.project import Project
from app.models.project_folder import ProjectFolder
from app.models.worksheet import WorkSheet
from app.models.work_entry import WorkEntry
from app.models.worker_work_entry import WorkerWorkEntry
from app.models.user import User
from app.middleware.role_required import role_required
from app.utils.query_options import apply_sort, get_search, paginate_list, paginate_query


project_bp = Blueprint(
    "projects",
    __name__,
    url_prefix="/api/projects"
)


@project_bp.route("", methods=["POST"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def create_project():
    data = request.get_json()

    project_name = data.get("project_name")
    project_code = data.get("project_code")
    description = data.get("description")
    folder_id = data.get("folder_id")

    if not folder_id:
        return {
            "success": False,
            "message": "Project folder is required"
        }, 400

    folder = ProjectFolder.query.filter_by(
        id=folder_id,
        is_active=True
    ).first()

    if not folder:
        return {
            "success": False,
            "message": "Active project folder not found"
        }, 404

    if not project_name:
        return {
            "success": False,
            "message": "Project name is required"
        }, 400

    if not project_code:
        return {
            "success": False,
            "message": "Project code is required"
        }, 400

    project_code = project_code.strip()

    existing_project = Project.query.filter_by(
        project_code=project_code
    ).first()

    if existing_project:
        return {
            "success": False,
            "message": "Project code already exists"
        }, 409

    user_id = get_jwt_identity()

    project = Project(
        folder_id=folder_id,
        project_name=project_name,
        project_code=project_code,
        description=description,
        created_by=user_id,
        is_active=True
    )

    db.session.add(project)
    db.session.commit()

    return {
        "success": True,
        "message": "Project created successfully",
        "project": serialize_project(project)
    }, 201


@project_bp.route("", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def get_projects():
    query = Project.query.outerjoin(ProjectFolder)
    search = get_search()
    folder_id = request.args.get("folder_id", type=int)

    if folder_id:
        query = query.filter(Project.folder_id == folder_id)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                Project.project_name.ilike(pattern),
                Project.project_code.ilike(pattern),
                Project.description.ilike(pattern),
                ProjectFolder.folder_name.ilike(pattern)
            )
        )

    query = apply_sort(
        query,
        {
            "id": Project.id,
            "project_name": Project.project_name,
            "project_code": Project.project_code,
            "created_at": Project.created_at,
            "is_active": Project.is_active,
            "folder_name": ProjectFolder.folder_name
        },
        "created_at"
    )
    projects, pagination = paginate_query(query)

    return {
        "success": True,
        "projects": [
            serialize_project(project)
            for project in projects
        ],
        "pagination": pagination
    }, 200


@project_bp.route("/active", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def get_active_projects():
    query = Project.query.outerjoin(ProjectFolder).filter(Project.is_active.is_(True))
    search = get_search()
    folder_id = request.args.get("folder_id", type=int)

    if folder_id:
        query = query.filter(Project.folder_id == folder_id)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                Project.project_name.ilike(pattern),
                Project.project_code.ilike(pattern),
                ProjectFolder.folder_name.ilike(pattern)
            )
        )

    query = apply_sort(
        query,
        {
            "project_name": Project.project_name,
            "project_code": Project.project_code,
            "created_at": Project.created_at
        },
        "project_name",
        "asc"
    )
    projects, pagination = paginate_query(query)

    return {
        "success": True,
        "projects": [
            serialize_project(project)
            for project in projects
        ],
        "pagination": pagination
    }, 200


@project_bp.route("/<int:project_id>", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def get_project_detail(project_id):
    project = Project.query.filter_by(
        id=project_id
    ).first()

    if not project:
        return {
            "success": False,
            "message": "Project not found"
        }, 404

    return {
        "success": True,
        "project": serialize_project(project)
    }, 200


@project_bp.route("/<int:project_id>/report", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def get_project_report(project_id):
    project = Project.query.filter_by(
        id=project_id
    ).first()

    if not project:
        return {
            "success": False,
            "message": "Project not found"
        }, 404

    entries_query = (
        WorkEntry.query
        .join(WorkSheet)
        .filter(
            WorkEntry.project_id == project_id,
            WorkSheet.status == "SUBMITTED",
            WorkEntry.status != "RUNNING"
        )
    )
    search = get_search()

    if search:
        pattern = f"%{search}%"
        entries_query = entries_query.join(
            User, WorkEntry.employee_id == User.id
        ).filter(
            db.or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern)
            )
        )

    entries = entries_query.all()

    worker_entries_query = (
        WorkerWorkEntry.query
        .join(WorkSheet)
        .filter(
            WorkerWorkEntry.project_id == project_id,
            WorkerWorkEntry.status == "SUBMITTED",
            WorkSheet.status == "SUBMITTED"
        )
    )

    if search:
        pattern = f"%{search}%"
        worker_entries_query = worker_entries_query.join(
            User, WorkerWorkEntry.employee_id == User.id
        ).filter(
            db.or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern)
            )
        )

    worker_entries = worker_entries_query.all()

    normal_total_minutes = sum(entry.total_minutes or 0 for entry in entries)
    worker_total_minutes = sum(entry.total_minutes or 0 for entry in worker_entries)
    total_minutes = normal_total_minutes + worker_total_minutes
    total_hours = round(total_minutes / 60, 2)
    approved_total_minutes = _sum_by_review_status(
        entries,
        worker_entries,
        "APPROVED"
    )
    rejected_total_minutes = _sum_by_review_status(
        entries,
        worker_entries,
        "REJECTED"
    )

    employee_summary = {}

    for entry in entries:
        emp = entry.employee

        if not emp:
            continue

        if emp.id not in employee_summary:
            employee_summary[emp.id] = {
                "employee_id": emp.id,
                "name": emp.full_name,
                "email": emp.email,
                "own_work_minutes": 0,
                "own_work_hours": 0.0,
                "worker_work_minutes": 0,
                "worker_work_hours": 0.0,
                "total_minutes": 0,
                "total_hours": 0.0,
                "entry_count": 0,
                "worker_entry_count": 0,
                "report_count": 0,
                "worksheet_ids": set()
            }

        employee_summary[emp.id]["own_work_minutes"] += (
            entry.total_minutes or 0
        )
        employee_summary[emp.id]["total_minutes"] += (
            entry.total_minutes or 0
        )
        employee_summary[emp.id]["entry_count"] += 1
        employee_summary[emp.id]["worksheet_ids"].add(
            entry.worksheet_id
        )

    worker_ids = set()

    for entry in worker_entries:
        emp = entry.employee

        if not emp:
            continue

        worker_ids.add(entry.worker_id)

        if emp.id not in employee_summary:
            employee_summary[emp.id] = {
                "employee_id": emp.id,
                "name": emp.full_name,
                "email": emp.email,
                "own_work_minutes": 0,
                "own_work_hours": 0.0,
                "worker_work_minutes": 0,
                "worker_work_hours": 0.0,
                "total_minutes": 0,
                "total_hours": 0.0,
                "entry_count": 0,
                "worker_entry_count": 0,
                "report_count": 0,
                "worksheet_ids": set()
            }

        employee_summary[emp.id]["worker_work_minutes"] += (
            entry.total_minutes or 0
        )
        employee_summary[emp.id]["total_minutes"] += (
            entry.total_minutes or 0
        )
        employee_summary[emp.id]["worker_entry_count"] += 1
        employee_summary[emp.id]["worksheet_ids"].add(
            entry.worksheet_id
        )

    summary_list = []

    for summary in employee_summary.values():
        summary["total_hours"] = round(
            summary["total_minutes"] / 60,
            2
        )
        summary["own_work_hours"] = round(
            summary["own_work_minutes"] / 60,
            2
        )
        summary["worker_work_hours"] = round(
            summary["worker_work_minutes"] / 60,
            2
        )
        summary["report_count"] = len(summary["worksheet_ids"])
        del summary["worksheet_ids"]

        summary_list.append(summary)

    sort_by = request.args.get("sort_by", "total_minutes")
    order = (request.args.get("order", "desc") or "desc").lower()
    sort_keys = {
        "name": lambda item: (item["name"] or "").lower(),
        "email": lambda item: (item["email"] or "").lower(),
        "total_minutes": lambda item: item["total_minutes"],
        "entry_count": lambda item: item["entry_count"],
        "report_count": lambda item: item["report_count"]
    }
    summary_list.sort(
        key=sort_keys.get(sort_by, sort_keys["total_minutes"]),
        reverse=order != "asc"
    )
    summary_list, pagination = paginate_list(summary_list)

    return {
        "success": True,
        "project": serialize_project(project),
        "normal_total_minutes": normal_total_minutes,
        "worker_total_minutes": worker_total_minutes,
        "total_minutes": total_minutes,
        "submitted_total_minutes": total_minutes,
        "approved_total_minutes": approved_total_minutes,
        "rejected_total_minutes": rejected_total_minutes,
        "total_hours": total_hours,
        "workers_worked": len(worker_ids),
        "employees": summary_list,
        "pagination": pagination
    }, 200


@project_bp.route("/<int:project_id>/report/employee/<int:employee_id>", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def get_project_employee_report(project_id, employee_id):
    project = Project.query.filter_by(id=project_id).first()

    if not project:
        return {
            "success": False,
            "message": "Project not found"
        }, 404

    employee = User.query.filter_by(id=employee_id).first()

    if not employee:
        return {
            "success": False,
            "message": "Employee not found"
        }, 404

    entries = (
        WorkEntry.query
        .join(WorkSheet)
        .filter(
            WorkEntry.project_id == project_id,
            WorkEntry.employee_id == employee_id,
            WorkEntry.status != "RUNNING",
            WorkSheet.status == "SUBMITTED"
        )
        .order_by(WorkEntry.start_time.asc())
        .all()
    )

    worker_entries = (
        WorkerWorkEntry.query
        .join(WorkSheet)
        .filter(
            WorkerWorkEntry.project_id == project_id,
            WorkerWorkEntry.employee_id == employee_id,
            WorkerWorkEntry.status == "SUBMITTED",
            WorkSheet.status == "SUBMITTED"
        )
        .order_by(WorkerWorkEntry.start_time.asc())
        .all()
    )

    own_work_minutes = sum(entry.total_minutes or 0 for entry in entries)
    worker_work_minutes = sum(entry.total_minutes or 0 for entry in worker_entries)
    total_minutes = own_work_minutes + worker_work_minutes

    return {
        "success": True,
        "project": serialize_project(project),
        "employee": {
            "id": employee.id,
            "name": employee.full_name,
            "email": employee.email
        },
        "entries": [
            serialize_report_entry(entry)
            for entry in entries
        ],
        "worker_entries": [
            serialize_worker_report_entry(entry)
            for entry in worker_entries
        ],
        "summary": {
            "own_work_minutes": own_work_minutes,
            "worker_work_minutes": worker_work_minutes,
            "total_minutes": total_minutes,
            "entry_count": len(entries) + len(worker_entries)
        }
    }, 200


@project_bp.route("/<int:project_id>", methods=["PUT"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def update_project(project_id):
    project = Project.query.filter_by(
        id=project_id
    ).first()

    if not project:
        return {
            "success": False,
            "message": "Project not found"
        }, 404

    data = request.get_json()

    project_name = data.get("project_name")
    project_code = data.get("project_code")
    description = data.get("description")
    folder_id = data.get("folder_id")
    is_active = data.get("is_active")

    if project_name:
        project.project_name = project_name

    if project_code is not None:
        project_code = project_code.strip()

        if not project_code:
            return {
                "success": False,
                "message": "Project code is required"
            }, 400

        existing_project = Project.query.filter(
            Project.project_code == project_code,
            Project.id != project.id
        ).first()

        if existing_project:
            return {
                "success": False,
                "message": "Project code already exists"
            }, 409

        project.project_code = project_code

    if description is not None:
        project.description = description

    if folder_id is not None:
        if not folder_id:
            return {
                "success": False,
                "message": "Project folder is required"
            }, 400

        folder = ProjectFolder.query.filter_by(
            id=folder_id,
            is_active=True
        ).first()

        if not folder:
            return {
                "success": False,
                "message": "Active project folder not found"
            }, 404

        project.folder_id = folder_id

    if is_active is not None:
        project.is_active = is_active

    db.session.commit()

    return {
        "success": True,
        "message": "Project updated successfully",
        "project": serialize_project(project)
    }, 200


@project_bp.route("/<int:project_id>", methods=["DELETE"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def delete_project(project_id):
    project = Project.query.filter_by(
        id=project_id
    ).first()

    if not project:
        return {
            "success": False,
            "message": "Project not found"
        }, 404

    project.is_active = False

    db.session.commit()

    return {
        "success": True,
        "message": "Project deleted successfully"
    }, 200


def serialize_project(project):
    return {
        "id": project.id,
        "folder_id": project.folder_id,
        "folder_name": project.folder.folder_name if project.folder else None,
        "project_name": project.project_name,
        "project_code": project.project_code,
        "description": project.description,
        "created_by": project.created_by,
        "is_active": project.is_active,
        "status": "Active" if project.is_active else "Inactive",
        "start_date": getattr(project, "start_date", None).isoformat()
        if getattr(project, "start_date", None) else None,
        "end_date": getattr(project, "end_date", None).isoformat()
        if getattr(project, "end_date", None) else None,
        "created_at": project.created_at.isoformat()
        if project.created_at else None
    }


def serialize_report_entry(entry):
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "project_name": entry.project.project_name if entry.project else None,
        "worksheet_id": entry.worksheet_id,
        "work_date": entry.worksheet.work_date.isoformat()
        if entry.worksheet and entry.worksheet.work_date else None,
        "task_title": entry.task_title,
        "description": entry.description,
        "start_time": entry.start_time.isoformat() if entry.start_time else None,
        "stop_time": entry.stop_time.isoformat() if entry.stop_time else None,
        "total_minutes": entry.total_minutes,
        "review_status": entry.worksheet.review_status
        if entry.worksheet else None,
        "type": "EMPLOYEE"
    }


def serialize_worker_report_entry(entry):
    return {
        "id": entry.id,
        "worker_id": entry.worker_id,
        "worker_name": entry.worker.full_name if entry.worker else None,
        "project_id": entry.project_id,
        "project_name": entry.project.project_name if entry.project else None,
        "worksheet_id": entry.worksheet_id,
        "work_date": entry.work_date.isoformat() if entry.work_date else None,
        "work_type": entry.work_type,
        "task_title": entry.task_title,
        "description": entry.description,
        "start_time": entry.start_time.isoformat() if entry.start_time else None,
        "end_time": entry.end_time.isoformat() if entry.end_time else None,
        "total_minutes": entry.total_minutes,
        "review_status": entry.worksheet.review_status
        if entry.worksheet else None,
        "type": "WORKER"
    }


def _sum_by_review_status(entries, worker_entries, review_status):
    normal_minutes = sum(
        entry.total_minutes or 0
        for entry in entries
        if entry.worksheet and entry.worksheet.review_status == review_status
    )
    worker_minutes = sum(
        entry.total_minutes or 0
        for entry in worker_entries
        if entry.worksheet and entry.worksheet.review_status == review_status
    )
    return normal_minutes + worker_minutes
