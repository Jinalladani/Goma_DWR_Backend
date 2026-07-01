from datetime import date, datetime, timezone

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.worksheet import WorkSheet
from app.models.work_entry import WorkEntry
from app.models.project import Project
from app.models.employee_project import EmployeeProject
from app.models.worker_work_entry import WorkerWorkEntry
from app.models.user import User
from app.middleware.role_required import role_required
from app.utils.time_validation import (
    combine_date_time,
    has_overlap,
    validate_not_future_datetime,
)


work_entry_bp = Blueprint(
    "work_entries",
    __name__,
    url_prefix="/api/work-entries"
)


@work_entry_bp.route("/start", methods=["POST"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def start_work():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    project_id = data.get("project_id")
    task_title = data.get("task_title")

    if not project_id or not task_title:
        return {
            "success": False,
            "message": "project_id and task_title are required"
        }, 400

    current_user = User.query.filter_by(id=user_id).first()

    if not current_user:
        return {
            "success": False,
            "message": "User not found"
        }, 404

    active_entry = WorkEntry.query.filter_by(
        employee_id=user_id,
        status="RUNNING"
    ).first()

    if active_entry:
        return {
            "success": False,
            "message": "Please stop current running entry first"
        }, 409

    project = Project.query.filter_by(
        id=project_id,
        is_active=True
    ).first()

    if not project:
        return {
            "success": False,
            "message": "Project not found or inactive"
        }, 404

    # EMPLOYEE needs assigned project access.
    # ADMIN / SUPER_ADMIN can work on any active project.
    if current_user.role and current_user.role.name == "EMPLOYEE":
        access = EmployeeProject.query.filter_by(
            employee_id=user_id,
            project_id=project_id,
            is_active=True
        ).first()

        if not access:
            return {
                "success": False,
                "message": "You do not have active access to this project"
            }, 403

    today = date.today()

    worksheet = WorkSheet.query.filter_by(
        employee_id=user_id,
        work_date=today
    ).first()

    if not worksheet:
        worksheet = WorkSheet(
            employee_id=user_id,
            work_date=today,
            status="DRAFT"
        )
        db.session.add(worksheet)
        db.session.flush()

    if worksheet.status == "SUBMITTED":
        return {
            "success": False,
            "message": "Today worksheet already submitted"
        }, 409

    entry = WorkEntry(
        worksheet_id=worksheet.id,
        employee_id=user_id,
        project_id=project_id,
        task_title=task_title,
        start_time=datetime.now(timezone.utc),
        status="RUNNING"
    )

    db.session.add(entry)
    db.session.commit()

    return {
        "success": True,
        "message": "Work started successfully",
        "entry": serialize_entry(entry)
    }, 201


@work_entry_bp.route("/stop/<int:entry_id>", methods=["PATCH"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def stop_work(entry_id):
    user_id = int(get_jwt_identity())

    entry = WorkEntry.query.filter_by(
        id=entry_id,
        employee_id=user_id
    ).first()

    if not entry:
        return {"success": False, "message": "Entry not found"}, 404

    if entry.status != "RUNNING":
        return {"success": False, "message": "Entry already stopped"}, 409

    now = datetime.now(timezone.utc)
    total_minutes = int((now - entry.start_time).total_seconds() / 60)

    entry.stop_time = now
    entry.total_minutes = total_minutes
    entry.status = "STOPPED"

    worksheet = WorkSheet.query.filter_by(id=entry.worksheet_id).first()

    if worksheet:
        worksheet.total_minutes = calculate_worksheet_total(worksheet.id)

    db.session.commit()

    return {
        "success": True,
        "message": "Work stopped successfully",
        "entry": serialize_entry(entry)
    }, 200


@work_entry_bp.route("/<int:entry_id>/description", methods=["PATCH"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def update_description(entry_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()

    entry = WorkEntry.query.filter_by(
        id=entry_id,
        employee_id=user_id
    ).first()

    if not entry:
        return {"success": False, "message": "Entry not found"}, 404

    description = (data.get("description") or "").strip()

    if not description:
        return {"success": False, "message": "Description is required"}, 400

    entry.description = description
    db.session.commit()

    return {
        "success": True,
        "message": "Description updated successfully",
        "entry": serialize_entry(entry)
    }, 200


@work_entry_bp.route("/<int:entry_id>", methods=["PUT"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def update_work_entry(entry_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()

    entry = WorkEntry.query.filter_by(
        id=entry_id,
        employee_id=user_id
    ).first()

    if not entry:
        return {"success": False, "message": "Entry not found"}, 404

    worksheet = WorkSheet.query.filter_by(id=entry.worksheet_id).first()

    if worksheet and worksheet.status == "SUBMITTED":
        return {
            "success": False,
            "message": "Cannot edit entries of a submitted worksheet"
        }, 400

    if "task_title" in data:
        entry.task_title = data.get("task_title")

    if "description" in data:
        description = (data.get("description") or "").strip()

        if not description:
            return {"success": False, "message": "Description is required"}, 400

        entry.description = description

    original_start = entry.start_time
    work_date = worksheet.work_date if worksheet else original_start.date()

    if "start_time" in data and data.get("start_time"):
        try:
            entry.start_time = combine_date_time(work_date, data.get("start_time"))
        except (TypeError, ValueError):
            return {
                "success": False,
                "message": "Invalid start_time format (expected HH:MM)"
            }, 400

    if "stop_time" in data and data.get("stop_time"):
        try:
            entry.stop_time = combine_date_time(work_date, data.get("stop_time"))
        except (TypeError, ValueError):
            return {
                "success": False,
                "message": "Invalid stop_time format (expected HH:MM)"
            }, 400

    if entry.start_time and entry.stop_time:
        validation_error = validate_not_future_datetime(
            work_date,
            entry.start_time,
            entry.stop_time
        )

        if validation_error:
            return {"success": False, "message": validation_error}, 400

        if _work_entry_overlaps(
            user_id,
            work_date,
            entry.start_time,
            entry.stop_time,
            entry.id
        ):
            return {
                "success": False,
                "message": "You already have a work entry in this time range."
            }, 400

        total_seconds = (entry.stop_time - entry.start_time).total_seconds()
        entry.total_minutes = int(total_seconds / 60)

    if worksheet:
        worksheet.total_minutes = calculate_worksheet_total(worksheet.id)

    db.session.commit()

    return {
        "success": True,
        "message": "Work entry updated successfully",
        "entry": serialize_entry(entry)
    }, 200


@work_entry_bp.route("/today", methods=["GET"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def today_entries():
    user_id = int(get_jwt_identity())

    worksheet = WorkSheet.query.filter_by(
        employee_id=user_id,
        work_date=date.today()
    ).first()

    if not worksheet:
        return {
            "success": True,
            "worksheet": None,
            "entries": []
        }, 200

    entries = WorkEntry.query.filter_by(
        worksheet_id=worksheet.id
    ).order_by(
        WorkEntry.id.asc()
    ).all()

    return {
        "success": True,
        "worksheet": serialize_worksheet(worksheet),
        "entries": [serialize_entry(entry) for entry in entries]
    }, 200


@work_entry_bp.route("/<int:entry_id>", methods=["DELETE"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def delete_entry(entry_id):
    user_id = int(get_jwt_identity())

    entry = WorkEntry.query.filter_by(
        id=entry_id,
        employee_id=user_id
    ).first()

    if not entry:
        return {"success": False, "message": "Entry not found"}, 404

    if entry.status == "RUNNING":
        return {
            "success": False,
            "message": "Running entry cannot be deleted"
        }, 409

    worksheet_id = entry.worksheet_id

    worksheet = WorkSheet.query.filter_by(id=worksheet_id).first()

    if worksheet and worksheet.status == "SUBMITTED":
        return {
            "success": False,
            "message": "Cannot delete entries of a submitted worksheet"
        }, 400

    db.session.delete(entry)
    db.session.flush()

    if worksheet:
        worksheet.total_minutes = calculate_worksheet_total(worksheet.id)

    db.session.commit()

    return {
        "success": True,
        "message": "Entry deleted successfully"
    }, 200


def calculate_worksheet_total(worksheet_id):
    entries = WorkEntry.query.filter_by(
        worksheet_id=worksheet_id
    ).all()

    worker_entries = WorkerWorkEntry.query.filter_by(
        worksheet_id=worksheet_id
    ).all()

    return sum(entry.total_minutes or 0 for entry in entries) + sum(
        entry.total_minutes or 0 for entry in worker_entries
    )


def _work_entry_overlaps(employee_id, work_date, start_time, stop_time, exclude_id=None):
    entries = (
        WorkEntry.query
        .join(WorkSheet)
        .filter(
            WorkEntry.employee_id == employee_id,
            WorkSheet.work_date == work_date,
            WorkEntry.status != "RUNNING",
            WorkEntry.stop_time.isnot(None)
        )
        .all()
    )

    return has_overlap(
        entries,
        start_time,
        stop_time,
        "start_time",
        "stop_time",
        exclude_id
    )


def serialize_entry(entry):
    return {
        "id": entry.id,
        "worksheet_id": entry.worksheet_id,
        "employee_id": entry.employee_id,
        "project_id": entry.project_id,
        "project_name": entry.project.project_name if entry.project else None,
        "task_title": entry.task_title,
        "description": entry.description,
        "start_time": entry.start_time.isoformat() if entry.start_time else None,
        "stop_time": entry.stop_time.isoformat() if entry.stop_time else None,
        "total_minutes": entry.total_minutes,
        "status": entry.status,
        "created_at": entry.created_at.isoformat() if entry.created_at else None
    }


def serialize_worksheet(worksheet):
    return {
        "id": worksheet.id,
        "employee_id": worksheet.employee_id,
        "work_date": worksheet.work_date.isoformat() if worksheet.work_date else None,
        "total_minutes": worksheet.total_minutes,
        "note": worksheet.note,
        "status": worksheet.status,
        "review_status": worksheet.review_status,
        "created_at": worksheet.created_at.isoformat() if worksheet.created_at else None
    }