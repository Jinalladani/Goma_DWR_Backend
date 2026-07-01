from app.extensions import db


class WorkEntry(db.Model):
    __tablename__ = "work_entries"

    id = db.Column(db.Integer, primary_key=True)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("daily_work_sheets.id", ondelete="CASCADE"))
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    task_title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    stop_time = db.Column(db.DateTime)
    total_minutes = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default="RUNNING")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    worksheet = db.relationship("WorkSheet")
    project = db.relationship("Project")
    employee = db.relationship("User")