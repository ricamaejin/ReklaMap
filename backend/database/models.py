from .db import db
from sqlalchemy.dialects.mysql import JSON, DECIMAL, ENUM
from sqlalchemy import Computed

# -----------------------
# Admin
# -----------------------
class Admin(db.Model):
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

    __table_args__ = (
        db.UniqueConstraint('first_name', 'last_name', name='uq_fullname'),
    )

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
    supporting_documents = db.Column(JSON, nullable=True)

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
    complaint_stage = db.Column(db.Enum("Pending", "Ongoing", "Resolved", "Overdue", "Unresolved", "Out of Jurisdiction"), nullable=False, default="Pending")
    # 👇 Computed column (read-only, generated by MySQL)
    priority_level = db.Column(
        db.String(50),
        Computed(
            "case "
            "when type_of_complaint = 'Pathway Dispute' then 'Severe' "
            "when type_of_complaint = 'Lot Dispute' then 'Moderate' "
            "when type_of_complaint = 'Boundary Dispute' then 'Moderate' "
            "when type_of_complaint = 'Unauthorized Occupation' then 'Minor' "
            "else 'Unclassified' end",
            persisted=False  # matches your VIRTUAL column
        )
    )
    description = db.Column(db.Text)
    complainant_name = db.Column(db.String(150), nullable=False)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.area_id'), nullable=False)
    address = db.Column(db.String(255), nullable=False)

    # Relationship to LotDispute
    lot_dispute = db.relationship(
        "LotDispute",
        back_populates="complaint",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    # Relationship to BoundaryDispute
    boundary_dispute = db.relationship(
        "BoundaryDispute",
        back_populates="complaint",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True
    )


    # Relationship to PathwayDispute
    pathway_dispute = db.relationship(
        "PathwayDispute",
        back_populates="complaint",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    # Relationship to UnauthorizedOccupation
    unauthorized_occupation = db.relationship(
        "UnauthorizedOccupation",
        back_populates="complaint",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    



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
    type_of_action = db.Column(db.String(100), nullable=False)
    details = db.Column(JSON)
    action_datetime = db.Column(db.DateTime, server_default=db.func.now())

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
# Family Member of Member
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
    current_address = db.Column(db.String(255))
    supporting_documents = db.Column(JSON)


    # Relationships back
    registration = db.relationship("Registration", backref="family_members")
    beneficiary = db.relationship("Beneficiary", backref="family_members")

    
# -----------------------
# Lot Dispute
# -----------------------

class LotDispute(db.Model):
    __tablename__ = "lot_dispute"

    lot_dispute_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.complaint_id', ondelete="CASCADE"), nullable=False)
    q1 = db.Column(db.String(200))
    # JSON array of objects: [{"block": <str>, "lot": <str>}, ...]
    block_lot = db.Column(db.JSON)
    q2 = db.Column(db.String(200))
    q3 = db.Column(db.Date)
    q4 = db.Column(db.String(200))
    q5 = db.Column(db.JSON)
    q6 = db.Column(db.String(200))
    q7 = db.Column(db.JSON)  # Multiple opposing names
    q8 = db.Column(db.JSON)  # Multiple relationships
    q9 = db.Column(db.JSON)  # Legal documents claim and document types
    q10 = db.Column(db.JSON)  # Additional question data (e.g., residence status)
    description = db.Column(db.Text)
    signature = db.Column(db.String(255))

    # Relationship back to complaint
    complaint = db.relationship(
        "Complaint",
        back_populates="lot_dispute",
        passive_deletes=True
    )

# -----------------------
# Boundary Dispute
# -----------------------

class BoundaryDispute(db.Model):
    __tablename__ = "boundary_dispute"

    boundary_dispute_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(
        db.Integer,
        db.ForeignKey('complaints.complaint_id', ondelete="CASCADE"),
        nullable=False
    )

    # Questionnaire fields
    q1 = db.Column(db.JSON)                         # nature/issues
    q2 = db.Column(db.String(50))                   # duration
    q3 = db.Column(db.String(100))                  # structure status
    q4 = db.Column(db.Enum('Yes', 'No'))            # prior notice
    q5 = db.Column(db.Enum('Yes', 'No'))            # confronted
    q5_1 = db.Column(db.Date)                       # date reported
    q6 = db.Column(db.JSON)                         # dispute effects
    q7 = db.Column(db.JSON)                         # reported to
    q8 = db.Column(db.String(100))                  # site inspection
    q9 = db.Column(db.JSON)                         # inspection result
    q10 = db.Column(db.Enum('Yes', 'No'))           # have supporting docs
    q10_1 = db.Column(db.JSON)                      # doc types
    q11 = db.Column(db.Enum('Yes', 'No', 'Not sure'))  # govt project involvement
    q12 = db.Column(db.JSON)                        # persons involved
    q13 = db.Column(db.JSON)                        # relationships
    q14 = db.Column(db.Enum('Yes', 'No', 'Not sure'))  # reside near site
    q15 = db.Column(db.Enum('Yes', 'No'))           # claim docs
    q15_1 = db.Column(db.JSON)                      # claim doc types
    block_lot = db.Column(db.JSON)                  # non-member block/lot pairs

    # Extra details
    description = db.Column(db.Text)                # incident description
    signature_path = db.Column(db.String(255))      # uploaded signature path

    # Relationship back to Complaint
    complaint = db.relationship(
        "Complaint",
        back_populates="boundary_dispute",
        passive_deletes=True
    )


# -----------------------
# Pathway Dispute
# -----------------------

class PathwayDispute(db.Model):
    __tablename__ = "pathway_dispute"

    pathway_dispute_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.complaint_id', ondelete="CASCADE"), nullable=False)
    block_lot = db.Column(db.JSON, nullable=True)
    q1 = db.Column(db.String(200), nullable=True)
    q2 = db.Column(db.String(200), nullable=True)
    q3 = db.Column(db.String(80), nullable=True)
    q4 = db.Column(db.String(80), nullable=True)
    q5 = db.Column(db.JSON, nullable=True)
    q6 = db.Column(db.Enum('Yes', 'No', 'Not Sure'), nullable=True)
    q7 = db.Column(db.String(80), nullable=True)
    q8 = db.Column(db.JSON, nullable=True)
    q9 = db.Column(db.JSON, nullable=True)
    q10 = db.Column(db.String(80), nullable=True)
    q11 = db.Column(db.JSON, nullable=True)
    q12 = db.Column(db.Enum('Yes', 'No', 'Not Sure'), nullable=True)
    description = db.Column(db.Text, nullable=True)
    signature = db.Column(db.String(255), nullable=True)

    # Relationship back to Complaint
    complaint = db.relationship(
        "Complaint",
        back_populates="pathway_dispute",
        passive_deletes=True
    )


# -----------------------
# Unauthorized Occupation
# -----------------------
class UnauthorizedOccupation(db.Model):
    __tablename__ = "unauthorized_occupation"

    unauthorized_occupation_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.complaint_id', ondelete="CASCADE"), nullable=False)
    block_lot = db.Column(db.JSON, nullable=True)
    q1 = db.Column(db.String(100), nullable=True)
    q2 = db.Column(db.JSON, nullable=True)
    q3 = db.Column(db.Date, nullable=True)
    q4 = db.Column(db.JSON, nullable=True)
    q5 = db.Column(db.String(50), nullable=True)
    q5a = db.Column(db.JSON, nullable=True)
    q6 = db.Column(db.String(50), nullable=True)
    q6a = db.Column(db.JSON, nullable=True)
    q7 = db.Column(db.JSON, nullable=True)
    q8 = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    signature = db.Column(db.String(255), nullable=True)

    # Relationship back to Complaint
    complaint = db.relationship(
        "Complaint",
        back_populates="unauthorized_occupation",
        passive_deletes=True
    )

