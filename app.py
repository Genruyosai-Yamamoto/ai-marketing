import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from flask import Flask, request,render_template
from routes.auth import auth_bp
from routes.user import user_bp
from routes.auth_api import api_auth_bp
from routes.business_api import business_api_bp
# from routes.payment import payment_bp
from datetime import timedelta
from werkzeug.middleware.proxy_fix import ProxyFix

# Create the Flask app
app = Flask(__name__, template_folder="templates", static_folder="static")

app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable is missing"
    )

app.config["DEBUG"] = os.getenv("DEBUG", "False").lower() == "true"


app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


# Session configuration for security
app.config.update(
    SESSION_COOKIE_SECURE=not app.config["DEBUG"],  # True in production, False in local dev
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)



# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(user_bp)
app.register_blueprint(api_auth_bp)
app.register_blueprint(business_api_bp)
# app.register_blueprint(payment_bp)


@app.after_request
def set_no_cache_headers(response):
    """
    Prevent the browser from caching any page so that after logout,
    pressing back or manually entering a URL forces a fresh server
    request (which login_required will reject).
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code='404'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', code='500', error=str(e)), 500

# Run locally if executed directly
if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))
    ssl_context = ("cert.pem", "key.pem")  # cert file, key file

    app.run(
        debug=app.config.get("DEBUG", True),
        host="0.0.0.0",
        port=port,
        threaded=True,
        use_reloader=app.config.get("DEBUG", True),
        # ssl_context=ssl_context
    )