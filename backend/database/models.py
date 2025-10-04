from .db import db
from sqlalchemy.dialects.mysql import JSON, DECIMAL, ENUM
from sqlalchemy import Computed

# -----------------------
# Admin
# -----------------------
class Admin(db.Model):
    __tablename__ = "admin"
    __tablename__ = "admin"

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
# Registration HOA Member (linking table)
# -----------------------

class RegistrationHOAMember(db.Model):
    __tablename__ = "registration_hoa_member"

    hoa_member_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    registration_id = db.Column(
        db.Integer,
        db.ForeignKey("registration.registration_id"),
        nullable=False
    )
    supporting_documents = db.Column(JSON, nullable=True)

    # Relationship back to registration
    registration = db.relationship("Registration", backref="hoa_member")


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
class Complaint(db.Model):
    __tablename__ = "complaints"   # must match phpMyAdmin table name

    complaint_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    registration_id = db.Column(db.Integer, db.ForeignKey("registration.registration_id", ondelete="CASCADE"), nullable=False)
    type_of_complaint = db.Column(db.String(150), nullable=False)
    date_received = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    status = db.Column(db.Enum("Valid", "Invalid"), nullable=False, default="Valid")
    # 👇 Computed column (read-only, generated by MySQL)
    priority_level = db.Column(
        db.String(50),
        Computed(
            "case "
            "when type_of_complaint = 'Overlapping' then 'Severe' "
            "when type_of_complaint = 'Pathway Dispute' then 'Severe' "
            "when type_of_complaint = 'Lot Dispute' then 'Moderate' "
            "when type_of_complaint = 'Boundary Dispute' then 'Moderate' "
            "when type_of_complaint = 'Unauthorized Occupation' then 'Minor' "
            "else 'Unclassified' end",
            persisted=False  # matches your VIRTUAL column
        )
    )
    description = db.Column(db.Text)
    
    # Relationship to overlapping (one-to-one)
    overlapping = db.relationship("Overlapping", backref="complaint", uselist=False, passive_deletes=True)

    complainant_name = db.Column(db.String(150), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.area_id'), nullable=False)
    address = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<Complaint {self.complaint_id}>"


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
# Non-Member Registration
# -----------------------
class RegistrationNonMember(db.Model):
    __tablename__ = "registration_non_member"
    non_member_id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.Integer, db.ForeignKey("registration.registration_id"), nullable=False)
    connections = db.Column(db.JSON, nullable=True)

# -----------------------
# Fam Member of Member
# -----------------------
class RegistrationFamOfMember(db.Model):
    __tablename__ = "registration_fam_of_member"

    fam_member_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # FK → Registration.registration_id
    registration_id = db.Column(
        db.Integer,
        db.ForeignKey("registration.registration_id"),
        nullable=True  # optional if parent registration doesn't exist
    )

    # FK → Beneficiary.beneficiary_id
    beneficiary_id = db.Column(
        db.Integer,
        db.ForeignKey("beneficiaries.beneficiary_id"),
        nullable=True
    )

    last_name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    suffix = db.Column(db.String(10))
    date_of_birth = db.Column(db.Date)
    sex = db.Column(ENUM("Male", "Female"))
    citizenship = db.Column(db.String(50))
    age = db.Column(DECIMAL(2, 0))
    phone_number = db.Column(db.String(20))
    year_of_residence = db.Column(DECIMAL(2, 0))
    relationship = db.Column(db.String(100), nullable=False)
    supporting_documents = db.Column(JSON)

    # Relationships back
    registration = db.relationship("Registration", backref="family_members")
    beneficiary = db.relationship("Beneficiary", backref="family_members")


# -----------------------
# Overlapping table
# -----------------------
class Overlapping(db.Model):
    __tablename__ = "overlapping"

    overlapping_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.complaint_id', ondelete="CASCADE"), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey('registration.registration_id', ondelete="CASCADE"), nullable=False)
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
    registration = db.relationship("Registration", backref="overlapping_complaints", passive_deletes=True)

    def __repr__(self):
        return f"<Overlapping {self.overlapping_id}>"
    
# -----------------------
# Lot Dispute
# -----------------------

class LotDispute(db.Model):
    __tablename__ = "lot_dispute"

    lot_dispute_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.complaint_id', ondelete="CASCADE"), nullable=False)
    q1 = db.Column(db.String(200))
    q2 = db.Column(db.String(200))
    q3 = db.Column(db.Date)
    q4 = db.Column(db.String(200))
    q5 = db.Column(db.JSON)
    q6 = db.Column(db.String(200))
    q7 = db.Column(db.String(100))
    q8 = db.Column(db.String(100))
    q9 = db.Column(db.Enum("Yes", "No", "Not Sure"))

    # Relationship back to complaint
    complaint = db.relationship("Complaint", backref="lot_dispute", passive_deletes=True)

# -----------------------
# Boundary Dispute
# -----------------------

class BoundaryDispute(db.Model):
    __tablename__ = "boundary_dispute"

    boundary_dispute_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.complaint_id', ondelete="CASCADE"), nullable=False)
    q1 = db.Column(db.String(200))  # nature of boundary issue
    q2 = db.Column(db.String(80))   # duration
    q3 = db.Column(db.String(80))   # constructed/under construction
    q4 = db.Column(db.Enum('Yes','No'))
    q5 = db.Column(db.Enum('Yes','No'))
    q6 = db.Column(db.JSON)         # multiple choices
    q7 = db.Column(db.Enum('Yes','No'))
    q7_1 = db.Column(db.Date)       # conditional date
    q8 = db.Column(db.Enum('Yes','No','Not Sure'))

    # Relationship back to Complaint
    complaint = db.relationship("Complaint", backref="boundary_dispute", passive_deletes=True)



