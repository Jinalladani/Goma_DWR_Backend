from app.extensions import db


class Worker(db.Model):
    __tablename__ = "workers"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20))
    worker_type = db.Column(db.String(80))
    assigned_employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

    assigned_employee = db.relationship(
        "User",
        foreign_keys=[assigned_employee_id]
    )
    creator = db.relationship("User", foreign_keys=[created_by])
