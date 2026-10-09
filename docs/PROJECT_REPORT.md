# Student Performance Management and Prediction System

**Domain:** AI / Machine Learning + Full-Stack Web Development
**Category:** Research-based application development

## Abstract

This project builds a web-based system for managing student academic records and predicting
student performance. Admin, teacher and student modules cover record management, marks and
attendance entry, interactive dashboards and ML-based prediction. Decision Tree and Random Forest
models are trained on the UCI Student Performance dataset (1,044 records, 33 attributes).

The Random Forest classifier predicts pass/fail with **91.9% accuracy** (F1 0.947, ROC-AUC 0.970)
when first- and second-period grades are known. Before any grades exist, it still reaches **78.9%**
from demographic, social and school attributes alone. This supports early identification of
at-risk students.

## 1. Introduction

Low achievement and course failure are long-standing concerns in secondary education. Teachers
usually find out that a student is struggling only after the student has failed an assessment.
A system that brings together academic, attendance and background data can flag at-risk students
earlier and support timely intervention.

**Objectives**

1. Store and manage student records, marks and attendance in a relational (MySQL) database.
2. Provide role-based modules for administrators, teachers and students.
3. Analyse performance through interactive dashboards and reports.
4. Train, compare and deploy Decision Tree and Random Forest models that predict:
   * the final grade,
   * the grade band,
   * the risk of failure.

## 2. Dataset

The data is the **UCI Student Performance** dataset (Cortez & Silva, 2008). It describes students
from two Portuguese secondary schools, Gabriel Pereira (GP) and Mousinho da Silveira (MS), in two
subjects:

| File | Subject | Records |
|------|---------|---------|
| `student-mat.csv` | Mathematics | 395 |
| `student-por.csv` | Portuguese language | 649 |

Each record has 30 input attributes and three grades on a 0–20 scale: G1 (first period),
G2 (second period) and G3 (final). The input attributes are:

* **Demographic:** school, sex, age, address, family size, parents' cohabitation status
* **Family:** parents' education and job, guardian, family support, family relationship quality
* **School:** reason for choosing the school, travel time, weekly study time, past failures,
  extra school support, paid classes, absences
* **Social and lifestyle:** activities, nursery, higher-education intention, internet,
  romantic relationship, free time, going out, alcohol consumption, health

The dataset has no missing values.

**Mapping to project requirements**

| Requirement | Dataset attribute |
|---|---|
| Marks | G1, G2, G3 |
| Attendance | absences |
| Previous academic performance | failures (number of past class failures) |

Assignment and practical scores are not in the dataset. The system stores them as teacher-entered
fields and does not use them in the models.

**Integration.** 358 students appear in both subject files. Following the authors' merge script,
they are matched on 13 identity attributes. This gives 686 unique students with 1,044 subject
enrolments, normalised into the `students` and `academic_records` tables.

## 3. Exploratory analysis

All statistics below use the full dataset (1,044 records).

**Overall**

* Pass rate (G3 ≥ 10) is 78.0% and the mean final grade is 11.34.
* Mathematics is harder: 67.1% pass and mean G3 10.42, compared with 84.6% pass and mean G3 11.91
  in Portuguese.

**Grade distribution**

| Grade | A (16–20) | B (14–15) | C (12–13) | D (10–11) | F (0–9) |
|---|---|---|---|---|---|
| Records | 122 | 172 | 216 | 304 | 230 |

**Correlation with G3 (Pearson)**

| Attribute | r |
|---|---|
| G2 | 0.911 |
| G1 | 0.809 |
| failures | −0.383 |
| Medu | 0.201 |
| studytime | 0.162 |
| Fedu | 0.160 |
| Dalc | −0.130 |
| age | −0.125 |
| absences | −0.046 |

**Factor analysis**

| Factor | Group | Pass rate |
|---|---|---|
| Past failures | 0 | 85.0% |
| | 1 | 51.7% |
| | 2 | 33.3% |
| | 3+ | 30.0% |
| Weekly study time | < 2 h | 72.6% |
| | 5–10 h | 85.8% |
| Wants higher education | yes | 80.7% |
| | no | 48.3% |
| Weekend alcohol | level 1 | 80.4% |
| | level 5 | 69.9% |
| School | GP | 81.2% |
| | MS | 68.8% |

**Absences**

* The relationship is not monotonic. Students with 1–5 absences pass more often (83.4%) than those
  with none (76.6%).
* All **53 records with a final grade of 0 also have 0 absences**. These are most likely students
  who dropped out or did not sit the final exam, and their absences were not recorded.
* Beyond 10 absences, the pass rate falls steadily: 66.3% at 11–20 and 52.2% at 21+.

## 4. Methodology

### 4.1 Prediction tasks

| Task | Type | Target |
|---|---|---|
| Pass/fail | binary classification | G3 ≥ 10 |
| Grade band | 5-class classification | A / B / C / D / F (the Erasmus-style bands used by Cortez & Silva) |
| Final grade | regression | G3 (0–20) |

Each task is trained on two feature sets:

* **Full:** all 30 attributes, plus subject, G1 and G2. Used after the second period.
* **Early warning:** the same attributes without G1 and G2. Used at the start of the year.

### 4.2 Pre-processing

* Nominal attributes (school, sex, address, family size, Pstatus, Mjob, Fjob, reason, guardian,
  subject) are one-hot encoded.
* Yes/no attributes become 0/1.
* Ordinal and numeric attributes are used as-is. Tree models need no scaling.

### 4.3 Training and evaluation

1. **Split:** 80/20 train/test (835/209), stratified on the grade band. `random_state=42` for
   reproducibility.
2. **Tuning:** grid search with 5-fold cross-validation on the training set.
   * Decision Tree: `max_depth`, `min_samples_leaf`
   * Random Forest: `n_estimators`, `max_depth`, `min_samples_leaf`
   * Classifiers use `class_weight="balanced"` because there are fewer fail/A cases.
3. **Model selection** uses the CV score: F1 for pass/fail, macro-F1 for grade band, RMSE for
   regression.
4. **Final evaluation** is on the untouched test set. The selected model is then refit on all data
   and saved with joblib.

### 4.4 Deployment logic

* The app uses the *full* model when G1 and G2 are recorded, otherwise the *early-warning* model.
* The pass probability sets the risk level: High < 50%, Medium 50–75%, Low ≥ 75%.
* Rule-based recommendations come from risk attributes such as low G2, a falling G1→G2 trend,
  past failures, ≥ 10 absences, < 2 h weekly study, high alcohol use and no higher-education plans.
* Every prediction is stored in the `predictions` table, which keeps a history.

## 5. Results

Held-out test set (n = 209). The deployed model for each row is in **bold**.

### 5.1 With period grades (full)

| Task | Metric | Decision Tree | Random Forest |
|---|---|---|---|
| Pass/fail | Accuracy | 0.895 | **0.919** |
| | Precision | 0.955 | **0.962** |
| | Recall | 0.908 | **0.933** |
| | F1 | 0.931 | **0.947** |
| | ROC-AUC | 0.920 | **0.970** |
| Grade band | Accuracy | **0.727** | 0.722 |
| | Macro-F1 | **0.724** | 0.712 |
| G3 regression | RMSE | 1.163 | **1.147** |
| | MAE | 0.798 | **0.830** |
| | R² | 0.916 | **0.919** |

Confusion matrix for the Random Forest pass/fail model:

| | Predicted fail | Predicted pass |
|---|---|---|
| **Actual fail** | 40 | 6 |
| **Actual pass** | 11 | 152 |

### 5.2 Early warning (without G1, G2)

| Task | Metric | Decision Tree | Random Forest |
|---|---|---|---|
| Pass/fail | Accuracy | 0.718 | **0.789** |
| | F1 | 0.818 | **0.862** |
| | ROC-AUC | 0.593 | **0.775** |
| Grade band | Accuracy | 0.268 | **0.325** |
| G3 regression | RMSE | 3.716 | **3.330** |
| | R² | 0.147 | **0.315** |

### 5.3 Feature importance (Random Forest, pass/fail)

* **With period grades:** G2 (0.32) and G1 (0.24) dominate. Failures, subject and absences follow.
* **Without period grades:** past failures is the strongest predictor, followed by absences,
  mother's job, age and parents' education.

### 5.4 Discussion

* **Prior grades dominate.** Once G1 and G2 are known, they explain most of the variance in G3:
  R² is about 0.92 and RMSE is about 1.1 grade points. Both models perform well here, and Random
  Forest is only marginally better. These results match those reported by Cortez & Silva (2008).
* **Random Forest matters most without grades.** In the early-warning setting it clearly beats a
  single Decision Tree: +7 points accuracy and +0.18 ROC-AUC. Averaging many trees lowers the
  variance on these weaker, noisier signals.
* **Early warning is useful for pass/fail but not for exact grades.** The early pass/fail model
  catches most failing students in time for intervention. The early 5-class and regression models
  are weak (33% accuracy, R² 0.32), so the app shows early predictions mainly as a pass probability
  and risk level.
* **Errors on failing students.** The full model misses 6 of 46 failing students in the test set
  (recall on the fail class 0.87). All six are borderline cases: G2 was 9–11 and the final grade
  was 9, one point below the pass mark. In practice, teachers should treat Medium-risk students
  near the threshold as needing attention, not only High-risk ones.

## 6. System design

### 6.1 Architecture

Browser (Bootstrap 5, Chart.js) → Flask (blueprints) → SQLAlchemy → MySQL.
Prediction requests go through `ml_service.py`, which loads the trained scikit-learn pipelines
saved with joblib. Training can be started from the admin UI in a background thread.

### 6.2 Database

| Table | Purpose |
|---|---|
| `users` | accounts with role admin, teacher or student |
| `subjects` | Mathematics and Portuguese |
| `students` | identity and family attributes |
| `academic_records` | one row per student per subject: grades, absences, study and lifestyle attributes, assignment and practical scores |
| `attendance` | daily register |
| `predictions` | prediction history |

The DDL is in `database/schema.sql`.

### 6.3 Modules

**Admin**
* KPI dashboard
* Student CRUD and subject enrolment
* User management
* Model training and comparison, with confusion matrix and feature importance
* Batch prediction

**Teacher**
* Subject dashboard
* Bulk marks entry
* Daily attendance, which updates the absence count the model uses
* At-risk list
* Class-wide prediction

**Student**
* Personal dashboard: marks, grade progression chart, predicted grade, risk level and
  recommendations, attendance history

**Shared**
* Search and filter
* Printable student report
* What-if predictor
* Analysis report with 10 charts and a group comparison table
* CSV export

### 6.4 Security

* Passwords are hashed with Werkzeug.
* Route access is enforced per role.
* Teachers can only see and edit records for their own subject.
* Students can only see their own records.

## 7. Limitations and future work

* **Small, regional sample.** The data covers 1,044 records from two Portuguese schools in
  2005–06. Models should be retrained on local institutional data before real use. The system
  supports this through **ML models → Retrain → current database records**.
* **Grade 0 ambiguity.** The dataset does not separate dropouts from students who sat the exam and
  scored 0. A dedicated dropout flag would improve both analysis and prediction.
* **Unused new fields.** Assignment and practical scores are collected but not yet used as features.
  Once enough labelled data exists, they could be added to the early-warning model.
* **Further work:**
  * Per-student explanations (e.g. SHAP values) in place of rule-based recommendations
  * Probability calibration
  * Additional models (gradient boosting)
  * Notifications to guardians for high-risk students

## References

1. P. Cortez and A. Silva. *Using Data Mining to Predict Secondary School Student Performance.*
   Proc. 5th FUture BUsiness TEChnology Conference (FUBUTEC 2008), pp. 5–12, Porto, Portugal, 2008.
2. UCI Machine Learning Repository, Student Performance dataset (ID 320),
   https://archive.ics.uci.edu/dataset/320/student+performance, CC BY 4.0.
3. F. Pedregosa et al. *Scikit-learn: Machine Learning in Python.* JMLR 12, pp. 2825–2830, 2011.
4. L. Breiman. *Random Forests.* Machine Learning 45(1), pp. 5–32, 2001.
