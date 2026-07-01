from datetime import date, datetime, time, timezone

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.employee_project import EmployeeProject
from app.models.project import Project
from app.models.worksheet import WorkSheet
from app.models.worker import Worker
from app.models.worker_work_entry import WorkerWorkEntry
from app.middleware.role_required import role_required
from app.utils.time_validation import (
    has_overlap,
    validate_not_future_datetime,
)
from app.utils.query_options import apply_sort, get_search, paginate_query


worker_entry_bp = Blueprint(
    "worker_entries",
    __name__,
    url_prefix="/api/worker-entries"
)


@worker_entry_bp.route("/today", methods=["GET"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def today_worker_entries():
    user_id = int(get_jwt_identity())

    entries = (
        WorkerWorkEntry.query
        .filter(
            WorkerWorkEntry.employee_id == user_id,
            WorkerWorkEntry.work_date == date.today()
        )
        .order_by(WorkerWorkEntry.id.asc())
        .all()
    )

    return {
        "success": True,
        "entries": [serialize_worker_entry(entry) for entry in entries]
    }, 200


@worker_entry_bp.route("", methods=["GET"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def get_worker_entries():
    user_id = int(get_jwt_identity())
    query = WorkerWorkEntry.query.filter(
        WorkerWorkEntry.employee_id == user_id
    )
    search = get_search()

    work_date = request.args.get("work_date")
    worker_id = request.args.get("worker_id")
    status = request.args.get("status")

    if work_date:
        query = query.filter(WorkerWorkEntry.work_date == work_date)

    if worker_id:
        query = query.filter(WorkerWorkEntry.worker_id == worker_id)

    if status:
        query = query.filter(WorkerWorkEntry.status == status)

    if search:
        pattern = f"%{search}%"
        query = query.join(Worker).filter(
            db.or_(
                Worker.full_name.ilike(pattern),
                WorkerWorkEntry.task_title.ilike(pattern),
                WorkerWorkEntry.description.ilike(pattern),
                WorkerWorkEntry.work_type.ilike(pattern)
            )
        )

    query = apply_sort(
        query,
        {
            "id": WorkerWorkEntry.id,
            "work_date": WorkerWorkEntry.work_date,
            "start_time": WorkerWorkEntry.start_time,
            "total_minutes": WorkerWorkEntry.total_minutes
        },
        "start_time",
        "asc"
    )
    entries, pagination = paginate_query(query)

    return {
        "success": True,
        "entries": [serialize_worker_entry(entry) for entry in entries],
        "pagination": pagination
    }, 200


@worker_entry_bp.route("", methods=["POST"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def create_worker_entry():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    parsed = _parse_entry_payload(data)

    if parsed.get("error"):
        return {"success": False, "message": parsed["error"]}, 400

    validation_error = validate_not_future_datetime(
        parsed["work_date"],
        parsed["start_time"],
        parsed["end_time"]
    )

    if validation_error:
        return {"success": False, "message": validation_error}, 400

    if _worker_entry_overlaps(
        parsed["worker_id"],
        parsed["work_date"],
        parsed["start_time"],
        parsed["end_time"]
    ):
        return {
            "success": False,
            "message": "This worker already has an entry in this time range."
        }, 400

    worker = _active_worker_for_user(parsed["worker_id"], user_id)

    if not worker:
        return {
            "success": False,
            "message": "Worker not found or inactive"
        }, 404

    project = Project.query.filter_by(
        id=parsed["project_id"],
        is_active=True
    ).first()

    if not project:
        return {"success": False, "message": "Project not found or inactive"}, 404

    access = EmployeeProject.query.filter_by(
        employee_id=user_id,
        project_id=parsed["project_id"],
        is_active=True
    ).first()

    if not access:
        return {
            "success": False,
            "message": "You do not have active access to this project"
        }, 403

    worksheet = _get_or_create_worksheet(user_id, parsed["work_date"])

    if worksheet.status == "SUBMITTED":
        return {
            "success": False,
            "message": "Cannot add worker entry to a submitted worksheet"
        }, 400

    entry = WorkerWorkEntry(
        worker_id=worker.id,
        employee_id=user_id,
        project_id=project.id,
        worksheet_id=worksheet.id,
        work_date=parsed["work_date"],
        work_type=parsed["work_type"],
        task_title=parsed["task_title"],
        description=parsed["description"],
        start_time=parsed["start_time"],
        end_time=parsed["end_time"],
        total_minutes=parsed["total_minutes"],
        status="DRAFT"
    )

    db.session.add(entry)
    db.session.flush()
    worksheet.total_minutes = _calculate_worksheet_total(worksheet.id)
    db.session.commit()

    return {
        "success": True,
        "message": "Worker entry saved successfully",
        "entry": serialize_worker_entry(entry)
    }, 201


@worker_entry_bp.route("/<int:entry_id>", methods=["PUT"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def update_worker_entry(entry_id):
    user_id = int(get_jwt_identity())
    entry = WorkerWorkEntry.query.filter_by(
        id=entry_id,
        employee_id=user_id
    ).first()

    if not entry:
        return {"success": False, "message": "Worker entry not found"}, 404

    worksheet = WorkSheet.query.filter_by(id=entry.worksheet_id).first()

    if entry.status == "SUBMITTED" or (worksheet and worksheet.status == "SUBMITTED"):
        return {
            "success": False,
            "message": "Cannot edit entries of a submitted worksheet"
        }, 400

    data = request.get_json() or {}
    parsed = _parse_entry_payload(data, partial=True, current_entry=entry)

    if parsed.get("error"):
        return {"success": False, "message": parsed["error"]}, 400

    if "worker_id" in parsed:
        worker = _active_worker_for_user(parsed["worker_id"], user_id)
        if not worker:
            return {"success": False, "message": "Worker not found or inactive"}, 404
        entry.worker_id = worker.id

    if "project_id" in parsed:
        project = Project.query.filter_by(
            id=parsed["project_id"],
            is_active=True
        ).first()
        if not project:
            return {"success": False, "message": "Project not found or inactive"}, 404

        access = EmployeeProject.query.filter_by(
            employee_id=user_id,
            project_id=project.id,
            is_active=True
        ).first()
        if not access:
            return {
                "success": False,
                "message": "You do not have active access to this project"
            }, 403

        entry.project_id = project.id

    for key in [
        "work_date",
        "work_type",
        "task_title",
        "description",
        "start_time",
        "end_time",
        "total_minutes"
    ]:
        if key in parsed:
            setattr(entry, key, parsed[key])

    if worksheet and worksheet.work_date != entry.work_date:
        new_worksheet = _get_or_create_worksheet(user_id, entry.work_date)
        entry.worksheet_id = new_worksheet.id
        worksheet.total_minutes = _calculate_worksheet_total(worksheet.id)
        worksheet = new_worksheet

    validation_error = validate_not_future_datetime(
        entry.work_date,
        entry.start_time,
        entry.end_time
    )

    if validation_error:
        return {"success": False, "message": validation_error}, 400

    if _worker_entry_overlaps(
        entry.worker_id,
        entry.work_date,
        entry.start_time,
        entry.end_time,
        entry.id
    ):
        return {
            "success": False,
            "message": "This worker already has an entry in this time range."
        }, 400

    if worksheet:
        worksheet.total_minutes = _calculate_worksheet_total(worksheet.id)

    db.session.commit()

    return {
        "success": True,
        "message": "Worker entry updated successfully",
        "entry": serialize_worker_entry(entry)
    }, 200


@worker_entry_bp.route("/<int:entry_id>", methods=["DELETE"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def delete_worker_entry(entry_id):
    user_id = int(get_jwt_identity())
    entry = WorkerWorkEntry.query.filter_by(
        id=entry_id,
        employee_id=user_id
    ).first()

    if not entry:
        return {"success": False, "message": "Worker entry not found"}, 404

    worksheet = WorkSheet.query.filter_by(id=entry.worksheet_id).first()

    if entry.status == "SUBMITTED" or (worksheet and worksheet.status == "SUBMITTED"):
        return {
            "success": False,
            "message": "Cannot delete entries of a submitted worksheet"
        }, 400

    worksheet_id = entry.worksheet_id
    db.session.delete(entry)
    db.session.flush()

    worksheet = WorkSheet.query.filter_by(id=worksheet_id).first()
    if worksheet:
        worksheet.total_minutes = _calculate_worksheet_total(worksheet.id)

    db.session.commit()

    return {
        "success": True,
        "message": "Worker entry deleted successfully"
    }, 200


def _parse_entry_payload(data, partial=False, current_entry=None):
    required = [
        "worker_id",
        "project_id",
        "work_date",
        "work_type",
        "task_title",
        "start_time",
        "end_time",
        "description"
    ]

    if not partial:
        missing = [
            field for field in required
            if data.get(field) in [None, ""]
        ]
        if missing:
            return {"error": "Worker, project, work type, task, date and time are required"}

    parsed = {}

    for int_field in ["worker_id", "project_id"]:
        if int_field in data and data.get(int_field) not in [None, ""]:
            try:
                parsed[int_field] = int(data.get(int_field))
            except (TypeError, ValueError):
                return {"error": f"Invalid {int_field}"}

    work_date = current_entry.work_date if current_entry else None
    if "work_date" in data and data.get("work_date"):
        try:
            work_date = date.fromisoformat(data.get("work_date"))
            parsed["work_date"] = work_date
        except ValueError:
            return {"error": "Invalid work_date format"}

    start_source = data.get("start_time")
    end_source = data.get("end_time")

    start_time = current_entry.start_time if current_entry else None
    end_time = current_entry.end_time if current_entry else None

    if start_source:
        start_time = _parse_datetime_or_time(start_source, work_date)
        if not start_time:
            return {"error": "Invalid start_time format"}
        parsed["start_time"] = start_time

    if end_source:
        end_time = _parse_datetime_or_time(end_source, work_date)
        if not end_time:
            return {"error": "Invalid end_time format"}
        parsed["end_time"] = end_time

    if "work_type" in data:
        work_type = (data.get("work_type") or "").strip()
        if not work_type:
            return {"error": "Work type is required"}
        parsed["work_type"] = work_type

    if "task_title" in data:
        task_title = (data.get("task_title") or "").strip()
        if not task_title:
            return {"error": "Task title is required"}
        parsed["task_title"] = task_title

    if "description" in data:
        description = (data.get("description") or "").strip()

        if not description:
            return {"error": "Description is required"}

        parsed["description"] = description
    elif not partial:
        return {"error": "Description is required"}

    if work_date and start_time and end_time:
        if end_time <= start_time:
            return {"error": "End time must be greater than start time"}

        parsed["total_minutes"] = int(
            (end_time - start_time).total_seconds() / 60
        )

    return parsed


def _parse_datetime_or_time(value, work_date):
    try:
        dt = None
        if "T" in value:
            dt = datetime.fromisoformat(value)
        elif len(value) == 5:
            hour, minute = map(int, value.split(":"))
            dt = datetime.combine(work_date, time(hour=hour, minute=minute), tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(value)

        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _active_worker_for_user(worker_id, user_id):
    return Worker.query.filter_by(
        id=worker_id,
        is_active=True
    ).first()


def _worker_entry_overlaps(worker_id, work_date, start_time, end_time, exclude_id=None):
    entries = WorkerWorkEntry.query.filter(
        WorkerWorkEntry.worker_id == worker_id,
        WorkerWorkEntry.work_date == work_date
    ).all()

    return has_overlap(
        entries,
        start_time,
        end_time,
        "start_time",
        "end_time",
        exclude_id
    )


def _get_or_create_worksheet(user_id, work_date):
    worksheet = WorkSheet.query.filter_by(
        employee_id=user_id,
        work_date=work_date
    ).first()

    if worksheet:
        return worksheet

    worksheet = WorkSheet(
        employee_id=user_id,
        work_date=work_date,
        status="DRAFT"
    )
    db.session.add(worksheet)
    db.session.flush()
    return worksheet


def _calculate_worksheet_total(worksheet_id):
    from app.models.work_entry import WorkEntry

    normal_entries = WorkEntry.query.filter(
        WorkEntry.worksheet_id == worksheet_id,
        WorkEntry.status != "RUNNING"
    ).all()
    worker_entries = WorkerWorkEntry.query.filter_by(
        worksheet_id=worksheet_id
    ).all()

    return sum(entry.total_minutes or 0 for entry in normal_entries) + sum(
        entry.total_minutes or 0 for entry in worker_entries
    )


def serialize_worker_entry(entry):
    return {
        "id": entry.id,
        "worker_id": entry.worker_id,
        "worker_name": entry.worker.full_name if entry.worker else None,
        "employee_id": entry.employee_id,
        "employee_name": entry.employee.full_name if entry.employee else None,
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
        "status": entry.status,
        "created_at": entry.created_at.isoformat()
        if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat()
        if entry.updated_at else None
    }
