from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity
from datetime import date, datetime

from app.extensions import db
from app.models.worksheet import WorkSheet
from app.models.work_entry import WorkEntry
from app.models.worker_work_entry import WorkerWorkEntry
from app.middleware.role_required import role_required
from app.utils.query_options import apply_sort, get_search, paginate_query


worksheet_bp = Blueprint(
    "worksheets",
    __name__,
    url_prefix="/api/worksheets"
)


@worksheet_bp.route("/submit", methods=["POST"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def submit_worksheet():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    worksheet = WorkSheet.query.filter_by(
        employee_id=user_id,
        work_date=date.today()
    ).first()

    if not worksheet:
        worksheet = WorkSheet(
            employee_id=user_id,
            work_date=date.today(),
            status="DRAFT"
        )
        db.session.add(worksheet)
        db.session.flush()

    if worksheet.status == "SUBMITTED":
        return {"success": False, "message": "Worksheet already submitted"}, 409

    running_entry = WorkEntry.query.filter_by(
        worksheet_id=worksheet.id,
        status="RUNNING"
    ).first()

    if running_entry:
        return {"success": False, "message": "Please stop running entry before submit"}, 409

    normal_entries = WorkEntry.query.filter(
        WorkEntry.worksheet_id == worksheet.id,
        WorkEntry.status != "RUNNING"
    ).all()

    worker_entries = WorkerWorkEntry.query.filter_by(
        employee_id=user_id,
        work_date=worksheet.work_date,
        status="DRAFT"
    ).all()

    entries_count = len(normal_entries) + len(worker_entries)

    if entries_count == 0:
        return {"success": False, "message": "At least one work entry required"}, 400

    if any(not (entry.description or "").strip() for entry in normal_entries):
        return {"success": False, "message": "Description is required for all employee work entries"}, 400

    if any(not (entry.description or "").strip() for entry in worker_entries):
        return {"success": False, "message": "Description is required for all worker entries"}, 400

    my_work_minutes = sum(entry.total_minutes or 0 for entry in normal_entries)
    worker_work_minutes = sum(entry.total_minutes or 0 for entry in worker_entries)

    for entry in worker_entries:
        entry.status = "SUBMITTED"
        entry.worksheet_id = worksheet.id

    worksheet.note = data.get("note")
    worksheet.status = "SUBMITTED"
    worksheet.submitted_at = datetime.now()
    worksheet.review_status = "PENDING"
    worksheet.total_minutes = my_work_minutes + worker_work_minutes

    db.session.commit()

    return {
        "success": True,
        "message": "Worksheet submitted successfully",
        "worksheet": serialize_worksheet(worksheet),
        "my_work_minutes": my_work_minutes,
        "worker_work_minutes": worker_work_minutes,
        "total_minutes": worksheet.total_minutes
    }, 200


@worksheet_bp.route("/my", methods=["GET"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def my_worksheets():
    user_id = int(get_jwt_identity())

    query = WorkSheet.query.filter_by(
        employee_id=user_id
    )
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    status = request.args.get("status")
    search = get_search()

    if date_from:
        query = query.filter(WorkSheet.work_date >= date_from)

    if date_to:
        query = query.filter(WorkSheet.work_date <= date_to)

    if status:
        query = query.filter(WorkSheet.status == status)

    if search:
        query = query.filter(WorkSheet.note.ilike(f"%{search}%"))

    query = apply_sort(
        query,
        {
            "id": WorkSheet.id,
            "work_date": WorkSheet.work_date,
            "total_minutes": WorkSheet.total_minutes,
            "submitted_at": WorkSheet.submitted_at,
            "status": WorkSheet.status
        },
        "work_date"
    )
    worksheets, pagination = paginate_query(query)

    return {
        "success": True,
        "worksheets": [serialize_worksheet(ws) for ws in worksheets],
        "pagination": pagination
    }, 200


@worksheet_bp.route("/<int:worksheet_id>", methods=["GET"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def worksheet_detail(worksheet_id):
    user_id = int(get_jwt_identity())

    worksheet = WorkSheet.query.filter_by(id=worksheet_id).first()

    if not worksheet:
        return {"success": False, "message": "Worksheet not found"}, 404

    if worksheet.employee_id != user_id:
        return {"success": False, "message": "Permission denied"}, 403

    query = WorkEntry.query.filter_by(
        worksheet_id=worksheet.id
    )
    search = get_search()

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                WorkEntry.task_title.ilike(pattern),
                WorkEntry.description.ilike(pattern)
            )
        )

    query = apply_sort(
        query,
        {
            "id": WorkEntry.id,
            "task_title": WorkEntry.task_title,
            "total_minutes": WorkEntry.total_minutes,
            "start_time": WorkEntry.start_time
        },
        "id",
        "asc"
    )
    entries, pagination = paginate_query(query)

    return {
        "success": True,
        "worksheet": serialize_worksheet(worksheet),
        "entries": [serialize_entry(entry) for entry in entries],
        "worker_entries": [
            serialize_worker_entry(entry)
            for entry in WorkerWorkEntry.query.filter_by(
                worksheet_id=worksheet.id
            ).order_by(WorkerWorkEntry.id.asc()).all()
        ],
        "pagination": pagination
    }, 200


def serialize_worksheet(worksheet):
    return {
        "id": worksheet.id,
        "employee_id": worksheet.employee_id,
        "employee_name": worksheet.employee.full_name if worksheet.employee else None,
        "work_date": worksheet.work_date.isoformat() if worksheet.work_date else None,
        "total_minutes": worksheet.total_minutes,
        "note": worksheet.note,
        "status": worksheet.status,
        "submitted_at": worksheet.submitted_at.isoformat() if worksheet.submitted_at else None,
        "review_status": worksheet.review_status,
        "review_comment": worksheet.review_comment,
        "created_at": worksheet.created_at.isoformat() if worksheet.created_at else None
    }


def serialize_entry(entry):
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "project_name": entry.project.project_name if entry.project else None,
        "task_title": entry.task_title,
        "description": entry.description,
        "start_time": entry.start_time.isoformat() if entry.start_time else None,
        "stop_time": entry.stop_time.isoformat() if entry.stop_time else None,
        "total_minutes": entry.total_minutes,
        "status": entry.status
    }


def serialize_worker_entry(entry):
    return {
        "id": entry.id,
        "worker_id": entry.worker_id,
        "worker_name": entry.worker.full_name if entry.worker else None,
        "project_id": entry.project_id,
        "project_name": entry.project.project_name if entry.project else None,
        "work_date": entry.work_date.isoformat() if entry.work_date else None,
        "work_type": entry.work_type,
        "task_title": entry.task_title,
        "description": entry.description,
        "start_time": entry.start_time.isoformat() if entry.start_time else None,
        "end_time": entry.end_time.isoformat() if entry.end_time else None,
        "total_minutes": entry.total_minutes,
        "status": entry.status
    }
