from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    from .routes.auth import bp as auth_bp
    from .routes.admin import bp as admin_bp
    from .routes.teacher import bp as teacher_bp
    from .routes.student import bp as student_bp
    from .routes.api import bp as api_bp
    from .routes.common import bp as common_bp
    for bp in (auth_bp, admin_bp, teacher_bp, student_bp, api_bp, common_bp):
        app.register_blueprint(bp)

    from .models import grade_letter
    app.jinja_env.globals["grade_letter"] = grade_letter

    from flask import render_template

    @app.errorhandler(403)
    @app.errorhandler(404)
    def http_error(e):
        return render_template("error.html", error=e), e.code

    return app
