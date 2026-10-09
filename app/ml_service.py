import json
import os
import threading

import joblib
import pandas as pd
from flask import current_app

from ml.pipeline import BINARY, FEATURE_SETS, prepare
from . import db
from .models import AcademicRecord, Prediction, Student, Subject

_cache = {}
_lock = threading.Lock()

STUDENT_COLS = ["school", "sex", "age", "address", "famsize", "Pstatus", "Medu", "Fedu",
                "Mjob", "Fjob", "reason", "nursery", "internet"]
RECORD_COLS = ["guardian", "traveltime", "studytime", "failures", "schoolsup", "famsup",
               "paid", "activities", "higher", "romantic", "famrel", "freetime", "goout",
               "Dalc", "Walc", "health", "absences", "G1", "G2", "G3"]


def _model(key):
    path = os.path.join(current_app.config["MODEL_DIR"], f"{key}.joblib")
    mtime = os.path.getmtime(path)
    with _lock:
        if key not in _cache or _cache[key][0] != mtime:
            _cache[key] = (mtime, joblib.load(path))
        return _cache[key][1]


def models_available():
    return os.path.exists(os.path.join(current_app.config["MODEL_DIR"], "metrics.json"))


def load_metrics():
    path = os.path.join(current_app.config["MODEL_DIR"], "metrics.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def record_to_row(rec: AcademicRecord):
    row = {c: getattr(rec.student, c) for c in STUDENT_COLS}
    row.update({c: getattr(rec, c) for c in RECORD_COLS})
    row["subject"] = rec.subject.code
    return row


def records_dataframe(only_graded=True):
    q = (AcademicRecord.query.join(Student).join(Subject)
         .options(db.joinedload(AcademicRecord.student), db.joinedload(AcademicRecord.subject)))
    if only_graded:
        q = q.filter(AcademicRecord.G3.isnot(None), AcademicRecord.G1.isnot(None),
                     AcademicRecord.G2.isnot(None))
    df = pd.DataFrame([record_to_row(r) for r in q.all()])
    for c in BINARY:
        df[c] = df[c].astype(int)
    return df


def risk_from_probability(p):
    if p < 0.5:
        return "High"
    if p < 0.75:
        return "Medium"
    return "Low"


def predict_row(row):
    """Predict for a dict of raw attributes. Uses the full model if G1 and G2 are known."""
    fs = "full" if row.get("G1") is not None and row.get("G2") is not None else "early"
    df = prepare(pd.DataFrame([row]))[FEATURE_SETS[fs]]
    pass_model = _model(f"{fs}_pass")
    p_pass = float(pass_model.predict_proba(df)[0][list(pass_model.classes_).index(1)])
    g3 = float(min(20, max(0, _model(f"{fs}_g3").predict(df)[0])))
    grade = str(_model(f"{fs}_grade").predict(df)[0])
    best = (load_metrics() or {}).get("best", {})
    return {
        "feature_set": fs,
        "predicted_g3": round(g3, 1),
        "predicted_grade": grade,
        "pass_probability": round(p_pass, 3),
        "risk_level": risk_from_probability(p_pass),
        "model_info": f"pass:{best.get(fs + '_pass')} grade:{best.get(fs + '_grade')} "
                      f"g3:{best.get(fs + '_g3')}",
        "recommendations": recommendations(row, p_pass),
    }


def predict_record(rec: AcademicRecord, save=True):
    row = record_to_row(rec)
    row.pop("G3", None)
    result = predict_row(row)
    if save:
        db.session.add(Prediction(record_id=rec.id, **{k: v for k, v in result.items()
                                                       if k != "recommendations"}))
    return result


def predict_records_batch(records):
    """Vectorised prediction for many records; saves a Prediction for each. Returns count."""
    best = (load_metrics() or {}).get("best", {})
    groups = {"full": [], "early": []}
    for rec in records:
        groups["full" if rec.G1 is not None and rec.G2 is not None else "early"].append(rec)
    for fs, recs in groups.items():
        if not recs:
            continue
        df = prepare(pd.DataFrame([record_to_row(r) for r in recs]))[FEATURE_SETS[fs]]
        pm = _model(f"{fs}_pass")
        probs = pm.predict_proba(df)[:, list(pm.classes_).index(1)]
        g3s = _model(f"{fs}_g3").predict(df)
        grades = _model(f"{fs}_grade").predict(df)
        info = f"pass:{best.get(fs + '_pass')} grade:{best.get(fs + '_grade')} g3:{best.get(fs + '_g3')}"
        db.session.add_all([
            Prediction(record_id=r.id, feature_set=fs, predicted_g3=round(float(min(20, max(0, g))), 1),
                       predicted_grade=str(gr), pass_probability=round(float(p), 3),
                       risk_level=risk_from_probability(p), model_info=info)
            for r, p, g, gr in zip(recs, probs, g3s, grades)])
    return sum(len(v) for v in groups.values())


def recommendations(row, p_pass):
    tips = []
    def g(k, default=0):
        return row[k] if row.get(k) is not None else default

    if row.get("G2") is not None and row["G2"] < 10:
        tips.append("Second-period grade is below passing; schedule remedial sessions before finals.")
    elif row.get("G1") is not None and row.get("G2") is not None and row["G2"] < row["G1"] - 1:
        tips.append("Grades are trending down from period 1 to 2; review recent topics with the student.")
    if g("failures") > 0:
        tips.append(f"{row['failures']} previous class failure(s); consider mentoring or school support.")
    if g("absences") >= 10:
        tips.append(f"High absences ({row['absences']}); follow up with guardian on attendance.")
    if g("studytime", 2) <= 1:
        tips.append("Weekly study time under 2 hours; set a structured study plan.")
    if g("Dalc", 1) >= 3 or g("Walc", 1) >= 4:
        tips.append("Elevated alcohol consumption reported; consider counselling referral.")
    if g("goout", 3) >= 5:
        tips.append("Very frequent going out; encourage balance with study time.")
    if not g("higher", 1):
        tips.append("Student does not plan higher education; career guidance may improve motivation.")
    if not g("schoolsup", 0) and p_pass < 0.5:
        tips.append("Not receiving extra educational support; enrol in school support program.")
    if not tips:
        tips.append("No major risk factors detected; maintain current study habits.")
    return tips
