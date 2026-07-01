from datetime import date

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db, bcrypt
from app.models.user import User
from app.models.role import Role
from app.models.worksheet import WorkSheet
from app.models.work_entry import WorkEntry
from app.models.project import Project
from app.middleware.role_required import role_required
from app.utils.query_options import apply_sort, get_search, paginate_query


user_bp = Blueprint("users", __name__, url_prefix="/api/users")


@user_bp.route("", methods=["POST"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def create_user():
    data = request.get_json()

    full_name = data.get("full_name")
    email = data.get("email")
    password = data.get("password")
    phone = data.get("phone")
    role_name = data.get("role")
    manager_id = data.get("manager_id")

    if not full_name or not email or not password or not role_name:
        return {"success": False, "message": "Name, email, password and role are required"}, 400

    current_user = get_current_user()

    if current_user.role.name == "ADMIN" and role_name != "EMPLOYEE":
        return {"success": False, "message": "Admin can create only employee"}, 403

    role = Role.query.filter_by(name=role_name).first()

    if not role:
        return {"success": False, "message": "Invalid role"}, 400

    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        return {"success": False, "message": "Email already exists"}, 409

    if phone:
        existing_phone = User.query.filter_by(phone=phone).first()

        if existing_phone:
            return {"success": False, "message": "Phone number already exists"}, 409

    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    user = User(
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        phone=phone,
        role_id=role.id,
        manager_id=manager_id if manager_id else current_user.id,
        is_active=True
    )

    db.session.add(user)
    db.session.commit()

    return {
        "success": True,
        "message": "User created successfully",
        "user": serialize_user(user)
    }, 201


@user_bp.route("", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def get_users():
    current_user = get_current_user()
    role = request.args.get("role")
    is_active = request.args.get("is_active")
    search = get_search()

    query = User.query

    if current_user.role.name == "ADMIN":
        query = query.join(Role).filter(Role.name.in_(["ADMIN", "EMPLOYEE"]))

    if role:
        role_obj = Role.query.filter_by(name=role).first()
        if role_obj:
            query = query.filter(User.role_id == role_obj.id)

    if is_active is not None:
        query = query.filter(User.is_active == (is_active.lower() == "true"))

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                User.phone.ilike(pattern)
            )
        )

    query = apply_sort(
        query,
        {
            "id": User.id,
            "full_name": User.full_name,
            "email": User.email,
            "created_at": User.created_at
        },
        "created_at"
    )
    users, pagination = paginate_query(query)

    return {
        "success": True,
        "users": [serialize_user(user) for user in users],
        "pagination": pagination
    }, 200


@user_bp.route("/<int:user_id>", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def get_user_detail(user_id):
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {"success": False, "message": "User not found"}, 404

    if not can_manage_user(user):
        return {"success": False, "message": "Admin can access only employees"}, 403

    return {
        "success": True,
        "user": serialize_user(user)
    }, 200


@user_bp.route("/<int:user_id>/reports", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def get_user_reports(user_id):
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {"success": False, "message": "User not found"}, 404

    if not can_manage_user(user):
        return {"success": False, "message": "Admin can access only employees"}, 403

    query = WorkEntry.query.join(WorkSheet).join(Project).filter(
        WorkEntry.employee_id == user.id,
        WorkSheet.status == "SUBMITTED",
        WorkEntry.status != "RUNNING"
    )

    search = get_search()
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                WorkEntry.task_title.ilike(pattern),
                WorkEntry.description.ilike(pattern),
                Project.project_name.ilike(pattern)
            )
        )

    total_minutes = query.with_entities(
        db.func.coalesce(db.func.sum(WorkEntry.total_minutes), 0)
    ).scalar() or 0
    query = apply_sort(
        query,
        {
            "work_date": WorkSheet.work_date,
            "total_minutes": WorkEntry.total_minutes,
            "task_title": WorkEntry.task_title,
            "created_at": WorkEntry.created_at
        },
        "work_date"
    )
    entries, pagination = paginate_query(query)
    reports = build_daily_reports(entries)

    return {
        "success": True,
        "user": serialize_user(user),
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 2),
        "reports": reports,
        "records": [
            serialize_report_entry(entry)
            for entry in entries
        ],
        "pagination": pagination
    }, 200


@user_bp.route("/<int:user_id>/report-calendar", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def get_user_report_calendar(user_id):
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {"success": False, "message": "User not found"}, 404

    if not can_manage_user(user):
        return {"success": False, "message": "Admin can access only employees"}, 403

    try:
        month = int(request.args.get("month"))
        year = int(request.args.get("year"))
    except (TypeError, ValueError):
        return {"success": False, "message": "Valid month and year are required"}, 400

    if month < 1 or month > 12:
        return {"success": False, "message": "Month must be between 1 and 12"}, 400

    start_date = date(year, month, 1)
    end_date = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    worksheets = WorkSheet.query.filter(
        WorkSheet.employee_id == user.id,
        WorkSheet.status == "SUBMITTED",
        WorkSheet.work_date >= start_date,
        WorkSheet.work_date < end_date
    ).order_by(
        WorkSheet.work_date.asc()
    ).all()

    return {
        "success": True,
        "submitted_dates": [
            worksheet.work_date.isoformat()
            for worksheet in worksheets
            if worksheet.work_date
        ],
        "reports": [
            {
                "worksheet_id": worksheet.id,
                "work_date": worksheet.work_date.isoformat(),
                "review_status": worksheet.review_status
            }
            for worksheet in worksheets
            if worksheet.work_date
        ]
    }, 200


@user_bp.route("/<int:user_id>", methods=["PUT"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def update_user(user_id):
    current_user = get_current_user()

    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {"success": False, "message": "User not found"}, 404

    if not can_manage_user(user, current_user):
        return {"success": False, "message": "Admin can manage only employees"}, 403

    data = request.get_json()

    full_name = data.get("full_name")
    phone = data.get("phone")
    role_name = data.get("role")
    manager_id = data.get("manager_id")
    is_active = data.get("is_active")

    if full_name:
        user.full_name = full_name

    if phone is not None:
        if phone:
            existing_phone = User.query.filter(
                User.phone == phone,
                User.id != user.id
            ).first()

            if existing_phone:
                return {"success": False, "message": "Phone number already exists"}, 409

        user.phone = phone

    if role_name:
        if current_user.role.name != "SUPER_ADMIN":
            return {"success": False, "message": "Only Super Admin can change role"}, 403

        role = Role.query.filter_by(name=role_name).first()

        if not role:
            return {"success": False, "message": "Invalid role"}, 400

        user.role_id = role.id

    if manager_id is not None:
        if current_user.role.name != "SUPER_ADMIN":
            return {"success": False, "message": "Only Super Admin can change manager"}, 403

        user.manager_id = manager_id

    if is_active is not None:
        user.is_active = is_active

    db.session.commit()

    return {
        "success": True,
        "message": "User updated successfully",
        "user": serialize_user(user)
    }, 200


@user_bp.route("/<int:user_id>/status", methods=["PATCH"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def update_user_status(user_id):
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {"success": False, "message": "User not found"}, 404

    if not can_manage_user(user):
        return {"success": False, "message": "Admin can manage only employees"}, 403

    data = request.get_json()
    is_active = data.get("is_active")

    if is_active is None:
        return {"success": False, "message": "is_active is required"}, 400

    user.is_active = is_active
    db.session.commit()

    return {
        "success": True,
        "message": "User status updated successfully",
        "user": serialize_user(user)
    }, 200


@user_bp.route("/<int:user_id>/reset-password", methods=["PATCH"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def reset_password(user_id):
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {"success": False, "message": "User not found"}, 404

    if not can_manage_user(user):
        return {"success": False, "message": "Admin can manage only employees"}, 403

    data = request.get_json()
    new_password = data.get("password")

    if not new_password:
        return {"success": False, "message": "Password is required"}, 400

    user.password_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
    db.session.commit()

    return {
        "success": True,
        "message": "Password reset successfully"
    }, 200


def get_current_user():
    user_id = get_jwt_identity()
    return User.query.filter_by(id=user_id).first()


def can_manage_user(user, current_user=None):
    current_user = current_user or get_current_user()

    if current_user.role.name == "SUPER_ADMIN":
        return True

    return user.role and user.role.name == "EMPLOYEE"


def serialize_user(user):
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role.name if user.role else None,
        "manager_id": user.manager_id,
        "manager_name": user.manager.full_name if user.manager else None,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }


def serialize_report_entry(entry):
    worksheet = entry.worksheet

    return {
        "id": entry.id,
        "worksheet_id": entry.worksheet_id,
        "work_date": worksheet.work_date.isoformat()
        if worksheet and worksheet.work_date else None,
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
        "status": entry.status,
        "worksheet_status": worksheet.status if worksheet else None,
        "submitted_at": worksheet.submitted_at.isoformat()
        if worksheet and worksheet.submitted_at else None
    }


def build_daily_reports(entries):
    reports_by_worksheet = {}

    for entry in entries:
        worksheet = entry.worksheet
        if not worksheet:
            continue

        if worksheet.id not in reports_by_worksheet:
            reports_by_worksheet[worksheet.id] = {
                "worksheet_id": worksheet.id,
                "work_date": worksheet.work_date.isoformat()
                if worksheet.work_date else None,
                "total_minutes": 0,
                "status": worksheet.status,
                "review_status": worksheet.review_status,
                "submitted_at": worksheet.submitted_at.isoformat()
                if worksheet.submitted_at else None,
                "note": worksheet.note,
                "entries": []
            }

        reports_by_worksheet[worksheet.id]["total_minutes"] += (
            entry.total_minutes or 0
        )
        reports_by_worksheet[worksheet.id]["entries"].append(
            serialize_report_entry(entry)
        )

    return list(reports_by_worksheet.values())
