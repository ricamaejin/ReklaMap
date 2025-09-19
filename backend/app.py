# tbd imports, db config, test code

from flask import Flask
from backend.database.db import db
from backend.database.models import Admin

from backend.admin.routes import admin_bp

app = Flask(__name__)

# ✅ Database configuration (already set in db.py)
# app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:Reklamapadmin123@<DB_HOST>/<DB_NAME>" # db name: reklamap?
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:Reklamapadmin123@192.168.1.50:3306/reklamap" # change ip, un if not root
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ✅ Register Blueprints
app.register_blueprint(admin_bp)
# app.register_blueprint(complainant_bp)
# app.register_blueprint(staff_bp)

# ✅ Initialize db with app
db.init_app(app)




# TEMP TEST ONLY
@app.route("/")
def home():
    return "Backend is running ✅"


# 🔹 Test route: get all admins from DB
@app.route("/test-admins")
def test_admins():
    admins = Admin.query.all()  # SELECT * FROM admins
    result = [admin.employee_id for admin in admins]  # return only employee IDs
    return {"admins": result}


if __name__ == "__main__":
    app.run(debug=True)
