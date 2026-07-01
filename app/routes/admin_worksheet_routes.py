from flask import Blueprint, request

from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.worksheet import WorkSheet
from app.models.work_entry import WorkEntry
from app.models.worker_work_entry import WorkerWorkEntry
from app.models.user import User
from app.middleware.role_required import role_required
from app.utils.query_options import apply_sort, get_search, paginate_query


admin_worksheet_bp = Blueprint(
    "admin_worksheets",
    __name__,
    url_prefix="/api/admin/worksheets"
)


@admin_worksheet_bp.route("", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def get_all_worksheets():
    query = WorkSheet.query.filter(
        WorkSheet.status == "SUBMITTED"
    )

    review_status = request.args.get("review_status")
    work_date = request.args.get("work_date")
    employee_id = request.args.get("employee_id")
    search = get_search()

    if review_status:
        query = query.filter(
            WorkSheet.review_status == review_status
        )

    if work_date:
        query = query.filter(
            WorkSheet.work_date == work_date
        )

    if employee_id:
        query = query.filter(
            WorkSheet.employee_id == employee_id
        )

    if search:
        pattern = f"%{search}%"
        query = query.join(User, WorkSheet.employee_id == User.id).filter(
            db.or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                WorkSheet.note.ilike(pattern)
            )
        )

    query = apply_sort(
        query,
        {
            "id": WorkSheet.id,
            "work_date": WorkSheet.work_date,
            "total_minutes": WorkSheet.total_minutes,
            "submitted_at": WorkSheet.submitted_at,
            "review_status": WorkSheet.review_status
        },
        "submitted_at"
    )
    worksheets, pagination = paginate_query(query)

    return {
        "success": True,
        "worksheets": [
            serialize_worksheet(worksheet)
            for worksheet in worksheets
        ],
        "pagination": pagination
    }, 200


@admin_worksheet_bp.route("/<int:worksheet_id>", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def get_worksheet_detail(worksheet_id):
    worksheet = WorkSheet.query.filter_by(
        id=worksheet_id
    ).first()

    if not worksheet:
        return {
            "success": False,
            "message": "Worksheet not found"
        }, 404

    if worksheet.status != "SUBMITTED":
        return {
            "success": False,
            "message": "Draft worksheet data is not available to admin"
        }, 404

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
        "entries": [
            serialize_entry(entry)
            for entry in entries
        ],
        "worker_entries": [
            serialize_worker_entry(entry)
            for entry in WorkerWorkEntry.query.filter_by(
                worksheet_id=worksheet.id,
                status="SUBMITTED"
            ).order_by(WorkerWorkEntry.id.asc()).all()
        ],
        "pagination": pagination
    }, 200


@admin_worksheet_bp.route("/<int:worksheet_id>/review", methods=["PATCH"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def review_worksheet(worksheet_id):
    current_user_id = int(get_jwt_identity())

    worksheet = WorkSheet.query.filter_by(
        id=worksheet_id
    ).first()

    if not worksheet:
        return {
            "success": False,
            "message": "Worksheet not found"
        }, 404

    if worksheet.status != "SUBMITTED":
        return {
            "success": False,
            "message": "Only submitted worksheet can be reviewed"
        }, 400

    current_user = User.query.filter_by(id=current_user_id).first()

    if (
        current_user
        and current_user.role.name == "ADMIN"
        and worksheet.employee_id == current_user_id
    ):
        return {
            "success": False,
            "message": "You cannot review your own worksheet"
        }, 403

    data = request.get_json()

    review_status = data.get("review_status")
    review_comment = data.get("review_comment")

    if review_status not in ["APPROVED", "REJECTED"]:
        return {
            "success": False,
            "message": "review_status must be APPROVED or REJECTED"
        }, 400

    if review_status == "REJECTED" and not (review_comment or "").strip():
        return {
            "success": False,
            "message": "Review comment is required when rejecting worksheet"
        }, 400

    worksheet.review_status = review_status
    worksheet.review_comment = review_comment
    worksheet.reviewed_by = current_user_id

    db.session.commit()

    return {
        "success": True,
        "message": "Worksheet reviewed successfully",
        "worksheet": serialize_worksheet(worksheet)
    }, 200


def serialize_worksheet(worksheet):
    return {
        "id": worksheet.id,
        "employee_id": worksheet.employee_id,
        "employee_name": worksheet.employee.full_name
        if worksheet.employee else None,
        "employee_role": worksheet.employee.role.name
        if worksheet.employee and worksheet.employee.role else None,
        "work_date": worksheet.work_date.isoformat()
        if worksheet.work_date else None,
        "total_minutes": worksheet.total_minutes,
        "note": worksheet.note,
        "status": worksheet.status,
        "submitted_at": worksheet.submitted_at.isoformat()
        if worksheet.submitted_at else None,
        "review_status": worksheet.review_status,
        "review_comment": worksheet.review_comment,
        "reviewed_by": worksheet.reviewed_by,
        "created_at": worksheet.created_at.isoformat()
        if worksheet.created_at else None
    }


def serialize_entry(entry):
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "project_name": entry.project.project_name
        if entry.project else None,
        "task_title": entry.task_title,
        "description": entry.description,
        "start_time": entry.start_time.isoformat()
        if entry.start_time else None,
        "stop_time": entry.stop_time.isoformat()
        if entry.stop_time else None,
        "total_minutes": entry.total_minutes,
        "status": entry.status
    }


def serialize_worker_entry(entry):
    return {
        "id": entry.id,
        "worker_id": entry.worker_id,
        "worker_name": entry.worker.full_name if entry.worker else None,
        "project_id": entry.project_id,
        "project_name": entry.project.project_name
        if entry.project else None,
        "work_date": entry.work_date.isoformat()
        if entry.work_date else None,
        "work_type": entry.work_type,
        "task_title": entry.task_title,
        "description": entry.description,
        "start_time": entry.start_time.isoformat()
        if entry.start_time else None,
        "end_time": entry.end_time.isoformat()
        if entry.end_time else None,
        "total_minutes": entry.total_minutes,
        "status": entry.status
    }
