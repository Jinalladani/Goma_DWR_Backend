from app.extensions import db


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)

    folder_id = db.Column(
        db.Integer,
        db.ForeignKey("project_folders.id"),
        nullable=True
    )

    folder = db.relationship(
        "ProjectFolder",
        back_populates="projects"
    )

    project_name = db.Column(
        db.String(200),
        nullable=False
    )

    project_code = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    description = db.Column(
        db.Text
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    is_active = db.Column(
        db.Boolean,
        default=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now()
    )
