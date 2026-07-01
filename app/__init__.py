from flask import Flask
from flask_cors import CORS

from app.config.config import Config

from app.extensions import (
    db,
    jwt,
    bcrypt,
    cors
)

def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)

    db.init_app(app)

    jwt.init_app(app)

    from app.models.revoked_token import RevokedToken

    @jwt.token_in_blocklist_loader
    def is_token_revoked(_jwt_header, jwt_payload):
        return RevokedToken.query.filter_by(jti=jwt_payload["jti"]).first() is not None

    bcrypt.init_app(app)

    CORS(
        app,
        resources={r"/*": {"origins": [
            "https://goma-dwr-frontend.onrender.com",
            "http://localhost:5173",
        ]}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )

    from app.routes.auth_routes import auth_bp
    from app.routes.test_routes import test_bp
    from app.routes.project_routes import project_bp
    from app.routes.user_routes import user_bp
    from app.routes.project_access_routes import project_access_bp
    from app.routes.worker_routes import worker_bp
    from app.routes.worker_entry_routes import worker_entry_bp
    from app.routes.work_entry_routes import work_entry_bp
    from app.routes.worksheet_routes import worksheet_bp
    from app.routes.admin_worksheet_routes import admin_worksheet_bp
    from app.routes.dashboard_routes import dashboard_bp
    from app.routes.project_folder_routes import project_folder_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(project_access_bp)
    app.register_blueprint(worker_bp)
    app.register_blueprint(worker_entry_bp)
    app.register_blueprint(work_entry_bp)
    app.register_blueprint(worksheet_bp)
    app.register_blueprint(admin_worksheet_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(project_folder_bp)

    @app.route("/")
    def home():
        return {
            "message": "Goma DWR Backend Running"
        }

    return app
