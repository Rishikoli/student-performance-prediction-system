import threading
import traceback

from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import current_user

from config import Config
from ml.pipeline import load_csv_dataset, train_all
from .common import role_required
from .. import db
from ..forms import MARK_FIELDS, RECORD_FIELDS, STUDENT_FIELDS, parse
from ..ml_service import (load_metrics, models_available, predict_records_batch,
                          records_dataframe)
from ..models import AcademicRecord, Prediction, Student, Subject, User

bp = Blueprint("admin", __name__, url_prefix="/admin")

TRAINING = {"running": False, "log": [], "error": None}


@bp.route("/")
@role_required("admin")
def dashboard():
    stats = {
        "students": Student.query.count(),
        "records": AcademicRecord.query.count(),
        "teachers": User.query.filter_by(role="teacher").count(),
        "predictions": Prediction.query.count(),
    }
    return render_template("admin/dashboard.html", stats=stats, metrics=load_metrics(),
                           subjects=Subject.query.all())


# ---------- users ----------
@bp.route("/users")
@role_required("admin")
def users():
    role = request.args.get("role", "staff")
    q = User.query
    q = q.filter(User.role.in_(["admin", "teacher"])) if role == "staff" else q.filter_by(role=role)
    page = q.order_by(User.role, User.username).paginate(
        page=request.args.get("page", 1, type=int), per_page=30)
    return render_template("admin/users.html", page=page, role=role)


@bp.route("/users/new", methods=["GET", "POST"])
@bp.route("/users/<int:uid>/edit", methods=["GET", "POST"])
@role_required("admin")
def user_form(uid=None):
    user = db.get_or_404(User, uid) if uid else None
    if request.method == "POST":
        f = request.form
        username = f.get("username", "").strip().lower()
        role = f.get("role")
        errors = []
        if not username or not f.get("full_name", "").strip():
            errors.append("Username and full name are required.")
        if role not in ("admin", "teacher") and not (user and user.role == "student"):
            errors.append("Invalid role.")
        clash = User.query.filter_by(username=username).first()
        if clash and clash is not user:
            errors.append("Username already exists.")
        if not user and len(f.get("password", "")) < 6:
            errors.append("Password must be at least 6 characters.")
        if role == "teacher" and not f.get("subject_id", type=int):
            errors.append("Teachers must be assigned a subject.")
        if user and user.id == current_user.id and role != "admin":
            errors.append("You cannot remove your own admin role.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            user = user or User(role=role)
            if user.role != "student":
                user.role = role
            user.username, user.full_name = username, f["full_name"].strip()
            user.subject_id = f.get("subject_id", type=int) if user.role == "teacher" else None
            if f.get("password"):
                user.set_password(f["password"])
            db.session.add(user)
            db.session.commit()
            flash("User saved.", "success")
            return redirect(url_for("admin.users", role="student" if user.role == "student" else "staff"))
    return render_template("admin/user_form.html", user=user, subjects=Subject.query.all())


@bp.route("/users/<int:uid>/toggle", methods=["POST"])
@role_required("admin")
def toggle_user(uid):
    user = db.get_or_404(User, uid)
    if user.id == current_user.id:
        flash("You cannot deactivate yourself.", "danger")
    else:
        user.is_active_user = not user.is_active_user
        db.session.commit()
        flash(f"User {'activated' if user.is_active_user else 'deactivated'}.", "success")
    return redirect(request.referrer or url_for("admin.users"))


@bp.route("/users/<int:uid>/delete", methods=["POST"])
@role_required("admin")
def delete_user(uid):
    user = db.get_or_404(User, uid)
    if user.id == current_user.id or user.role == "student":
        flash("This user cannot be deleted here.", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("User deleted.", "success")
    return redirect(url_for("admin.users"))


# ---------- students ----------
@bp.route("/students/new", methods=["GET", "POST"])
@bp.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@role_required("admin")
def student_form(sid=None):
    st = db.get_or_404(Student, sid) if sid else None
    subjects = Subject.query.all()
    fields = STUDENT_FIELDS + ([] if st else RECORD_FIELDS + MARK_FIELDS)
    if request.method == "POST":
        data, errors = parse(request.form, fields)
        subj = request.form.get("subject_id", type=int)
        if not st and subj not in {s.id for s in subjects}:
            errors.append("Choose a subject for the first enrolment.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            sdata = {k: data[k] for k, *_ in STUDENT_FIELDS}
            if st:
                for k, v in sdata.items():
                    setattr(st, k, v)
                if st.user:
                    st.user.full_name = st.name
            else:
                prefix = sdata["school"]
                last = (Student.query.filter(Student.roll_no.like(f"{prefix}%"))
                        .order_by(Student.roll_no.desc()).first())
                n = int(last.roll_no[len(prefix):]) + 1 if last else 1
                st = Student(roll_no=f"{prefix}{n:04d}", **sdata)
                st.records.append(AcademicRecord(
                    subject_id=subj, **{k: data[k] for k, *_ in RECORD_FIELDS + MARK_FIELDS}))
                u = User(username=st.roll_no.lower(), full_name=st.name, role="student")
                pw = request.form.get("password") or "student123"
                u.set_password(pw)
                st.user = u
                db.session.add(st)
            db.session.commit()
            flash(f"Student {st.roll_no} saved." + ("" if sid else
                  f" Login: {st.roll_no.lower()} / {request.form.get('password') or 'student123'}"),
                  "success")
            return redirect(url_for("common.student_detail", sid=st.id))
    return render_template("admin/student_form.html", st=st, subjects=subjects,
                           student_fields=STUDENT_FIELDS,
                           record_fields=[] if st else RECORD_FIELDS + MARK_FIELDS,
                           values=request.form if request.method == "POST" else st)


@bp.route("/students/<int:sid>/delete", methods=["POST"])
@role_required("admin")
def delete_student(sid):
    st = db.get_or_404(Student, sid)
    db.session.delete(st)
    db.session.commit()
    flash(f"Student {st.roll_no} deleted.", "success")
    return redirect(url_for("common.students"))


@bp.route("/records/<int:rid>/delete", methods=["POST"])
@role_required("admin")
def delete_record(rid):
    rec = db.get_or_404(AcademicRecord, rid)
    sid = rec.student_id
    db.session.delete(rec)
    db.session.commit()
    flash("Enrolment removed.", "success")
    return redirect(url_for("common.student_detail", sid=sid))


# ---------- ML models ----------
@bp.route("/models")
@role_required("admin")
def models():
    return render_template("admin/models.html", metrics=load_metrics(), training=TRAINING)


def _train_job(app, source):
    with app.app_context():
        try:
            if source == "database":
                df = records_dataframe()
            else:
                df = load_csv_dataset(Config.DATA_DIR)
            TRAINING["log"].append(f"Training on {len(df)} records from {source}...")
            train_all(df, app.config["MODEL_DIR"], source=source, log=TRAINING["log"].append)
            TRAINING["log"].append("Done.")
        except Exception as e:   # surface failure in UI
            TRAINING["error"] = str(e)
            TRAINING["log"].append(traceback.format_exc())
        finally:
            TRAINING["running"] = False


@bp.route("/models/train", methods=["POST"])
@role_required("admin")
def train():
    if TRAINING["running"]:
        flash("Training already in progress.", "warning")
    else:
        source = "database" if request.form.get("source") == "database" else "csv"
        TRAINING.update(running=True, log=[], error=None)
        threading.Thread(target=_train_job, args=(current_app._get_current_object(), source),
                         daemon=True).start()
        flash("Training started. This takes about a minute.", "info")
    return redirect(url_for("admin.models"))


@bp.route("/models/status")
@role_required("admin")
def train_status():
    return jsonify(TRAINING)


@bp.route("/predict-all", methods=["POST"])
@role_required("admin")
def predict_all():
    if not models_available():
        flash("Train the models first.", "warning")
        return redirect(url_for("admin.models"))
    n = predict_records_batch(AcademicRecord.query.all())
    db.session.commit()
    flash(f"Generated predictions for {n} academic records.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))
