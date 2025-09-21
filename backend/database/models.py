# change exactly as cols in db phpmyadmin

from .db import db

# -----------------------
# Admin table (matches phpMyAdmin "admin" table)
# -----------------------
class Admin(db.Model):
    __tablename__ = "admin"   # phpMyAdmin

    admin_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<Admin {self.employee_ID}>"


# -----------------------
# Complainant table (future mapping)
# -----------------------
# class Complainant(db.Model):
#     __tablename__ = "complainants"   # must match phpMyAdmin table name
#
#     id = db.Column(db.Integer, primary_key=True)
#     email = db.Column(db.String(120), unique=True)
#     password = db.Column(db.String(200))
#
#     def __repr__(self):
#         return f"<Complainant {self.email}>"


# -----------------------
# Staff table (future mapping)
# -----------------------
# class Staff(db.Model):
#     __tablename__ = "staff"   # must match phpMyAdmin table name
#
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100))
#     role = db.Column(db.String(50))
#
#     def __repr__(self):
#         return f"<Staff {self.name}>"
