from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.project_folder import ProjectFolder
from app.middleware.role_required import role_required
from app.utils.query_options import apply_sort, get_search, paginate_query


project_folder_bp = Blueprint(
    "project_folders",
    __name__,
    url_prefix="/api/project-folders"
)


@project_folder_bp.route("", methods=["POST"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def create_project_folder():
    data = request.get_json() or {}

    folder_name = (data.get("folder_name") or "").strip()
    description = data.get("description")

    if not folder_name:
        return {
            "success": False,
            "message": "Folder name is required"
        }, 400

    existing_folder = ProjectFolder.query.filter(
        db.func.lower(ProjectFolder.folder_name) == folder_name.lower()
    ).first()

    if existing_folder:
        return {
            "success": False,
            "message": "Folder name already exists"
        }, 409

    folder = ProjectFolder(
        folder_name=folder_name,
        description=description,
        created_by=get_jwt_identity(),
        is_active=True
    )

    db.session.add(folder)
    db.session.commit()

    return {
        "success": True,
        "message": "Project folder created successfully",
        "folder": serialize_project_folder(folder)
    }, 201


@project_folder_bp.route("", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def get_project_folders():
    query = ProjectFolder.query
    search = get_search()
    is_active = request.args.get("is_active")

    if is_active is not None:
        query = query.filter(ProjectFolder.is_active.is_(is_active.lower() == "true"))

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                ProjectFolder.folder_name.ilike(pattern),
                ProjectFolder.description.ilike(pattern)
            )
        )

    query = apply_sort(
        query,
        {
            "id": ProjectFolder.id,
            "folder_name": ProjectFolder.folder_name,
            "created_at": ProjectFolder.created_at,
            "is_active": ProjectFolder.is_active
        },
        "created_at"
    )
    folders, pagination = paginate_query(query)

    return {
        "success": True,
        "folders": [serialize_project_folder(folder) for folder in folders],
        "pagination": pagination
    }, 200


@project_folder_bp.route("/active", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def get_active_project_folders():
    query = ProjectFolder.query.filter(ProjectFolder.is_active.is_(True))
    search = get_search()

    if search:
        pattern = f"%{search}%"
        query = query.filter(ProjectFolder.folder_name.ilike(pattern))

    query = apply_sort(
        query,
        {
            "folder_name": ProjectFolder.folder_name,
            "created_at": ProjectFolder.created_at
        },
        "folder_name",
        "asc"
    )
    folders, pagination = paginate_query(query)

    return {
        "success": True,
        "folders": [serialize_project_folder(folder) for folder in folders],
        "pagination": pagination
    }, 200


@project_folder_bp.route("/<int:folder_id>", methods=["GET"])
@role_required(["SUPER_ADMIN", "ADMIN", "EMPLOYEE"])
def get_project_folder(folder_id):
    folder = ProjectFolder.query.filter_by(id=folder_id).first()

    if not folder:
        return {
            "success": False,
            "message": "Project folder not found"
        }, 404

    return {
        "success": True,
        "folder": serialize_project_folder(folder)
    }, 200


@project_folder_bp.route("/<int:folder_id>", methods=["PUT"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def update_project_folder(folder_id):
    folder = ProjectFolder.query.filter_by(id=folder_id).first()

    if not folder:
        return {
            "success": False,
            "message": "Project folder not found"
        }, 404

    data = request.get_json() or {}
    folder_name = data.get("folder_name")
    description = data.get("description")
    is_active = data.get("is_active")

    if folder_name is not None:
        folder_name = folder_name.strip()
        if not folder_name:
            return {
                "success": False,
                "message": "Folder name is required"
            }, 400

        existing_folder = ProjectFolder.query.filter(
            db.func.lower(ProjectFolder.folder_name) == folder_name.lower(),
            ProjectFolder.id != folder.id
        ).first()

        if existing_folder:
            return {
                "success": False,
                "message": "Folder name already exists"
            }, 409

        folder.folder_name = folder_name

    if description is not None:
        folder.description = description

    if is_active is not None:
        folder.is_active = bool(is_active)

    db.session.commit()

    return {
        "success": True,
        "message": "Project folder updated successfully",
        "folder": serialize_project_folder(folder)
    }, 200


@project_folder_bp.route("/<int:folder_id>", methods=["DELETE"])
@role_required(["SUPER_ADMIN", "ADMIN"])
def delete_project_folder(folder_id):
    folder = ProjectFolder.query.filter_by(id=folder_id).first()

    if not folder:
        return {
            "success": False,
            "message": "Project folder not found"
        }, 404

    active_project_count = folder.projects.filter_by(is_active=True).count()

    if active_project_count:
        return {
            "success": False,
            "message": "Folder has active projects. Deactivate or move projects first."
        }, 400

    folder.is_active = False
    db.session.commit()

    return {
        "success": True,
        "message": "Project folder deleted successfully"
    }, 200


def serialize_project_folder(folder):
    return {
        "id": folder.id,
        "folder_name": folder.folder_name,
        "description": folder.description,
        "created_by": folder.created_by,
        "is_active": folder.is_active,
        "status": "Active" if folder.is_active else "Inactive",
        "project_count": folder.projects.count() if folder.projects else 0,
        "active_project_count": folder.projects.filter_by(is_active=True).count() if folder.projects else 0,
        "created_at": folder.created_at.isoformat() if folder.created_at else None
    }
