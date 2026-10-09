from flask import Blueprint, render_template
from flask_login import current_user

from .common import role_required
from ..ml_service import record_to_row, recommendations
from ..models import Attendance

bp = Blueprint("student", __name__, url_prefix="/student")


@bp.route("/")
@role_required("student")
def dashboard():
    st = current_user.student
    tips = {}
    for r in st.records:
        p = r.latest_prediction
        if p:
            tips[r.id] = recommendations(record_to_row(r), p.pass_probability)
    recent = (Attendance.query.filter(Attendance.record_id.in_([r.id for r in st.records]))
              .order_by(Attendance.date.desc()).limit(10).all())
    return render_template("student/dashboard.html", st=st, tips=tips, recent=recent)
