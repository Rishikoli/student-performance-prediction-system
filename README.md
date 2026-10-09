# Student Performance Management and Prediction System (SPMS)

A web application for managing student academic records and predicting performance with
machine learning. It is built on the
[UCI Student Performance dataset](https://archive.ics.uci.edu/dataset/320/student+performance).

**Stack:** Flask · MySQL (SQLAlchemy) · scikit-learn (Decision Tree, Random Forest) · pandas / NumPy ·
Bootstrap 5 · Chart.js

## Features

| Module  | What it does |
|---------|--------------|
| **Admin**   | Dashboard KPIs and charts; manage students (add, edit, delete, enrol in subjects); manage staff and student accounts; train and compare ML models; predict for all students |
| **Teacher** | Subject dashboard; bulk marks entry (G1, G2, G3, assignment, practical); daily attendance register; list of at-risk students; prediction for their own class |
| **Student** | Own profile, marks, grade progression chart, predicted final grade, risk level, recommendations, attendance history |
| **Shared**  | Searchable and filterable student list; student report (printable); what-if predictor; performance analysis report with 10 charts; CSV export |

## Login credentials (roles, usernames, passwords)

These demo accounts are created by `python seed.py`:

| Role | Username | Password | Access |
|------|----------|----------|--------|
| **Admin** | `admin` | `admin123` | Everything: dashboard, all students, add/edit/delete students, user management, ML model training, batch prediction, reports |
| **Teacher (Mathematics)** | `teacher_math` | `teacher123` | Mathematics students only: marks entry, attendance, at-risk list, predictions, reports |
| **Teacher (Portuguese)** | `teacher_por` | `teacher123` | Portuguese students only: marks entry, attendance, at-risk list, predictions, reports |
| **Student** | roll number in lowercase, e.g. `gp0001`, `gp0002`, `ms0001` | `student123` | Own profile, marks, grade chart, predicted grade, risk level, recommendations, attendance |

* Student roll numbers run from `gp0001` to `gp0452` (Gabriel Pereira school) and from `ms0001` to `ms0234` (Mousinho da Silveira school), 686 students in total.
* Any user can change their password from **Change password** in the sidebar.
* The admin can create more teachers or admins under **Users → New staff user**.
* A student account is created automatically for each student the admin adds.

> These are demo credentials for evaluation. Change them, and set `SECRET_KEY`, before any real deployment.

## Quick start

```bash
cd StudentPerformanceSystem
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python seed.py          # create tables + import the 1,044 UCI records
python -m ml.train      # optional: pre-trained models are already in ml/models/
python run.py           # http://127.0.0.1:5000
```

Without `DATABASE_URL` the app uses a local SQLite file (`database/spms.db`) so it runs anywhere.

### Using MySQL

```sql
CREATE DATABASE student_performance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'spms_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON student_performance.* TO 'spms_user'@'localhost';
```

```bash
export DATABASE_URL="mysql+pymysql://spms_user:your_password@localhost/student_performance"
export SECRET_KEY="some-long-random-string"
python seed.py --reset
python run.py
```

`database/schema.sql` has the equivalent MySQL DDL, generated from the models, for reference
or manual setup.

## Dataset → database mapping

The UCI files contain 395 Mathematics and 649 Portuguese records. 358 students appear in both. They
are matched on the 13 identity attributes used by the dataset's own `student-merge.R`, which gives
**686 students** and **1,044 academic records**. The dataset has no student names, so each student
is labelled by roll number (`GP0001`, `MS0001`, …).

| Table | Contents |
|-------|----------|
| `students` | identity and family attributes: school, sex, age, address, famsize, Pstatus, Medu, Fedu, Mjob, Fjob, reason, nursery, internet |
| `academic_records` | one row per student per subject: G1, G2, G3, absences, failures, studytime, support, lifestyle attributes, plus `assignment_score` and `practical_score` |
| `attendance` | daily present/absent entries; marking absent updates `academic_records.absences` |
| `predictions` | history of model outputs (predicted G3, grade band, pass probability, risk level) |
| `users`, `subjects` | accounts (admin/teacher/student) and courses |

`assignment_score` and `practical_score` are **not in the UCI dataset**. They are empty for imported
records and are filled in by teachers. The ML models do not use them.

## Machine learning

* **Targets:** pass/fail (G3 ≥ 10), 5-level grade (A ≥ 16, B 14–15, C 12–13, D 10–11, F < 10),
  and the final grade G3 (regression).
* **Feature sets:**
  * *full*: all attributes plus G1 and G2.
  * *early warning*: no period grades, for use before any exam.
* **Algorithms:** Decision Tree and Random Forest. Hyper-parameters are tuned with 5-fold CV on an
  80% stratified split and evaluated on the held-out 20%. The model with the best CV score is
  refit on all data and deployed.
* The app uses the full model when G1 and G2 are present, otherwise the early-warning model.
* Risk level comes from the pass probability: High < 50%, Medium < 75%, Low ≥ 75%.

Results on the held-out test set (209 records):

| Task | Features | Decision Tree | Random Forest |
|------|----------|---------------|---------------|
| Pass/fail accuracy | full  | 0.895 | **0.919** (F1 0.947, AUC 0.970) |
| Pass/fail accuracy | early | 0.718 | **0.789** (F1 0.862, AUC 0.775) |
| 5-level accuracy   | full  | **0.727** | 0.722 |
| 5-level accuracy   | early | 0.268 | **0.325** |
| G3 RMSE            | full  | 1.163 | **1.147** (R² 0.919) |
| G3 RMSE            | early | 3.716 | **3.330** (R² 0.315) |

Retrain from the UI (**ML models → Retrain**), from either the original CSV or the current
database records, or from the command line:

```bash
python -m ml.train        # from data/*.csv
python -m ml.train --db   # from the database (includes teacher edits)
```

## Project structure

```
StudentPerformanceSystem/
├── run.py                  # entry point
├── config.py               # DATABASE_URL / SECRET_KEY
├── seed.py                 # create tables, import UCI dataset, demo users
├── requirements.txt
├── app/
│   ├── __init__.py         # app factory
│   ├── models.py           # SQLAlchemy models
│   ├── forms.py            # field specs + validation (from UCI attribute descriptions)
│   ├── ml_service.py       # model loading, prediction, recommendations
│   ├── routes/             # auth, admin, teacher, student, common, api (chart JSON)
│   ├── templates/          # Jinja2 + Bootstrap 5
│   └── static/             # style.css, charts.js (Chart.js helpers)
├── ml/
│   ├── pipeline.py         # preprocessing, DT/RF training, evaluation
│   ├── train.py            # CLI
│   └── models/             # trained .joblib models + metrics.json
├── data/                   # UCI csv files + attribute description
├── database/schema.sql     # MySQL DDL
└── docs/PROJECT_REPORT.md  # project / research report
```

## Dataset citation

P. Cortez and A. Silva. *Using Data Mining to Predict Secondary School Student Performance.*
In A. Brito and J. Teixeira (Eds.), Proceedings of the 5th FUture BUsiness TEChnology Conference
(FUBUTEC 2008), pp. 5–12, Porto, Portugal, April 2008, EUROSIS.
Dataset licence: CC BY 4.0.
