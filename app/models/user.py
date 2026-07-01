from app.extensions import db


class User(db.Model):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(db.String(150), nullable=False)

    email = db.Column(db.String(150), unique=True, nullable=False)

    password_hash = db.Column(db.Text, nullable=False)

    phone = db.Column(db.String(20))

    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"))

    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    is_active = db.Column(db.Boolean, default=True)

    reset_password_token_hash = db.Column(db.Text)

    reset_password_expires_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, server_default=db.func.now())

    role = db.relationship("Role", backref="users", foreign_keys=[role_id])

    manager = db.relationship("User", remote_side=[id])
