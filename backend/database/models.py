# change exactly as cols in db phpmyadmin

from .db import db

# -----------------------
# Admin
# -----------------------
class Admin(db.Model):
    __tablename__ = "admin"

    admin_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

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


# -----------------------
# Complainant table
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
# Registration table
# -----------------------
class Registration(db.Model):
    __tablename__ = "registration"

    registration_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    beneficiary_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    category = db.Column(db.String(50))
    last_name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    suffix = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    sex = db.Column(db.String(10))
    citizenship = db.Column(db.String(50))
    age = db.Column(db.Integer)
    phone_number = db.Column(db.String(20))
    year_of_residence = db.Column(db.String(50))
    civil_status = db.Column(db.String(50))
    current_address = db.Column(db.String(255))
    hoa = db.Column(db.String(100))
    block_no = db.Column(db.String(50))
    lot_no = db.Column(db.String(50))
    lot_size = db.Column(db.String(50))
    recipient_of_other_housing = db.Column(db.String(10))
    signature_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # relationship back to user
    user = db.relationship("User", backref="registrations")


# -----------------------
# Complaint table
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
class Complaint(db.Model):
    __tablename__ = "complaints"

    complaint_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    registration_id = db.Column(db.Integer, db.ForeignKey("registration.registration_id"), nullable=False)
    type_of_complaint = db.Column(db.String(150), nullable=False)
    date_received = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    status = db.Column(db.Enum("Valid", "Invalid"), nullable=False, default="Valid")
    priority_level = db.Column(db.Enum("Severe", "Moderate", "Minor"))
    description = db.Column(db.Text)

    # Relationship to overlapping (one-to-one)
    overlapping = db.relationship("Overlapping", backref="complaint", uselist=False)

# -----------------------
class RegistrationNonMember(db.Model):
    __tablename__ = "registration_non_member"
    non_member_id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.Integer, db.ForeignKey("registration.registration_id"), nullable=False)
    connections = db.Column(db.JSON, nullable=True)


# -----------------------
# Overlapping table
# -----------------------
class Overlapping(db.Model):
    __tablename__ = "overlapping"

    overlapping_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.complaint_id'), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey('registration.registration_id'), nullable=False)
    q1 = db.Column(db.JSON)
    q2 = db.Column(db.String(80))
    q3 = db.Column(db.String(50))
    q4 = db.Column(db.JSON)
    q5 = db.Column(db.JSON)
    q6 = db.Column(db.JSON)
    q7 = db.Column(db.String(80))
    q8 = db.Column(db.String(100))
    q9 = db.Column(db.JSON)
    q10 = db.Column(db.String(50))
    q11 = db.Column(db.String(50))
    q12 = db.Column(db.String(50))
    q13 = db.Column(db.String(50))
    description = db.Column(db.Text)
    signature = db.Column(db.String(255))

    # relationships back to registration
    registration = db.relationship("Registration", backref="overlapping_complaints")

    def __repr__(self):
        return f"<Overlapping {self.overlapping_id}>"

