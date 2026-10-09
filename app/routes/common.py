import csv
import io
from functools import wraps

from flask import (Blueprint, Response, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required
from sqlalchemy import or_

from .. import db
from ..forms import MARK_FIELDS, RECORD_FIELDS, STUDENT_FIELDS, parse
from ..ml_service import (load_metrics, models_available, predict_record, predict_row,
                          record_to_row, recommendations)
from ..models import AcademicRecord, Student, Subject

bp = Blueprint("common", __name__)


def role_required(*roles):
    def deco(f):
        @wraps(f)
        @login_required
        def wrapper(*a, **kw):
            if current_user.role not in roles:
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco


def scoped_records():
    """Academic records visible to the current staff user."""
    q = AcademicRecord.query.join(Student).join(Subject)
    if current_user.role == "teacher":
        q = q.filter(AcademicRecord.subject_id == current_user.subject_id)
    return q


def can_view_student(st):
    if current_user.role == "admin":
        return True
    if current_user.role == "student":
        return current_user.student_id == st.id
    return any(r.subject_id == current_user.subject_id for r in st.records)


def can_edit_record(rec):
    return current_user.role == "admin" or (
        current_user.role == "teacher" and rec.subject_id == current_user.subject_id)


@bp.route("/")
@login_required
def index():
    return redirect(url_for({"admin": "admin.dashboard", "teacher": "teacher.dashboard",
                             "student": "student.dashboard"}[current_user.role]))


@bp.route("/students")
@role_required("admin", "teacher")
def students():
    q = scoped_records()
    s = request.args.get("q", "").strip()
    if s:
        q = q.filter(or_(Student.roll_no.ilike(f"%{s}%"), Student.name.ilike(f"%{s}%")))
    for f in ("school", "sex"):
        if request.args.get(f):
            q = q.filter(getattr(Student, f) == request.args[f])
    if request.args.get("subject") and current_user.role == "admin":
        q = q.filter(Subject.code == request.args["subject"])
    status = request.args.get("status")
    if status == "pass":
        q = q.filter(AcademicRecord.G3 >= 10)
    elif status == "fail":
        q = q.filter(AcademicRecord.G3 < 10)
    elif status == "pending":
        q = q.filter(AcademicRecord.G3.is_(None))
    sort = request.args.get("sort", "roll")
    order = {"roll": Student.roll_no, "g3": AcademicRecord.G3.desc(),
             "g3_asc": AcademicRecord.G3.asc(), "absences": AcademicRecord.absences.desc()}
    q = q.order_by(order.get(sort, Student.roll_no), Subject.code)
    page = q.paginate(page=request.args.get("page", 1, type=int), per_page=25)
    args = {k: v for k, v in request.args.items() if k != "page"}
    return render_template("common/students.html", page=page, args=args)


@bp.route("/students/<int:sid>")
@login_required
def student_detail(sid):
    st = db.get_or_404(Student, sid)
    if not can_view_student(st):
        abort(403)
    tips = {r.id: recommendations(record_to_row(r), r.latest_prediction.pass_probability)
            for r in st.records if r.latest_prediction}
    return render_template("common/student_detail.html", st=st, can_edit_record=can_edit_record,
                           subjects=Subject.query.all(), tips=tips)


@bp.route("/records/<int:rid>/edit", methods=["GET", "POST"])
@role_required("admin", "teacher")
def edit_record(rid):
    rec = db.get_or_404(AcademicRecord, rid)
    if not can_edit_record(rec):
        abort(403)
    if request.method == "POST":
        data, errors = parse(request.form, RECORD_FIELDS + MARK_FIELDS)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            for k, v in data.items():
                setattr(rec, k, v)
            db.session.commit()
            flash("Academic record updated.", "success")
            return redirect(url_for("common.student_detail", sid=rec.student_id))
    return render_template("common/record_form.html", rec=rec, st=rec.student,
                           fields=RECORD_FIELDS + MARK_FIELDS, values=rec)


@bp.route("/students/<int:sid>/enrol", methods=["GET", "POST"])
@role_required("admin")
def add_record(sid):
    st = db.get_or_404(Student, sid)
    taken = {r.subject_id for r in st.records}
    available = [s for s in Subject.query.all() if s.id not in taken]
    if not available:
        flash("Student is already enrolled in all subjects.", "info")
        return redirect(url_for("common.student_detail", sid=sid))
    if request.method == "POST":
        data, errors = parse(request.form, RECORD_FIELDS + MARK_FIELDS)
        subj = request.form.get("subject_id", type=int)
        if subj not in {s.id for s in available}:
            errors.append("Choose a subject.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db.session.add(AcademicRecord(student_id=sid, subject_id=subj, **data))
            db.session.commit()
            flash("Enrolment added.", "success")
            return redirect(url_for("common.student_detail", sid=sid))
    return render_template("common/record_form.html", rec=None, st=st, subjects=available,
                           fields=RECORD_FIELDS + MARK_FIELDS, values=request.form)


@bp.route("/records/<int:rid>/predict", methods=["POST"])
@login_required
def predict(rid):
    rec = db.get_or_404(AcademicRecord, rid)
    if not can_view_student(rec.student):
        abort(403)
    if not models_available():
        flash("No trained model found. Ask the administrator to train the models.", "warning")
    else:
        predict_record(rec)
        db.session.commit()
        flash(f"Prediction generated for {rec.subject.name}.", "success")
    return redirect(url_for("common.student_detail", sid=rec.student_id) + f"#rec{rec.id}")


@bp.route("/predict", methods=["GET", "POST"])
@role_required("admin", "teacher")
def what_if():
    result, values = None, request.form
    if request.method == "POST":
        fields = STUDENT_FIELDS[1:] + RECORD_FIELDS + MARK_FIELDS[:3]
        data, errors = parse(request.form, fields)
        subj = request.form.get("subject")
        if subj not in ("MAT", "POR"):
            errors.append("Choose a subject.")
        if errors:
            for e in errors:
                flash(e, "danger")
        elif not models_available():
            flash("No trained model found.", "warning")
        else:
            data["subject"] = subj
            result = predict_row(data)
    return render_template("common/predict.html", student_fields=STUDENT_FIELDS[1:],
                           record_fields=RECORD_FIELDS, mark_fields=MARK_FIELDS[:3],
                           values=values, result=result)


@bp.route("/reports")
@role_required("admin", "teacher")
def reports():
    return render_template("common/reports.html", metrics=load_metrics(),
                           subjects=Subject.query.all())


@bp.route("/reports/export.csv")
@role_required("admin", "teacher")
def export_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["roll_no", "name", "school", "subject", "absences", "G1", "G2", "G3", "grade",
                "assignment_score", "practical_score", "predicted_g3", "pass_probability",
                "risk_level"])
    for r in scoped_records().order_by(Student.roll_no, Subject.code).all():
        p = r.latest_prediction
        w.writerow([r.student.roll_no, r.student.name, r.student.school, r.subject.code,
                    r.absences, r.G1, r.G2, r.G3, r.grade or "", r.assignment_score,
                    r.practical_score, p.predicted_g3 if p else "",
                    p.pass_probability if p else "", p.risk_level if p else ""])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=performance_report.csv"})
