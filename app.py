import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, IntegerField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, NumberRange, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-this-secret")
db_url = os.getenv("DATABASE_URL", "sqlite:///exam_portal.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["WTF_CSRF_TIME_LIMIT"] = 3600
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    allow_multiple_attempts = db.Column(db.Boolean, default=False, nullable=False)
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)
    teacher = db.relationship("User", backref="created_exams")

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(500), nullable=False)
    option_b = db.Column(db.String(500), nullable=False)
    option_c = db.Column(db.String(500), nullable=False)
    option_d = db.Column(db.String(500), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)
    marks = db.Column(db.Integer, nullable=False, default=1)
    exam = db.relationship("Exam", backref=db.backref("questions", cascade="all, delete-orphan"))

class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    submitted_at = db.Column(db.DateTime)
    score = db.Column(db.Integer)
    total_marks = db.Column(db.Integer)
    status = db.Column(db.String(20), default="in_progress", nullable=False)
    exam = db.relationship("Exam")
    student = db.relationship("User")
    answers = db.relationship("Answer", backref="attempt", cascade="all, delete-orphan")

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempt.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    selected_option = db.Column(db.String(1))
    question = db.relationship("Question")

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign in")

class UserForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=180)])
    password = PasswordField("Temporary password", validators=[DataRequired(), Length(min=8)])
    role = SelectField("Role", choices=[("teacher", "Teacher"), ("student", "Student")], validators=[DataRequired()])
    submit = SubmitField("Create account")

class ExamForm(FlaskForm):
    title = StringField("Exam title", validators=[DataRequired(), Length(max=180)])
    description = TextAreaField("Description")
    duration_minutes = IntegerField("Duration (minutes)", validators=[DataRequired(), NumberRange(min=1, max=600)])
    submit = SubmitField("Save exam")

class QuestionForm(FlaskForm):
    text = TextAreaField("Question", validators=[DataRequired()])
    option_a = StringField("Option A", validators=[DataRequired(), Length(max=500)])
    option_b = StringField("Option B", validators=[DataRequired(), Length(max=500)])
    option_c = StringField("Option C", validators=[DataRequired(), Length(max=500)])
    option_d = StringField("Option D", validators=[DataRequired(), Length(max=500)])
    correct_option = SelectField("Correct option", choices=[("A","A"),("B","B"),("C","C"),("D","D")])
    marks = IntegerField("Marks", validators=[DataRequired(), NumberRange(min=1, max=100)])
    submit = SubmitField("Add question")

class ForgotForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Send reset link")

class ResetForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=8)])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Reset password")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

def token_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="password-reset")

def send_reset_email(user, token):
    import smtplib
    from email.message import EmailMessage
    host = os.getenv("MAIL_SERVER")
    username = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")
    sender = os.getenv("MAIL_DEFAULT_SENDER", username)
    if not all([host, username, password, sender]):
        raise RuntimeError("Email settings are not configured.")
    link = url_for("reset_password", token=token, _external=True)
    msg = EmailMessage()
    msg["Subject"] = "Exam Portal - Password reset"
    msg["From"] = sender
    msg["To"] = user.email
    msg.set_content(f"Hello {user.name},\n\nReset your password using this link (valid for 30 minutes):\n{link}\n\nIf you did not request this, ignore this email.")
    with smtplib.SMTP(host, int(os.getenv("MAIL_PORT", "587"))) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(msg)

def finish_attempt(attempt):
    if attempt.status != "in_progress":
        return
    questions = Question.query.filter_by(exam_id=attempt.exam_id).all()
    answers = {a.question_id: a.selected_option for a in attempt.answers}
    score = sum(q.marks for q in questions if answers.get(q.id) == q.correct_option)
    attempt.score = score
    attempt.total_marks = sum(q.marks for q in questions)
    attempt.status = "submitted"
    attempt.submitted_at = now_utc()
    db.session.commit()

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for({"admin":"admin_dashboard","teacher":"teacher_dashboard","student":"student_dashboard"}[current_user.role]))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.email) == form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for({"admin":"admin_dashboard","teacher":"teacher_dashboard","student":"student_dashboard"}[user.role]))
        flash("Invalid email or password.", "error")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))

@app.route("/forgot-password", methods=["GET","POST"])
def forgot_password():
    form = ForgotForm()
    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.email) == form.email.data.lower()).first()
        # Keep response generic to avoid account enumeration.
        if user:
            token = token_serializer().dumps(user.email)
            try:
                send_reset_email(user, token)
            except Exception:
                app.logger.exception("Password reset email failed")
                flash("Reset email could not be sent. Check the server email configuration.", "error")
                return render_template("forgot.html", form=form)
        flash("If that email is registered, a password reset link has been sent.", "success")
        return redirect(url_for("login"))
    return render_template("forgot.html", form=form)

@app.route("/reset-password/<token>", methods=["GET","POST"])
def reset_password(token):
    try:
        email = token_serializer().loads(token, max_age=1800)
    except SignatureExpired:
        flash("This reset link has expired. Request a new one.", "error")
        return redirect(url_for("forgot_password"))
    except BadSignature:
        abort(400)
    user = User.query.filter_by(email=email).first_or_404()
    form = ResetForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Password updated. Please sign in.", "success")
        return redirect(url_for("login"))
    return render_template("reset.html", form=form)

@app.route("/admin")
@roles_required("admin")
def admin_dashboard():
    return render_template("admin.html", users=User.query.order_by(User.created_at.desc()).all(),
                           exams=Exam.query.order_by(Exam.created_at.desc()).all())

@app.route("/admin/users", methods=["GET","POST"])
@roles_required("admin")
def admin_users():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter(func.lower(User.email) == form.email.data.lower()).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(name=form.name.data.strip(), email=form.email.data.lower(), role=form.role.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f"{user.role.title()} account created.", "success")
            return redirect(url_for("admin_users"))
    return render_template("users.html", form=form, users=User.query.order_by(User.created_at.desc()).all())

@app.route("/teacher")
@roles_required("teacher")
def teacher_dashboard():
    exams = Exam.query.filter_by(teacher_id=current_user.id).order_by(Exam.created_at.desc()).all()
    return render_template("teacher.html", exams=exams)

@app.route("/teacher/exams/new", methods=["GET","POST"])
@roles_required("teacher")
def create_exam():
    form = ExamForm()
    if form.validate_on_submit():
        exam = Exam(title=form.title.data, description=form.description.data,
                    duration_minutes=form.duration_minutes.data, teacher_id=current_user.id)
        db.session.add(exam)
        db.session.commit()
        flash("Exam created. Add questions before publishing.", "success")
        return redirect(url_for("manage_questions", exam_id=exam.id))
    return render_template("exam_form.html", form=form)

def teacher_exam_or_404(exam_id):
    exam = db.session.get(Exam, exam_id)
    if not exam or exam.teacher_id != current_user.id:
        abort(404)
    return exam

@app.route("/teacher/exams/<int:exam_id>/questions", methods=["GET","POST"])
@roles_required("teacher")
def manage_questions(exam_id):
    exam = teacher_exam_or_404(exam_id)
    form = QuestionForm()
    if form.validate_on_submit():
        q = Question(exam_id=exam.id, text=form.text.data, option_a=form.option_a.data,
                     option_b=form.option_b.data, option_c=form.option_c.data, option_d=form.option_d.data,
                     correct_option=form.correct_option.data, marks=form.marks.data)
        db.session.add(q)
        db.session.commit()
        flash("Question added.", "success")
        return redirect(url_for("manage_questions", exam_id=exam.id))
    return render_template("questions.html", exam=exam, form=form)

@app.post("/teacher/exams/<int:exam_id>/publish")
@roles_required("teacher")
def publish_exam(exam_id):
    exam = teacher_exam_or_404(exam_id)
    if not exam.questions:
        flash("Add at least one question before publishing.", "error")
    else:
        exam.is_published = not exam.is_published
        db.session.commit()
        flash("Exam publication status updated.", "success")
    return redirect(url_for("manage_questions", exam_id=exam.id))

@app.post("/teacher/exams/<int:exam_id>/attempts")
@roles_required("teacher")
def toggle_attempts(exam_id):
    exam = teacher_exam_or_404(exam_id)
    exam.allow_multiple_attempts = not exam.allow_multiple_attempts
    db.session.commit()
    flash("Multiple-attempt setting updated.", "success")
    return redirect(url_for("teacher_dashboard"))

@app.route("/student")
@roles_required("student")
def student_dashboard():
    exams = Exam.query.filter_by(is_published=True).order_by(Exam.created_at.desc()).all()
    attempts = Attempt.query.filter_by(student_id=current_user.id).order_by(Attempt.started_at.desc()).all()
    return render_template("student.html", exams=exams, attempts=attempts)

@app.post("/exam/<int:exam_id>/start")
@roles_required("student")
def start_exam(exam_id):
    exam = db.session.get(Exam, exam_id)
    if not exam or not exam.is_published or not exam.questions:
        abort(404)
    active = Attempt.query.filter_by(student_id=current_user.id, exam_id=exam.id, status="in_progress").first()
    if active:
        return redirect(url_for("take_attempt", attempt_id=active.id))
    previous = Attempt.query.filter_by(student_id=current_user.id, exam_id=exam.id, status="submitted").count()
    if previous and not exam.allow_multiple_attempts:
        flash("You have already attempted this exam.", "error")
        return redirect(url_for("student_dashboard"))
    attempt = Attempt(exam_id=exam.id, student_id=current_user.id)
    db.session.add(attempt)
    db.session.commit()
    return redirect(url_for("take_attempt", attempt_id=attempt.id))

@app.route("/attempt/<int:attempt_id>", methods=["GET","POST"])
@roles_required("student")
def take_attempt(attempt_id):
    attempt = db.session.get(Attempt, attempt_id)
    if not attempt or attempt.student_id != current_user.id:
        abort(404)
    if attempt.status == "submitted":
        return redirect(url_for("student_dashboard"))
    deadline = attempt.started_at + timedelta(minutes=attempt.exam.duration_minutes)
    if now_utc() >= deadline:
        finish_attempt(attempt)
        flash("Time is up. Your exam was submitted automatically.", "success")
        return redirect(url_for("student_dashboard"))
    questions = Question.query.filter_by(exam_id=attempt.exam_id).all()
    if request.method == "POST":
        for q in questions:
            selected = request.form.get(f"q_{q.id}")
            if selected in ("A","B","C","D"):
                answer = Answer.query.filter_by(attempt_id=attempt.id, question_id=q.id).first()
                if not answer:
                    answer = Answer(attempt_id=attempt.id, question_id=q.id)
                    db.session.add(answer)
                answer.selected_option = selected
        db.session.commit()
        if request.form.get("action") == "submit":
            finish_attempt(attempt)
            flash("Exam submitted successfully.", "success")
            return redirect(url_for("student_dashboard"))
        flash("Answers saved.", "success")
        return redirect(url_for("take_attempt", attempt_id=attempt.id))
    saved = {a.question_id:a.selected_option for a in attempt.answers}
    remaining = max(0, int((deadline - now_utc()).total_seconds()))
    return render_template("take_exam.html", attempt=attempt, questions=questions, saved=saved, remaining=remaining)

@app.route("/result/<int:attempt_id>")
@roles_required("student","admin","teacher")
def result(attempt_id):
    attempt = db.session.get(Attempt, attempt_id)
    if not attempt:
        abort(404)
    if current_user.role == "student" and attempt.student_id != current_user.id:
        abort(404)
    if current_user.role == "teacher" and attempt.exam.teacher_id != current_user.id:
        abort(404)
    if attempt.status == "in_progress":
        abort(400)
    return render_template("result.html", attempt=attempt)

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The requested page was not found."), 404

with app.app_context():
    db.create_all()
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if admin_email and admin_password and not User.query.filter_by(role="admin").first():
        admin = User(name="Administrator", email=admin_email.lower(), role="admin")
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
