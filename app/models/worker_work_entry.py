from app.extensions import db


class WorkerWorkEntry(db.Model):
    __tablename__ = "worker_work_entries"

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(
        db.Integer,
        db.ForeignKey("workers.id"),
        nullable=False
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
    worksheet_id = db.Column(
        db.Integer,
        db.ForeignKey("daily_work_sheets.id", ondelete="SET NULL")
    )
    work_date = db.Column(db.Date, nullable=False)
    work_type = db.Column(db.String(80), nullable=False)
    task_title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime(timezone=True), nullable=False)
    end_time = db.Column(db.DateTime(timezone=True), nullable=False)
    total_minutes = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default="DRAFT")
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

    worker = db.relationship("Worker")
    employee = db.relationship("User")
    project = db.relationship("Project")
    worksheet = db.relationship("WorkSheet")
