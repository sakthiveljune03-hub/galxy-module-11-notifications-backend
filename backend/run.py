from app import create_app
from app.configs.config import Config

app = create_app()

if __name__ == '__main__':
    print(f"Starting GALXY Notification Service in '{Config.FLASK_ENV}' mode...")
    print(f"Server local address: http://localhost:{Config.PORT}")
    app.run(host='0.0.0.0', port=Config.PORT, debug=(Config.FLASK_ENV == "development"))
