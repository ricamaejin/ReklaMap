from .auth import auth_bp
from .map import map_bp
from .complaints import complaints_bp

def register_admin_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(complaints_bp)
