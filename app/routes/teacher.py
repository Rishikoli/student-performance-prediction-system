from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .common import role_required, scoped_records
from .. import db
from ..ml_service import models_available, predict_records_batch
from ..models import AcademicRecord, Attendance, Prediction, Student

bp = Blueprint("teacher", __name__, url_prefix="/teacher")


def _int_or_none(v, lo, hi):
    v = (v or "").strip()
    if v == "":
        return None
    n = float(v)
    if not lo <= n <= hi:
        raise ValueError
    return n


@bp.route("/")
@role_required("teacher")
def dashboard():
    q = scoped_records()
    total = q.count()
    graded = q.filter(AcademicRecord.G3.isnot(None))
    stats = {
        "students": total,
        "pass_rate": (graded.filter(AcademicRecord.G3 >= 10).count() / graded.count() * 100)
        if graded.count() else 0,
        "avg_g3": db.session.query(db.func.avg(AcademicRecord.G3))
        .filter(AcademicRecord.subject_id == current_user.subject_id).scalar() or 0,
        "avg_abs": db.session.query(db.func.avg(AcademicRecord.absences))
        .filter(AcademicRecord.subject_id == current_user.subject_id).scalar() or 0,
    }
    return render_template("teacher/dashboard.html", stats=stats, at_risk=_at_risk(limit=10))


def _at_risk(limit=None):
    latest = (db.session.query(db.func.max(Prediction.id))
              .join(AcademicRecord)
              .filter(AcademicRecord.subject_id == current_user.subject_id)
              .group_by(Prediction.record_id))
    q = (Prediction.query.filter(Prediction.id.in_(latest), Prediction.risk_level != "Low")
         .order_by(Prediction.pass_probability))
    return q.limit(limit).all() if limit else q.all()


@bp.route("/marks", methods=["GET", "POST"])
@role_required("teacher")
def marks():
    if request.method == "POST":
        updated, bad = 0, []
        recs = {r.id: r for r in scoped_records().filter(
            AcademicRecord.id.in_([int(k[4:]) for k in request.form if k.startswith("rid_")])).all()}
        for rid, rec in recs.items():
            try:
                vals = {
                    "G1": _int_or_none(request.form.get(f"G1_{rid}"), 0, 20),
                    "G2": _int_or_none(request.form.get(f"G2_{rid}"), 0, 20),
                    "G3": _int_or_none(request.form.get(f"G3_{rid}"), 0, 20),
                    "assignment_score": _int_or_none(request.form.get(f"as_{rid}"), 0, 100),
                    "practical_score": _int_or_none(request.form.get(f"ps_{rid}"), 0, 100),
                }
            except ValueError:
                bad.append(rec.student.roll_no)
                continue
            for k in ("G1", "G2", "G3"):
                if vals[k] is not None:
                    vals[k] = int(vals[k])
            changed = False
            for k, v in vals.items():
                if getattr(rec, k) != v:
                    setattr(rec, k, v)
                    changed = True
            updated += changed
        db.session.commit()
        if bad:
            flash("Invalid values (grades 0-20, scores 0-100) for: " + ", ".join(bad), "danger")
        flash(f"Saved marks for {updated} student(s).", "success")
        return redirect(request.url)
    s = request.args.get("q", "").strip()
    q = scoped_records()
    if s:
        q = q.filter(Student.roll_no.ilike(f"%{s}%") | Student.name.ilike(f"%{s}%"))
    page = q.order_by(Student.roll_no).paginate(page=request.args.get("page", 1, type=int),
                                                per_page=30)
    return render_template("teacher/marks.html", page=page, q=s)


@bp.route("/attendance", methods=["GET", "POST"])
@role_required("teacher")
def attendance():
    try:
        day = date.fromisoformat(request.values.get("date", date.today().isoformat()))
    except ValueError:
        day = date.today()
    s = request.args.get("q", "").strip()
    q = scoped_records()
    if s:
        q = q.filter(Student.roll_no.ilike(f"%{s}%") | Student.name.ilike(f"%{s}%"))
    page = q.order_by(Student.roll_no).paginate(page=request.args.get("page", 1, type=int),
                                                per_page=40)
    if request.method == "POST":
        n = 0
        for rec in page.items:
            status = request.form.get(f"st_{rec.id}")
            if status not in ("present", "absent"):
                continue
            existing = Attendance.query.filter_by(record_id=rec.id, date=day).first()
            prev = existing.status if existing else None
            if prev == status:
                continue
            # keep the absences counter (a model feature) in sync with the register
            if status == "absent":
                rec.absences += 1
            elif prev == "absent":
                rec.absences = max(0, rec.absences - 1)
            if existing:
                existing.status = status
            else:
                db.session.add(Attendance(record_id=rec.id, date=day, status=status,
                                          marked_by=current_user.id))
            n += 1
        db.session.commit()
        flash(f"Attendance saved for {day.isoformat()} ({n} change(s)).", "success")
        return redirect(url_for("teacher.attendance", date=day.isoformat(), q=s,
                                page=page.page))
    marked = {a.record_id: a.status for a in Attendance.query.filter(
        Attendance.date == day, Attendance.record_id.in_([r.id for r in page.items])).all()}
    return render_template("teacher/attendance.html", page=page, day=day, marked=marked, q=s)


@bp.route("/at-risk")
@role_required("teacher")
def at_risk():
    return render_template("teacher/at_risk.html", preds=_at_risk())


@bp.route("/predict-all", methods=["POST"])
@role_required("teacher")
def predict_all():
    if not models_available():
        flash("No trained model available yet.", "warning")
    else:
        n = predict_records_batch(scoped_records().all())
        db.session.commit()
        flash(f"Generated predictions for {n} students.", "success")
    return redirect(request.referrer or url_for("teacher.dashboard"))
