"""JSON endpoints feeding the Chart.js dashboards."""
import numpy as np
import pandas as pd
from flask import Blueprint, abort, jsonify, request
from flask_login import current_user

from ml.pipeline import NUMERIC, PERIOD_GRADES, to_grade
from .common import can_view_student, role_required
from .. import db
from ..ml_service import records_dataframe
from ..models import AcademicRecord, Prediction, Student, Subject

bp = Blueprint("api", __name__, url_prefix="/api")


def _group(df, col, order=None, labels=None):
    g = df.groupby(col)["G3"].agg(["mean", "count", lambda s: (s >= 10).mean() * 100])
    g.columns = ["avg", "n", "pass_rate"]
    order = order if order is not None else sorted(g.index)
    g = g.reindex(order)
    return {"labels": [labels.get(k, str(k)) if labels else str(k) for k in order],
            "avg_g3": [round(v, 2) if pd.notna(v) else None for v in g["avg"]],
            "pass_rate": [round(v, 1) if pd.notna(v) else None for v in g["pass_rate"]],
            "n": [int(v) if pd.notna(v) else 0 for v in g["n"]]}


@bp.route("/stats")
@role_required("admin", "teacher")
def stats():
    df = records_dataframe()
    subj = request.args.get("subject", "all")
    if current_user.role == "teacher":
        subj = db.session.get(Subject, current_user.subject_id).code
    if subj in ("MAT", "POR"):
        df = df[df["subject"] == subj]
    if df.empty:
        return jsonify({"empty": True})

    df = df.assign(grade=to_grade(df["G3"]))
    grade_counts = df["grade"].value_counts().reindex(list("ABCDF"), fill_value=0)
    by_subject = {}
    for code, g in df.groupby("subject"):
        by_subject[code] = {"G1": round(g.G1.mean(), 2), "G2": round(g.G2.mean(), 2),
                            "G3": round(g.G3.mean(), 2),
                            "pass_rate": round((g.G3 >= 10).mean() * 100, 1), "n": len(g)}

    df["abs_bucket"] = pd.cut(df["absences"], [-1, 0, 5, 10, 20, 100],
                              labels=["0", "1-5", "6-10", "11-20", "21+"])
    corr = (df[NUMERIC + PERIOD_GRADES + ["G3"]].corr(numeric_only=True)["G3"]
            .drop("G3").sort_values(key=np.abs, ascending=False))

    # latest prediction per record -> risk distribution
    latest = db.session.query(db.func.max(Prediction.id)).join(AcademicRecord).join(Subject)
    if subj in ("MAT", "POR"):
        latest = latest.filter(Subject.code == subj)
    latest = latest.group_by(Prediction.record_id)
    risk = dict(db.session.query(Prediction.risk_level, db.func.count())
                .filter(Prediction.id.in_(latest)).group_by(Prediction.risk_level).all())

    scatter = {code: g[["G2", "G3"]].values.tolist() for code, g in df.groupby("subject")}
    return jsonify({
        "n": len(df),
        "pass_rate": round((df.G3 >= 10).mean() * 100, 1),
        "avg_g3": round(df.G3.mean(), 2),
        "avg_absences": round(df.absences.mean(), 2),
        "grade_dist": {"labels": list(grade_counts.index), "values": grade_counts.tolist()},
        "by_subject": by_subject,
        "studytime": _group(df, "studytime", [1, 2, 3, 4],
                            {1: "<2h", 2: "2-5h", 3: "5-10h", 4: ">10h"}),
        "failures": _group(df, "failures", [0, 1, 2, 3], {3: "3+"}),
        "absences": _group(df, "abs_bucket", ["0", "1-5", "6-10", "11-20", "21+"]),
        "higher": _group(df, "higher", [1, 0], {1: "Yes", 0: "No"}),
        "walc": _group(df, "Walc", [1, 2, 3, 4, 5]),
        "school": _group(df, "school", ["GP", "MS"]),
        "sex": _group(df, "sex", ["F", "M"], {"F": "Female", "M": "Male"}),
        "correlation": {"labels": list(corr.index), "values": [round(v, 3) for v in corr]},
        "risk": {k: risk.get(k, 0) for k in ("Low", "Medium", "High")},
        "scatter": scatter,
    })


@bp.route("/student/<int:sid>")
def student(sid):
    st = db.get_or_404(Student, sid)
    if not current_user.is_authenticated or not can_view_student(st):
        abort(403)
    out = []
    for r in st.records:
        p = r.latest_prediction
        out.append({"subject": r.subject.name, "code": r.subject.code,
                    "grades": [r.G1, r.G2, r.G3],
                    "predicted_g3": p.predicted_g3 if p else None})
    return jsonify(out)
