"""Training / evaluation pipeline for student performance prediction.

Tasks (target derived from final grade G3, 0-20):
  * pass     - binary, pass if G3 >= 10
  * grade    - 5-level (A/B/C/D/F) per Cortez & Silva (2008)
  * g3       - regression of the final grade

Feature sets:
  * full  - all attributes including period grades G1, G2
  * early - without G1, G2 (early-warning before any exam)

Algorithms compared: Decision Tree and Random Forest (scikit-learn).
"""
import json
import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (accuracy_score, f1_score, precision_score, recall_score,
                             roc_auc_score, confusion_matrix, mean_absolute_error,
                             mean_squared_error, r2_score)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

RANDOM_STATE = 42

CATEGORICAL = ["subject", "school", "sex", "address", "famsize", "Pstatus", "Mjob", "Fjob",
               "reason", "guardian"]
BINARY = ["schoolsup", "famsup", "paid", "activities", "nursery", "higher", "internet",
          "romantic"]
NUMERIC = ["age", "Medu", "Fedu", "traveltime", "studytime", "failures", "famrel",
           "freetime", "goout", "Dalc", "Walc", "health", "absences"]
PERIOD_GRADES = ["G1", "G2"]

FEATURE_SETS = {
    "full": CATEGORICAL + BINARY + NUMERIC + PERIOD_GRADES,
    "early": CATEGORICAL + BINARY + NUMERIC,
}
GRADE_LABELS = ["A", "B", "C", "D", "F"]


def to_grade(g3):
    g3 = np.asarray(g3)
    return np.select([g3 >= 16, g3 >= 14, g3 >= 12, g3 >= 10], ["A", "B", "C", "D"], "F")


def load_csv_dataset(data_dir):
    frames = []
    for code, fname in (("MAT", "student-mat.csv"), ("POR", "student-por.csv")):
        df = pd.read_csv(os.path.join(data_dir, fname), sep=";")
        df.insert(0, "subject", code)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def prepare(df):
    """Normalise a raw frame (csv or db) so binary columns are 0/1 ints."""
    df = df.copy()
    for c in BINARY:
        if not pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c]):
            df[c] = (df[c].astype(str).str.lower() == "yes").astype(int)
        else:
            df[c] = df[c].astype(int)
    for c in NUMERIC + PERIOD_GRADES + ["G3"]:
        if c in df:
            df[c] = pd.to_numeric(df[c])
    return df


def _preprocessor(feature_set):
    cols = FEATURE_SETS[feature_set]
    cat = [c for c in cols if c in CATEGORICAL]
    rest = [c for c in cols if c not in CATEGORICAL]
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
        ("num", "passthrough", rest),
    ], verbose_feature_names_out=False)


def _candidates(task):
    if task == "g3":
        return {
            "DecisionTree": (DecisionTreeRegressor(random_state=RANDOM_STATE),
                             {"model__max_depth": [3, 5, 8, None],
                              "model__min_samples_leaf": [1, 5, 10]}),
            "RandomForest": (RandomForestRegressor(random_state=RANDOM_STATE, n_jobs=-1),
                             {"model__n_estimators": [200, 400],
                              "model__max_depth": [None, 10],
                              "model__min_samples_leaf": [1, 3]}),
        }
    return {
        "DecisionTree": (DecisionTreeClassifier(random_state=RANDOM_STATE, class_weight="balanced"),
                         {"model__max_depth": [3, 5, 8, None],
                          "model__min_samples_leaf": [1, 5, 10]}),
        "RandomForest": (RandomForestClassifier(random_state=RANDOM_STATE, n_jobs=-1,
                                                class_weight="balanced"),
                         {"model__n_estimators": [200, 400],
                          "model__max_depth": [None, 10],
                          "model__min_samples_leaf": [1, 3]}),
    }


def _targets(df):
    return {
        "pass": (df["G3"] >= 10).astype(int).values,
        "grade": to_grade(df["G3"]),
        "g3": df["G3"].values.astype(float),
    }


def _evaluate(task, model, X_test, y_test):
    pred = model.predict(X_test)
    if task == "g3":
        return {"rmse": float(np.sqrt(mean_squared_error(y_test, pred))),
                "mae": float(mean_absolute_error(y_test, pred)),
                "r2": float(r2_score(y_test, pred))}
    m = {"accuracy": float(accuracy_score(y_test, pred))}
    if task == "pass":
        proba = model.predict_proba(X_test)[:, 1]
        m.update(precision=float(precision_score(y_test, pred)),
                 recall=float(recall_score(y_test, pred)),
                 f1=float(f1_score(y_test, pred)),
                 roc_auc=float(roc_auc_score(y_test, proba)),
                 confusion_matrix=confusion_matrix(y_test, pred, labels=[0, 1]).tolist(),
                 labels=["Fail", "Pass"])
    else:
        m.update(f1_macro=float(f1_score(y_test, pred, average="macro")),
                 confusion_matrix=confusion_matrix(y_test, pred, labels=GRADE_LABELS).tolist(),
                 labels=GRADE_LABELS)
    return m


def train_all(df, model_dir, source="csv", log=print):
    """Train DT + RF for every (feature_set, task); persist best models and metrics."""
    df = prepare(df)
    os.makedirs(model_dir, exist_ok=True)
    targets = _targets(df)
    strat = targets["grade"]   # stratify every split on grade band for comparability
    idx_train, idx_test = train_test_split(np.arange(len(df)), test_size=0.2,
                                           random_state=RANDOM_STATE, stratify=strat)
    report = {"trained_at": datetime.now().isoformat(timespec="seconds"), "source": source,
              "n_samples": int(len(df)), "n_train": int(len(idx_train)),
              "n_test": int(len(idx_test)), "results": {}, "best": {},
              "feature_importance": {}}

    for fs, cols in FEATURE_SETS.items():
        X = df[cols]
        for task, y in targets.items():
            key = f"{fs}_{task}"
            report["results"][key] = {}
            score_name = "neg_root_mean_squared_error" if task == "g3" else (
                "f1" if task == "pass" else "f1_macro")
            cv = (KFold(5, shuffle=True, random_state=RANDOM_STATE) if task == "g3"
                  else StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE))
            best_name, best_cv, best_model = None, -np.inf, None
            for name, (est, grid) in _candidates(task).items():
                pipe = Pipeline([("prep", _preprocessor(fs)), ("model", est)])
                gs = GridSearchCV(pipe, grid, scoring=score_name, cv=cv, n_jobs=-1)
                gs.fit(X.iloc[idx_train], y[idx_train])
                metrics = _evaluate(task, gs.best_estimator_, X.iloc[idx_test], y[idx_test])
                metrics["cv_score"] = float(gs.best_score_)
                metrics["cv_metric"] = score_name
                metrics["params"] = {k.replace("model__", ""): v for k, v in gs.best_params_.items()}
                report["results"][key][name] = metrics
                log(f"  {key:12s} {name:13s} cv={gs.best_score_:.3f} "
                    + " ".join(f"{k}={v:.3f}" for k, v in metrics.items()
                               if isinstance(v, float) and k != "cv_score"))
                if gs.best_score_ > best_cv:
                    best_name, best_cv, best_model = name, gs.best_score_, gs.best_estimator_
            # refit chosen model on all data for deployment
            best_model.fit(X, y)
            joblib.dump(best_model, os.path.join(model_dir, f"{key}.joblib"), compress=3)
            report["best"][key] = best_name

            if task == "pass":
                # importance of the Random Forest model, aggregated back to original columns
                rf = Pipeline([("prep", _preprocessor(fs)),
                               ("model", RandomForestClassifier(
                                   n_estimators=400, random_state=RANDOM_STATE, n_jobs=-1,
                                   class_weight="balanced"))]).fit(X, y)
                names = rf.named_steps["prep"].get_feature_names_out()
                imp = {}
                for n, v in zip(names, rf.named_steps["model"].feature_importances_):
                    base = next((c for c in CATEGORICAL if n.startswith(c + "_")), n)
                    imp[base] = imp.get(base, 0) + float(v)
                report["feature_importance"][fs] = dict(
                    sorted(imp.items(), key=lambda kv: -kv[1]))

    with open(os.path.join(model_dir, "metrics.json"), "w") as f:
        json.dump(report, f, indent=2)
    return report
