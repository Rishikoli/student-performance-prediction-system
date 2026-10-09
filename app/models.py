from datetime import datetime, date

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db

# Grade bands from Cortez & Silva (2008), 0-20 Portuguese scale
GRADE_BANDS = [(16, "A", "Excellent"), (14, "B", "Good"), (12, "C", "Satisfactory"),
               (10, "D", "Sufficient"), (0, "F", "Fail")]


def grade_letter(g):
    if g is None:
        return None
    for low, letter, _ in GRADE_BANDS:
        if g >= low:
            return letter


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.Enum("admin", "teacher", "student", name="user_role"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))     # teachers
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))     # students
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    subject = db.relationship("Subject")
    student = db.relationship("Student", back_populates="user")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_active(self):
        return self.is_active_user


class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)   # MAT / POR
    name = db.Column(db.String(100), nullable=False)


class Student(db.Model):
    """Identity / demographic attributes shared across courses."""
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    school = db.Column(db.Enum("GP", "MS", name="school_enum"), nullable=False)
    sex = db.Column(db.Enum("F", "M", name="sex_enum"), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    address = db.Column(db.Enum("U", "R", name="address_enum"), nullable=False)
    famsize = db.Column(db.Enum("LE3", "GT3", name="famsize_enum"), nullable=False)
    Pstatus = db.Column(db.Enum("T", "A", name="pstatus_enum"), nullable=False)
    Medu = db.Column(db.Integer, nullable=False)
    Fedu = db.Column(db.Integer, nullable=False)
    Mjob = db.Column(db.String(20), nullable=False)
    Fjob = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(20), nullable=False)
    nursery = db.Column(db.Boolean, nullable=False)
    internet = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    records = db.relationship("AcademicRecord", back_populates="student",
                              cascade="all, delete-orphan")
    user = db.relationship("User", back_populates="student", uselist=False,
                           cascade="all, delete-orphan")


class AcademicRecord(db.Model):
    """One student's enrolment in one subject (one row of the UCI csv files)."""
    __tablename__ = "academic_records"
    __table_args__ = (db.UniqueConstraint("student_id", "subject_id"),)
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)

    guardian = db.Column(db.String(10), nullable=False)
    traveltime = db.Column(db.Integer, nullable=False)
    studytime = db.Column(db.Integer, nullable=False)
    failures = db.Column(db.Integer, nullable=False)      # previous academic performance
    schoolsup = db.Column(db.Boolean, nullable=False)
    famsup = db.Column(db.Boolean, nullable=False)
    paid = db.Column(db.Boolean, nullable=False)
    activities = db.Column(db.Boolean, nullable=False)
    higher = db.Column(db.Boolean, nullable=False)
    romantic = db.Column(db.Boolean, nullable=False)
    famrel = db.Column(db.Integer, nullable=False)
    freetime = db.Column(db.Integer, nullable=False)
    goout = db.Column(db.Integer, nullable=False)
    Dalc = db.Column(db.Integer, nullable=False)
    Walc = db.Column(db.Integer, nullable=False)
    health = db.Column(db.Integer, nullable=False)

    absences = db.Column(db.Integer, nullable=False, default=0)
    G1 = db.Column(db.Integer)   # first period grade (0-20)
    G2 = db.Column(db.Integer)   # second period grade (0-20)
    G3 = db.Column(db.Integer)   # final grade (0-20) - prediction target
    # Not part of the UCI dataset; entered by teachers in the app (0-100)
    assignment_score = db.Column(db.Float)
    practical_score = db.Column(db.Float)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship("Student", back_populates="records")
    subject = db.relationship("Subject")
    attendance = db.relationship("Attendance", back_populates="record",
                                 cascade="all, delete-orphan")
    predictions = db.relationship("Prediction", back_populates="record",
                                  cascade="all, delete-orphan",
                                  order_by="Prediction.created_at.desc()")

    @property
    def grade(self):
        return grade_letter(self.G3)

    @property
    def latest_prediction(self):
        return self.predictions[0] if self.predictions else None


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (db.UniqueConstraint("record_id", "date"),)
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("academic_records.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.Enum("present", "absent", name="att_status"), nullable=False)
    marked_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    record = db.relationship("AcademicRecord", back_populates="attendance")


class Prediction(db.Model):
    __tablename__ = "predictions"
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("academic_records.id"), nullable=False)
    feature_set = db.Column(db.String(10), nullable=False)    # full / early
    predicted_g3 = db.Column(db.Float, nullable=False)
    predicted_grade = db.Column(db.String(2), nullable=False)
    pass_probability = db.Column(db.Float, nullable=False)
    risk_level = db.Column(db.String(10), nullable=False)
    model_info = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    record = db.relationship("AcademicRecord", back_populates="predictions")
