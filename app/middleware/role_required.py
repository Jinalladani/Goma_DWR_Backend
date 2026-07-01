from functools import wraps

from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.user import User


def role_required(allowed_roles):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            user_id = get_jwt_identity()

            user = User.query.filter_by(id=user_id).first()

            if not user:
                return {
                    "success": False,
                    "message": "User not found"
                }, 404

            if not user.is_active:
                return {
                    "success": False,
                    "message": "User account is inactive"
                }, 403

            if user.role.name not in allowed_roles:
                return {
                    "success": False,
                    "message": "You do not have permission to access this resource"
                }, 403

            return fn(*args, **kwargs)

        return wrapper

    return decorator