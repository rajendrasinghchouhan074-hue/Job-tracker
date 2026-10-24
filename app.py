import os
import csv
import io
from datetime import date
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, Response)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (UserMixin, LoginManager, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobs.db"

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

STATUSES = ["Applied", "Interview", "Offer", "Rejected"]
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(30), default="Applied")
    date_applied = db.Column(db.Date, default=date.today)
    notes = db.Column(db.Text, default="")
    job_link = db.Column(db.String(300), default="")
    follow_up = db.Column(db.Date, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


def clean_link(link):
    link = link.strip()
    if link and not link.lower().startswith(("http://", "https://")):
        link = "https://" + link
    return link


def parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def csv_safe(value):
    value = "" if value is None else str(value)
    if value and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    selected = request.args.get("status", "")

    base = Application.query.filter_by(user_id=current_user.id)
    all_jobs = base.all()
    counts = {s: 0 for s in STATUSES}
    for j in all_jobs:
        if j.status in counts:
            counts[j.status] += 1

    today = date.today()
    due_count = sum(1 for j in all_jobs
                    if j.follow_up and j.follow_up <= today
                    and j.status in ("Applied", "Interview"))

    query = base
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Application.company.ilike(like),
                                    Application.role.ilike(like)))
    if selected in STATUSES:
        query = query.filter(Application.status == selected)
    jobs = query.order_by(Application.date_applied.desc()).all()

    return render_template("index.html", jobs=jobs, counts=counts,
                           total=len(all_jobs), statuses=STATUSES,
                           q=q, selected=selected, today=today,
                           due_count=due_count)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        job = Application(
            company=request.form["company"].strip(),
            role=request.form["role"].strip(),
            status=request.form["status"],
            notes=request.form.get("notes", "").strip(),
            job_link=clean_link(request.form.get("job_link", "")),
            follow_up=parse_date(request.form.get("follow_up")),
            user_id=current_user.id,
        )
        db.session.add(job)
        db.session.commit()
        return redirect(url_for("index"))
    return render_template("form.html", job=None, statuses=STATUSES)


@app.route("/edit/<int:job_id>", methods=["GET", "POST"])
@login_required
def edit(job_id):
    job = Application.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    if request.method == "POST":
        job.company = request.form["company"].strip()
        job.role = request.form["role"].strip()
        job.status = request.form["status"]
        job.notes = request.form.get("notes", "").strip()
        job.job_link = clean_link(request.form.get("job_link", ""))
        job.follow_up = parse_date(request.form.get("follow_up"))
        db.session.commit()
        return redirect(url_for("index"))
    return render_template("form.html", job=job, statuses=STATUSES)


@app.route("/delete/<int:job_id>", methods=["POST"])
@login_required
def delete(job_id):
    job = Application.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    db.session.delete(job)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/export")
@login_required
def export():
    jobs = (Application.query.filter_by(user_id=current_user.id)
            .order_by(Application.date_applied.desc()).all())
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Company", "Role", "Status", "Date applied",
                     "Follow-up", "Job link", "Notes"])
    for j in jobs:
        writer.writerow([csv_safe(j.company), csv_safe(j.role),
                         csv_safe(j.status), csv_safe(j.date_applied),
                         csv_safe(j.follow_up), csv_safe(j.job_link),
                         csv_safe(j.notes)])
    data = "\ufeff" + buf.getvalue()
    return Response(data, mimetype="text/csv", headers={
        "Content-Disposition": "attachment; filename=job_applications.csv"})

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form["old_password"]
        new = request.form["new_password"]
        if not current_user.check_password(old):
            flash("Current password is incorrect")
        elif len(new) < 6:
            flash("New password must be at least 6 characters")
        else:
            current_user.set_password(new)
            db.session.commit()
            flash("Password changed successfully")
            return redirect(url_for("index"))
    return render_template("change_password.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if User.query.filter_by(username=username).first():
            flash("This username is already taken")
            return redirect(url_for("register"))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"].strip()).first()
        if user and user.check_password(request.form["password"]):
            login_user(user)
            return redirect(url_for("index"))
        flash("Incorrect username or password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/admin")
@login_required
def admin():
    if current_user.username != ADMIN_USERNAME:
        return "Access denied", 403
    rows = []
    for u in User.query.all():
        jobs = Application.query.filter_by(user_id=u.id).all()
        counts = {s: 0 for s in STATUSES}
        for j in jobs:
            if j.status in counts:
                counts[j.status] += 1
        last = max((j.date_applied for j in jobs), default=None)
        rows.append({"username": u.username, "total": len(jobs),
                     "counts": counts, "last": last})
    return render_template("admin.html", rows=rows, statuses=STATUSES)


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)