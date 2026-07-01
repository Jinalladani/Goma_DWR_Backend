from app.extensions import db


class EmployeeProject(db.Model):

    __tablename__ = "employee_projects"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id"),
        nullable=False
    )

    assigned_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    is_active = db.Column(
        db.Boolean,
        default=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now()
    )

    employee = db.relationship(
        "User",
        foreign_keys=[employee_id]
    )

    project = db.relationship(
        "Project"
    )
