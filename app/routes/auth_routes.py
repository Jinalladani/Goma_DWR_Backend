import hashlib
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required
)
from app.extensions import bcrypt, db
from app.models.revoked_token import RevokedToken
from app.models.user import User

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth"
)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return {
            "success": False,
            "message": "Email and password required"
        }, 400

    user = User.query.filter_by(
        email=email
    ).first()

    if not user:
        return {
            "success": False,
            "message": "Invalid email or password"
        }, 401

    is_valid = bcrypt.check_password_hash(
        user.password_hash,
        password
    )

    if not is_valid:
        return {
            "success": False,
            "message": "Invalid email or password"
        }, 401

    if not user.is_active:
        return {
            "success": False,
            "message": "User account is inactive"
        }, 403

    access_token = create_access_token(
        identity=str(user.id)
    )
    refresh_token = create_refresh_token(
        identity=str(user.id)
    )

    return {
        "success": True,
        "token": access_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": user.role.name,
            "phone": user.phone
        }
    }, 200


@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def profile():
    user_id = get_jwt_identity()
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {
            "success": False,
            "message": "User not found"
        }, 404

    return {
        "success": True,
        "user": {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": user.role.name,
            "phone": user.phone,
            "is_active": user.is_active
        }
    }, 200


@auth_bp.route("/profile/update", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {
            "success": False,
            "message": "User not found"
        }, 404

    data = request.get_json()
    full_name = data.get("full_name")
    phone = data.get("phone")

    if not full_name:
        return {
            "success": False,
            "message": "Full name is required"
        }, 400

    if phone:
        existing_phone = User.query.filter(
            User.phone == phone,
            User.id != user.id
        ).first()

        if existing_phone:
            return {
                "success": False,
                "message": "Phone number already exists"
            }, 409

    user.full_name = full_name
    user.phone = phone

    db.session.commit()

    return {
        "success": True,
        "message": "Profile updated successfully",
        "user": {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": user.role.name,
            "phone": user.phone,
            "is_active": user.is_active
        }
    }, 200


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return {
            "success": False,
            "message": "User not found"
        }, 404

    data = request.get_json()
    old_password = data.get("old_password")
    new_password = data.get("new_password")

    if not old_password or not new_password:
        return {
            "success": False,
            "message": "Old password and new password are required"
        }, 400

    is_valid = bcrypt.check_password_hash(user.password_hash, old_password)
    if not is_valid:
        return {
            "success": False,
            "message": "Incorrect old password"
        }, 401

    user.password_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
    db.session.commit()

    return {
        "success": True,
        "message": "Password changed successfully"
    }, 200


@auth_bp.route("/forgot-password/request", methods=["POST"])
def request_password_reset():
    data = request.get_json()
    email = data.get("email")
    phone = data.get("phone")

    if not email or not phone:
        return {
            "success": False,
            "message": "Email and phone number are required"
        }, 400

    user = User.query.filter_by(
        email=email,
        phone=phone,
        is_active=True
    ).first()

    if not user:
        return {
            "success": False,
            "message": "User not found with matching email and phone number"
        }, 404

    reset_token = secrets.token_urlsafe(32)
    user.reset_password_token_hash = hash_reset_token(reset_token)
    user.reset_password_expires_at = datetime.utcnow() + timedelta(minutes=15)

    db.session.commit()

    return {
        "success": True,
        "message": "Password reset verification successful",
        "reset_token": reset_token,
        "expires_in_minutes": 15
    }, 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    user = User.query.filter_by(id=user_id, is_active=True).first()

    if not user:
        return {
            "success": False,
            "message": "User account is unavailable"
        }, 401

    access_token = create_access_token(identity=str(user.id))

    return {
        "success": True,
        "token": access_token,
        "access_token": access_token
    }, 200


@auth_bp.route("/forgot-password/reset", methods=["POST"])
def reset_forgotten_password():
    data = request.get_json()
    reset_token = data.get("reset_token")
    new_password = data.get("password")

    if not reset_token or not new_password:
        return {
            "success": False,
            "message": "Reset token and new password are required"
        }, 400

    token_hash = hash_reset_token(reset_token)

    user = User.query.filter_by(
        reset_password_token_hash=token_hash
    ).first()

    if not user or not user.reset_password_expires_at:
        return {
            "success": False,
            "message": "Invalid or expired reset token"
        }, 400

    if user.reset_password_expires_at < datetime.utcnow():
        user.reset_password_token_hash = None
        user.reset_password_expires_at = None
        db.session.commit()

        return {
            "success": False,
            "message": "Invalid or expired reset token"
        }, 400

    user.password_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
    user.reset_password_token_hash = None
    user.reset_password_expires_at = None

    db.session.commit()

    return {
        "success": True,
        "message": "Password reset successfully"
    }, 200


# =========================
# LOGOUT API
# =========================
@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    revoke_token(get_jwt())

    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token")

    if refresh_token:
        try:
            refresh_payload = decode_token(refresh_token)
        except Exception:
            refresh_payload = None

        if refresh_payload and (
            refresh_payload.get("type") != "refresh"
            or refresh_payload.get("sub") != get_jwt_identity()
        ):
            refresh_payload = None

        if refresh_payload:
            revoke_token(refresh_payload)

    db.session.commit()

    return {
        "success": True,
        "message": "Logout successful"
    }, 200


def hash_reset_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def revoke_token(payload):
    if RevokedToken.query.filter_by(jti=payload["jti"]).first():
        return

    db.session.add(
        RevokedToken(
            jti=payload["jti"],
            token_type=payload["type"],
            user_id=int(payload["sub"]),
            expires_at=datetime.utcfromtimestamp(payload["exp"])
        )
    )
