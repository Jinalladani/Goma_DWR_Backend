from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.models.project import Project
from app.models.project_folder import ProjectFolder
from app.models.employee_project import EmployeeProject

from app.middleware.role_required import role_required
from app.utils.query_options import apply_sort, get_search, paginate_query


project_access_bp = Blueprint(
    "project_access",
    __name__,
    url_prefix="/api/project-access"
)


# =========================
# ASSIGN PROJECT
# =========================
@project_access_bp.route("/assign", methods=["POST"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def assign_project():

    data = request.get_json()

    employee_id = data.get("employee_id")
    project_id = data.get("project_id")

    if not employee_id or not project_id:
        return {
            "success": False,
            "message": "employee_id and project_id are required"
        }, 400

    employee = User.query.filter_by(
        id=employee_id
    ).first()

    if not employee:
        return {
            "success": False,
            "message": "Employee not found"
        }, 404

    project = Project.query.filter_by(
        id=project_id
    ).first()

    if not project:
        return {
            "success": False,
            "message": "Project not found"
        }, 404

    existing = EmployeeProject.query.filter_by(
        employee_id=employee_id,
        project_id=project_id
    ).first()

    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.session.commit()

            return {
                "success": True,
                "message": "Project access activated successfully",
                "data": serialize_access(existing)
            }, 200

        return {
            "success": False,
            "message": "Project already assigned"
        }, 409

    current_user_id = get_jwt_identity()

    access = EmployeeProject(
        employee_id=employee_id,
        project_id=project_id,
        assigned_by=current_user_id
    )

    db.session.add(access)
    db.session.commit()

    return {
        "success": True,
        "message": "Project assigned successfully",
        "data": serialize_access(access)
    }, 201


# =========================
# EMPLOYEE PROJECTS
# =========================
@project_access_bp.route("/employee/<int:employee_id>", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def employee_projects(employee_id):

    query = EmployeeProject.query.join(Project).filter(
        EmployeeProject.employee_id == employee_id
    )
    search = get_search()

    if search:
        query = query.filter(
            Project.project_name.ilike(f"%{search}%")
        )

    query = apply_sort(
        query,
        {
            "created_at": EmployeeProject.created_at,
            "project_name": Project.project_name
        },
        "created_at"
    )
    accesses, pagination = paginate_query(query)

    return {
        "success": True,
        "projects": [
            serialize_access(access)
            for access in accesses
        ],
        "pagination": pagination
    }, 200


# =========================
# MY PROJECTS
# =========================
@project_access_bp.route("/my-projects", methods=["GET"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def my_projects():

    user_id = get_jwt_identity()
    current_user = User.query.filter_by(id=user_id).first()

    if current_user and current_user.role.name in ["ADMIN", "SUPER_ADMIN"]:
        query = Project.query.outerjoin(ProjectFolder).filter(
            Project.is_active.is_(True)
        )

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
                "created_at": Project.created_at,
                "project_name": Project.project_name
            },
            "project_name",
            "asc"
        )
        projects, pagination = paginate_query(query)

        return {
            "success": True,
            "projects": [
                {
                    "id": project.id,
                    "project_id": project.id,
                    "folder_id": project.folder_id,
                    "folder_name": project.folder.folder_name if project.folder else None,
                    "project_name": project.project_name,
                    "project_code": project.project_code,
                    "is_active": project.is_active
                }
                for project in projects
            ],
            "pagination": pagination
        }, 200

    query = EmployeeProject.query.join(Project).outerjoin(ProjectFolder).filter(
        EmployeeProject.employee_id == user_id,
        EmployeeProject.is_active.is_(True),
        Project.is_active.is_(True)
    )
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
            "created_at": EmployeeProject.created_at,
            "project_name": Project.project_name
        },
        "project_name",
        "asc"
    )
    accesses, pagination = paginate_query(query)

    return {
        "success": True,
        "projects": [
            serialize_access(access)
            for access in accesses
        ],
        "pagination": pagination
    }, 200


# =========================
# UPDATE ACCESS STATUS
# =========================
@project_access_bp.route("/status/<int:access_id>", methods=["PUT"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def update_project_access_status(access_id):

    data = request.get_json()
    is_active = data.get("is_active")

    if is_active is None:
        return {
            "success": False,
            "message": "is_active is required"
        }, 400

    access = EmployeeProject.query.filter_by(
        id=access_id
    ).first()

    if not access:
        return {
            "success": False,
            "message": "Access record not found"
        }, 404

    access.is_active = bool(is_active)
    db.session.commit()

    return {
        "success": True,
        "message": (
            "Project access activated successfully"
            if access.is_active
            else "Project access deactivated successfully"
        ),
        "data": serialize_access(access)
    }, 200


# =========================
# REMOVE ACCESS
# =========================
@project_access_bp.route("/remove/<int:access_id>", methods=["DELETE"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def remove_project_access(access_id):

    access = EmployeeProject.query.filter_by(
        id=access_id
    ).first()

    if not access:
        return {
            "success": False,
            "message": "Access record not found"
        }, 404

    db.session.delete(access)
    db.session.commit()

    return {
        "success": True,
        "message": "Project access removed successfully"
    }, 200


# =========================
# SERIALIZER
# =========================
def serialize_access(access):

    return {
        "id": access.id,

        "employee_id": access.employee_id,

        "employee_name": (
            access.employee.full_name
            if access.employee else None
        ),

        "project_id": access.project_id,

        "folder_id": access.project.folder_id if access.project else None,

        "folder_name": (
            access.project.folder.folder_name
            if access.project and access.project.folder else None
        ),

        "project_name": (
            access.project.project_name
            if access.project else None
        ),

        "is_active": access.is_active,

        "assigned_by": access.assigned_by,

        "created_at": (
            access.created_at.isoformat()
            if access.created_at else None
        )
    }
