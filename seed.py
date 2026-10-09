"""Create tables and import the UCI Student Performance dataset.

    python seed.py            # create tables + import (skips if data already present)
    python seed.py --reset    # drop everything and re-import
"""
import os
import sys

import pandas as pd
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import AcademicRecord, Student, Subject, User
from app.ml_service import RECORD_COLS, STUDENT_COLS

BOOL_COLS = {"nursery", "internet", "schoolsup", "famsup", "paid", "activities", "higher",
             "romantic"}
DEFAULT_STUDENT_PASSWORD = "student123"


def conv(col, v):
    if col in BOOL_COLS:
        return v == "yes"
    return int(v) if isinstance(v, (int, float)) or str(v).isdigit() else v


def import_dataset(data_dir):
    subjects = {"MAT": Subject(code="MAT", name="Mathematics"),
                "POR": Subject(code="POR", name="Portuguese Language")}
    db.session.add_all(subjects.values())
    db.session.flush()

    # Students in both files are matched on the 13 identity attributes used by the
    # dataset authors' student-merge.R; ambiguous (duplicate) keys are kept separate.
    students = {}
    counter = {"GP": 0, "MS": 0}
    n_records = 0
    for code, fname in (("MAT", "student-mat.csv"), ("POR", "student-por.csv")):
        df = pd.read_csv(os.path.join(data_dir, fname), sep=";")
        dup = df.duplicated(STUDENT_COLS, keep=False)
        for i, r in df.iterrows():
            key = tuple(r[c] for c in STUDENT_COLS)
            st = students.get(key) if not dup[i] else None
            if st is None or any(rec.subject_id == subjects[code].id for rec in st.records):
                counter[r["school"]] += 1
                roll = f"{r['school']}{counter[r['school']]:04d}"
                st = Student(roll_no=roll, name=f"Student {roll}",
                             **{c: conv(c, r[c]) for c in STUDENT_COLS})
                db.session.add(st)
                if not dup[i]:
                    students[key] = st
            st.records.append(AcademicRecord(subject_id=subjects[code].id,
                                             **{c: conv(c, r[c]) for c in RECORD_COLS}))
            n_records += 1
    db.session.flush()
    return subjects, n_records


def create_users(subjects):
    admin = User(username="admin", full_name="System Administrator", role="admin")
    admin.set_password("admin123")
    t1 = User(username="teacher_math", full_name="Mathematics Teacher", role="teacher",
              subject_id=subjects["MAT"].id)
    t1.set_password("teacher123")
    t2 = User(username="teacher_por", full_name="Portuguese Teacher", role="teacher",
              subject_id=subjects["POR"].id)
    t2.set_password("teacher123")
    db.session.add_all([admin, t1, t2])
    # one hash reused for the demo student accounts (hashing ~700 passwords is slow)
    pw_hash = generate_password_hash(DEFAULT_STUDENT_PASSWORD)
    for st in Student.query.all():
        db.session.add(User(username=st.roll_no.lower(), full_name=st.name, role="student",
                            student_id=st.id, password_hash=pw_hash))


def main():
    app = create_app()
    with app.app_context():
        if "--reset" in sys.argv:
            db.drop_all()
        db.create_all()
        if Subject.query.first():
            print("Database already seeded (use --reset to re-import).")
            return
        subjects, n = import_dataset(app.config["DATA_DIR"])
        create_users(subjects)
        db.session.commit()
        print(f"Imported {Student.query.count()} students, {n} academic records.")
        print("Logins: admin/admin123, teacher_math/teacher123, teacher_por/teacher123, "
              f"students <roll no e.g. gp0001>/{DEFAULT_STUDENT_PASSWORD}")


if __name__ == "__main__":
    main()
