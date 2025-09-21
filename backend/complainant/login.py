from flask import Flask, request, redirect, send_from_directory
from werkzeug.security import check_password_hash
import mysql.connector
import os

app = Flask(__name__)

# MySQL connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="yourpassword",
    database="reklamap"
)
cursor = db.cursor(dictionary=True)

# Serve login HTML
@app.route("/")
def home():
    return send_from_directory(os.path.abspath("C:\Users\win10\Documents\GitHub\ReklaMap\frontend\portal\complainant_login.html"), "complainant_login.html")

# Login route
@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")

    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    if user and check_password_hash(user['password'], password):
        # Redirect to dashboard on successful login
        return redirect("/dashboard")
    else:
        return "❌ Invalid email or password", 401

# Serve dashboard HTML
@app.route("/dashboard")
def dashboard():
    return send_from_directory(os.path.abspath("C:\Users\win10\Documents\GitHub\ReklaMap\frontend\complainant\home\dashboard.html"), "dashboard.html")

if __name__ == "__main__":
    app.run(port=3000, debug=True)
