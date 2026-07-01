from app.extensions import db


class WorkSheet(db.Model):
    __tablename__ = "daily_work_sheets"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    work_date = db.Column(db.Date, nullable=False)
    total_minutes = db.Column(db.Integer, default=0)
    note = db.Column(db.Text)
    status = db.Column(db.String(30), default="DRAFT")
    submitted_at = db.Column(db.DateTime(timezone=True))
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    review_status = db.Column(db.String(30), default="PENDING")
    review_comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    employee = db.relationship("User", foreign_keys=[employee_id])