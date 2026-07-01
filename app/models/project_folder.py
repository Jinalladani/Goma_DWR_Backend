from app.extensions import db


class ProjectFolder(db.Model):
    __tablename__ = "project_folders"

    id = db.Column(db.Integer, primary_key=True)

    folder_name = db.Column(
        db.String(200),
        nullable=False,
        unique=True
    )

    description = db.Column(db.Text)

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

    projects = db.relationship(
        "Project",
        back_populates="folder",
        lazy="dynamic"
    )
