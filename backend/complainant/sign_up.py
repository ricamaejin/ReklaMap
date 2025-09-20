from flask import Flask, request, send_from_directory
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
cursor = db.cursor()

# Serve HTML file from a different folder
@app.route("/")
def home():
    # adjust the path to HTML file
    return send_from_directory(os.path.abspath("C:\Users\win10\Documents\GitHub\ReklaMap\frontend\portal"), "sign_up.html")

@app.route("/signup", methods=["POST"])
def signup():
    firstName = request.form.get("firstName")
    lastName = request.form.get("lastName")
    email = request.form.get("email")
    password = request.form.get("password")

    sql = "INSERT INTO users (first_name, last_name, email, password) VALUES (%s, %s, %s, %s)"
    values = (firstName, lastName, email, password)

    cursor.execute(sql, values)
    db.commit()

    return "Sign up successful!"

if __name__ == "__main__":
    app.run(port=3000, debug=True)
