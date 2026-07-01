from flask import Blueprint

from app.middleware.role_required import role_required


test_bp = Blueprint(
    "test",
    __name__,
    url_prefix="/api/test"
)


@test_bp.route("/super-admin", methods=["GET"])
@role_required(["SUPER_ADMIN"])
def super_admin_test():
    return {
        "success": True,
        "message": "Super Admin access granted"
    }, 200


@test_bp.route("/admin", methods=["GET"])
@role_required(["ADMIN", "SUPER_ADMIN"])
def admin_test():
    return {
        "success": True,
        "message": "Admin access granted"
    }, 200


@test_bp.route("/employee", methods=["GET"])
@role_required(["EMPLOYEE", "ADMIN", "SUPER_ADMIN"])
def employee_test():
    return {
        "success": True,
        "message": "Employee access granted"
    }, 200