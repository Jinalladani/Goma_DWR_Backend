from datetime import date

from flask import Blueprint

from app.extensions import db
from app.models.user import User
from app.models.role import Role
from app.models.project import Project
from app.models.worksheet import WorkSheet
from app.models.work_entry import WorkEntry

from app.middleware.role_required import role_required


dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/api/dashboard"
)


# ======================================================
# SUPER ADMIN DASHBOARD
# ======================================================
@dashboard_bp.route("/super-admin", methods=["GET"])
@role_required(["SUPER_ADMIN"])
def super_admin_dashboard():

    total_users = User.query.count()

    total_admins = (
        User.query
        .join(Role)
        .filter(Role.name == "ADMIN")
        .count()
    )

    total_employees = (
        User.query
        .join(Role)
        .filter(Role.name == "EMPLOYEE")
        .count()
    )

    total_projects = Project.query.count()

    total_worksheets = WorkSheet.query.filter(
        WorkSheet.status == "SUBMITTED"
    ).count()

    approved_worksheets = WorkSheet.query.filter(
        WorkSheet.review_status == "APPROVED",
        WorkSheet.status == "SUBMITTED"
    ).count()

    rejected_worksheets = WorkSheet.query.filter(
        WorkSheet.review_status == "REJECTED",
        WorkSheet.status == "SUBMITTED"
    ).count()

    submitted_worksheets = WorkSheet.query.filter(
        WorkSheet.status == "SUBMITTED"
    ).count()

    return {
        "success": True,
        "data": {
            "total_users": total_users,
            "total_admins": total_admins,
            "total_employees": total_employees,
            "total_projects": total_projects,
            "total_worksheets": total_worksheets,
            "submitted_worksheets": submitted_worksheets,
            "approved_worksheets": approved_worksheets,
            "rejected_worksheets": rejected_worksheets
        }
    }, 200


# ======================================================
# ADMIN DASHBOARD
# ======================================================
@dashboard_bp.route("/admin", methods=["GET"])
@role_required(["ADMIN", "SUPER_ADMIN"])
def admin_dashboard():
    today = date.today()

    total_employees = (
        User.query
        .join(Role)
        .filter(Role.name == "EMPLOYEE")
        .count()
    )

    total_projects = Project.query.count()

    active_projects = Project.query.filter(
        Project.is_active.is_(True)
    ).count()

    submitted_reports = WorkSheet.query.filter(
        WorkSheet.status == "SUBMITTED"
    ).count()

    approved_reports = WorkSheet.query.filter(
        WorkSheet.status == "SUBMITTED",
        WorkSheet.review_status == "APPROVED"
    ).count()

    rejected_reports = WorkSheet.query.filter(
        WorkSheet.status == "SUBMITTED",
        WorkSheet.review_status == "REJECTED"
    ).count()

    pending_reports = WorkSheet.query.filter(
        WorkSheet.status == "SUBMITTED",
        WorkSheet.review_status == "PENDING"
    ).count()

    today_submissions = WorkSheet.query.filter(
        WorkSheet.status == "SUBMITTED",
        WorkSheet.work_date == today
    ).count()

    today_total_minutes = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(WorkEntry.total_minutes),
                0
            )
        )
        .join(WorkSheet)
        .filter(
            WorkSheet.status == "SUBMITTED",
            WorkSheet.work_date == today,
            WorkEntry.status != "RUNNING"
        )
        .scalar()
    ) or 0

    total_hours_minutes = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(WorkEntry.total_minutes),
                0
            )
        )
        .join(WorkSheet)
        .filter(
            WorkSheet.status == "SUBMITTED"
        )
        .scalar()
    ) or 0

    return {
        "success": True,
        "data": {
            "total_employees": total_employees,
            "total_projects": total_projects,
            "active_projects": active_projects,
            "submitted_reports": submitted_reports,
            "approved_reports": approved_reports,
            "rejected_reports": rejected_reports,
            "pending_reports": pending_reports,
            "today_submissions": today_submissions,
            "today_total_minutes": today_total_minutes,
            "total_hours_minutes": total_hours_minutes,
            "total_hours_text": minutes_to_text(total_hours_minutes)
        }
    }, 200


# ======================================================
# EMPLOYEE DASHBOARD
# ======================================================
@dashboard_bp.route("/employee", methods=["GET"])
@role_required(["EMPLOYEE"])
def employee_dashboard():

    from flask_jwt_extended import get_jwt_identity

    employee_id = int(get_jwt_identity())

    total_minutes = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(WorkEntry.total_minutes),
                0
            )
        )
        .join(WorkSheet)
        .filter(
            WorkEntry.employee_id == employee_id,
            WorkSheet.status == "SUBMITTED"
        )
        .scalar()
    ) or 0

    total_entries = (
        WorkEntry.query
        .join(WorkSheet)
        .filter(
            WorkEntry.employee_id == employee_id,
            WorkSheet.status == "SUBMITTED"
        )
        .count()
    )

    active_projects = (
        db.session.query(
            db.func.count(
                db.distinct(WorkEntry.project_id)
            )
        )
        .join(WorkSheet)
        .filter(
            WorkEntry.employee_id == employee_id,
            WorkSheet.status == "SUBMITTED"
        )
        .scalar()
    ) or 0

    return {
        "success": True,
        "data": {
            "total_minutes": total_minutes,
            "total_hours_text": minutes_to_text(total_minutes),
            "total_entries": total_entries,
            "active_projects": active_projects
        }
    }, 200


# ======================================================
# COMMON
# ======================================================
def minutes_to_text(minutes):

    total = int(minutes or 0)

    hours = total // 60
    mins = total % 60

    return (
        f"{str(hours).zfill(2)}h "
        f"{str(mins).zfill(2)}m"
    )
