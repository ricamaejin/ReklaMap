# change exactly as cols in db phpmyadmin

from .db import db

# -----------------------
# Admin
# -----------------------
class Admin(db.Model):
    __tablename__ = "admin"   # phpMyAdmin

    admin_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    account = db.Column(db.Integer, nullable=False)  # 1=admin, 2=staff

    def __repr__(self):
        return f"<Admin {self.employee_id}>"

class Area(db.Model):
    __tablename__ = 'areas'
    area_id = db.Column(db.Integer, primary_key=True)
    area_code = db.Column(db.String(10), nullable=False)
    area_name = db.Column(db.String(100), nullable=False)
    president = db.Column(db.String(150), nullable=False)
    designation = db.Column(db.String(100), nullable=False)
    contact_no = db.Column(db.String(20), nullable=True)
    blocks = db.relationship('Block', backref='area', lazy=True)
    beneficiaries = db.relationship('Beneficiary', backref='area', lazy=True)

class Block(db.Model):
    __tablename__ = 'blocks'
    block_id = db.Column(db.Integer, primary_key=True)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.area_id'), nullable=False)
    block_no = db.Column(db.Integer, nullable=False)
    beneficiaries = db.relationship('Beneficiary', backref='block', lazy=True)

class Beneficiary(db.Model):
    __tablename__ = 'beneficiaries'
    beneficiary_id = db.Column(db.Integer, primary_key=True)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.area_id'), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey('blocks.block_id'), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_initial = db.Column(db.String(10))
    last_name = db.Column(db.String(100), nullable=False)
    suffix = db.Column(db.String(10))
    lot_no = db.Column(db.Integer, nullable=False)
    sqm = db.Column(db.Integer, nullable=False)
    co_owner = db.Column(db.Boolean, default=False)

class GeneratedLots(db.Model):
    __tablename__ = "generated_lots"   # must match phpMyAdmin table name

    genlot_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.area_id'), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey('blocks.block_id'), nullable=False)
    remarks = db.Column(db.String(255), nullable=False)
    lot_no = db.Column(db.Integer, nullable=False)
    sqm = db.Column(db.Integer, nullable=False)
    last_name = db.Column(db.String(100), nullable=True)
    first_name = db.Column(db.String(100), nullable=True)
    middle_initial = db.Column(db.String(10), nullable=True)
    suffix = db.Column(db.String(10), nullable=True)

    def __repr__(self):
        return f"<GeneratedLots {self.genlot_id}>"

# -----------------------
# Complainant table (future mapping)
# -----------------------
class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

# -----------------------
# Policy
# -----------------------
class Policy(db.Model):
    __tablename__ = "policies"   # must match phpMyAdmin table name

    policy_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    policy_code = db.Column(db.String(50), nullable=False)
    law = db.Column(db.String(500), nullable=False)
    section_number = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    application = db.Column(db.String(150))

    def __repr__(self):
        return f"<Policy {self.policy_code}>"


# -----------------------
# Complaints
# -----------------------
class Complaints(db.Model):
    __tablename__ = "complaints"   # must match phpMyAdmin table name

    complaint_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complainant_name = db.Column(db.String(150), nullable=False)
    complaint_type = db.Column(db.String(100), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.area_id'), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    priority_level = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='pending')
    date_submitted = db.Column(db.DateTime, server_default=db.func.now())
    description = db.Column(db.Text)

    def __repr__(self):
        return f"<Complaints {self.complaint_id}>"


# -----------------------
# Complaint History
# -----------------------
class ComplaintHistory(db.Model):
    __tablename__ = "complaint_history"   # must match phpMyAdmin table name

    history_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.complaint_id'), nullable=False)
    assigned_to = db.Column(db.String(150), nullable=True)  # Staff member name
    action_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    date_created = db.Column(db.DateTime, server_default=db.func.now())
    created_by = db.Column(db.String(150), nullable=False)  # Admin/Staff who made the entry

    def __repr__(self):
        return f"<ComplaintHistory {self.history_id}>"


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


