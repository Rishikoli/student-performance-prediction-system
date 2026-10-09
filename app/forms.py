"""Field specs (from the UCI dataset description) used to render and parse forms."""

SCALE_1_5 = [(i, str(i)) for i in range(1, 6)]
EDU = [(0, "0 - none"), (1, "1 - primary (4th grade)"), (2, "2 - 5th to 9th grade"),
       (3, "3 - secondary"), (4, "4 - higher education")]
JOBS = [(j, j.replace("_", " ").title()) for j in
        ("teacher", "health", "services", "at_home", "other")]
YESNO = [(1, "Yes"), (0, "No")]

STUDENT_FIELDS = [
    ("name", "Full name", "text", None),
    ("school", "School", "select", [("GP", "Gabriel Pereira"), ("MS", "Mousinho da Silveira")]),
    ("sex", "Sex", "select", [("F", "Female"), ("M", "Male")]),
    ("age", "Age", "number", (15, 22)),
    ("address", "Address", "select", [("U", "Urban"), ("R", "Rural")]),
    ("famsize", "Family size", "select", [("LE3", "≤ 3"), ("GT3", "> 3")]),
    ("Pstatus", "Parents' status", "select", [("T", "Living together"), ("A", "Apart")]),
    ("Medu", "Mother's education", "select", EDU),
    ("Fedu", "Father's education", "select", EDU),
    ("Mjob", "Mother's job", "select", JOBS),
    ("Fjob", "Father's job", "select", JOBS),
    ("reason", "Reason for choosing school", "select",
     [("home", "Close to home"), ("reputation", "Reputation"), ("course", "Course preference"),
      ("other", "Other")]),
    ("nursery", "Attended nursery school", "bool", YESNO),
    ("internet", "Internet at home", "bool", YESNO),
]

RECORD_FIELDS = [
    ("guardian", "Guardian", "select",
     [("mother", "Mother"), ("father", "Father"), ("other", "Other")]),
    ("traveltime", "Travel time", "select",
     [(1, "< 15 min"), (2, "15-30 min"), (3, "30-60 min"), (4, "> 1 hour")]),
    ("studytime", "Weekly study time", "select",
     [(1, "< 2 hours"), (2, "2-5 hours"), (3, "5-10 hours"), (4, "> 10 hours")]),
    ("failures", "Past class failures", "select", [(0, "0"), (1, "1"), (2, "2"), (3, "3+")]),
    ("schoolsup", "Extra educational support", "bool", YESNO),
    ("famsup", "Family educational support", "bool", YESNO),
    ("paid", "Extra paid classes", "bool", YESNO),
    ("activities", "Extra-curricular activities", "bool", YESNO),
    ("higher", "Wants higher education", "bool", YESNO),
    ("romantic", "In a romantic relationship", "bool", YESNO),
    ("famrel", "Family relationship quality (1-5)", "select", SCALE_1_5),
    ("freetime", "Free time after school (1-5)", "select", SCALE_1_5),
    ("goout", "Going out with friends (1-5)", "select", SCALE_1_5),
    ("Dalc", "Workday alcohol consumption (1-5)", "select", SCALE_1_5),
    ("Walc", "Weekend alcohol consumption (1-5)", "select", SCALE_1_5),
    ("health", "Health status (1-5)", "select", SCALE_1_5),
]

MARK_FIELDS = [
    ("absences", "Absences", "number", (0, 93)),
    ("G1", "Period 1 grade (0-20)", "number", (0, 20)),
    ("G2", "Period 2 grade (0-20)", "number", (0, 20)),
    ("G3", "Final grade (0-20)", "number", (0, 20)),
    ("assignment_score", "Assignment score (0-100)", "number", (0, 100)),
    ("practical_score", "Practical score (0-100)", "number", (0, 100)),
]

OPTIONAL = {"G1", "G2", "G3", "assignment_score", "practical_score"}
FLOAT_FIELDS = {"assignment_score", "practical_score"}


def parse(form, fields):
    """Parse request.form against field specs. Returns (data, errors)."""
    data, errors = {}, []
    for name, label, kind, opts in fields:
        raw = (form.get(name) or "").strip()
        if raw == "":
            if name in OPTIONAL:
                data[name] = None
                continue
            errors.append(f"{label} is required.")
            continue
        if kind == "bool":
            data[name] = raw in ("1", "true", "yes", "on")
        elif kind == "number":
            try:
                v = float(raw) if name in FLOAT_FIELDS else int(raw)
            except ValueError:
                errors.append(f"{label} must be a number.")
                continue
            lo, hi = opts
            if not lo <= v <= hi:
                errors.append(f"{label} must be between {lo} and {hi}.")
            data[name] = v
        elif kind == "select":
            valid = {str(v): v for v, _ in opts}
            if raw not in valid:
                errors.append(f"Invalid value for {label}.")
                continue
            data[name] = valid[raw]
        else:
            data[name] = raw[:100]
    return data, errors
