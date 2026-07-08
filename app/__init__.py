from flask import Flask
from flask_cors import CORS
from app.routes.notification_routes import notification_bp

def create_app():
    app = Flask(__name__)
    from app.configs.config import Config
    origins = [orig.strip() for orig in Config.CORS_ORIGINS.split(",") if orig.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}})  # Enable restricted Cross-Origin Resource Sharing for the React frontend
    
    # Register the notifications blueprint routes
    app.register_blueprint(notification_bp)
    
    @app.route("/")
    def index():
        return {
            "success": True,
            "message": "GALXY Notification Service API is running"
        }
        
    return app
# app package
