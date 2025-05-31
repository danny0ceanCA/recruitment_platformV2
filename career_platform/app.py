# Load .env if python-dotenv is available, otherwise skip
try:
    from dotenv import load_dotenv
    load_dotenv()   # pull in keys from .env into os.environ
except ImportError:
    pass   # <-- this will pull in the keys from .env into os.environ

import os
import json
import math
from flask import Flask, request, redirect, url_for, render_template, flash, render_template_string
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import openai
import redis

from .models import db, Staff, Student, Job, Match
from .forms import (
    RegisterForm,
    LoginForm,
    ForgotPasswordForm,
    UpdatePasswordForm,
    StudentForm,
    JobForm,
    MatchForm,
)

# Helper to generate embeddings via OpenAI
def embed_text(text):
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return []
    openai.api_key = api_key
    try:
        resp = openai.Embedding.create(model='text-embedding-ada-002', input=[text])
        return resp['data'][0]['embedding']
    except Exception:
        return []

# Compute cosine similarity between two vectors
def cosine_similarity(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x*y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x*x for x in a))
    norm_b = math.sqrt(sum(x*x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

# Ensure upload directory exists
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///career.db'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure OpenAI and Redis
openai.api_key = os.environ.get('OPENAI_API_KEY')
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD
)

# Initialize database and create tables on startup
db.init_app(app)
with app.app_context():
    db.create_all()

# Setup Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Staff.query.get(int(user_id))

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        if Staff.query.filter_by(username=username).first():
            flash('User exists')
        else:
            user = Staff(
                username=username,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                name=form.name.data,
                school=form.school.data,
                is_admin=form.is_admin.data,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Registered')
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = Staff.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template('login.html', form=form)

# Forgot-password route
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        username = form.username.data
        new_password = form.password.data
        user = Staff.query.filter_by(username=username).first()
        if user:
            user.set_password(new_password)
            db.session.commit()
            flash('Password updated')
            return redirect(url_for('login'))
        else:
            flash('User not found')
    return render_template_string(
        '<form method="post">{{ form.csrf_token }}Username: {{ form.username }}<br>'
        'New Password: {{ form.password }}<br>{{ form.submit }}</form>',
        form=form,
    )

# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Update-password route
@app.route('/update-password', methods=['GET', 'POST'])
@login_required
def update_password():
    form = UpdatePasswordForm()
    if form.validate_on_submit():
        new_password = form.password.data
        current_user.set_password(new_password)
        db.session.commit()
        flash('Password updated')
        return redirect(url_for('index'))
    return render_template_string(
        '<form method="post">{{ form.csrf_token }}New Password: {{ form.password }}<br>{{ form.submit }}</form>',
        form=form,
    )

# Dashboard route
@app.route('/')
@login_required
def index():
    students = Student.query.all()
    jobs = Job.query.all()
    matches = Match.query.all()
    return render_template('dashboard.html', students=students, jobs=jobs, matches=matches)

# Admin view of matches
@app.route('/admin/matches')
@login_required
def admin_matches():
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    jobs = Job.query.all()
    job_matches = {job: Match.query.filter_by(job_id=job.id, finalized=False, archived=False).order_by(Match.score.desc()).all() for job in jobs}
    return render_template('admin_matches.html', job_matches=job_matches)

# Finalize match route
@app.route('/matches/<int:match_id>/finalize')
@login_required
def finalize_match(match_id):
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    m = Match.query.get_or_404(match_id)
    m.finalized = True
    db.session.commit()
    flash('Match finalized')
    return redirect(url_for('admin_matches'))

# Archive match route
@app.route('/matches/<int:match_id>/archive')
@login_required
def archive_match(match_id):
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    m = Match.query.get_or_404(match_id)
    m.archived = True
    db.session.commit()
    flash('Match archived')
    return redirect(url_for('admin_matches'))

# Add student route
@app.route('/students/new', methods=['GET', 'POST'])
@login_required
def add_student():
    form = StudentForm()
    if form.validate_on_submit():
        file = form.resume.data
        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)
        summary = summarize_student(form.name.data, form.location.data, form.experience.data)
        student = Student(
            name=form.name.data,
            location=form.location.data,
            experience=form.experience.data,
            resume_path=path,
            summary=summary,
            school=current_user.school,
        )
        db.session.add(student)
        db.session.commit()
        embedding = create_embedding(summary)
        store_embedding(student.id, embedding)
        flash('Student added')
        return redirect(url_for('index'))
    return render_template('add_student.html', form=form)

# Summarize student via OpenAI
def summarize_student(name, location, experience):
    if not openai.api_key:
        return f"{name}, {location}: {experience[:50]}..."
    prompt = f"Summarize student {name} from {location} with experience: {experience}"
    try:
        resp = openai.Completion.create(model='text-davinci-003', prompt=prompt, max_tokens=50)
        return resp.choices[0].text.strip()
    except Exception:
        return experience[:50]

# Create embedding via OpenAI
def create_embedding(text):
    if not openai.api_key:
        return None
    try:
        resp = openai.Embedding.create(model='text-embedding-ada-002', input=text)
        return resp['data'][0]['embedding']
    except Exception:
        return None

# Store embedding in Redis
def store_embedding(student_id, embedding):
    if embedding is not None:
        redis_client.set(f'embedding:{student_id}', json.dumps(embedding))

# Retrieve embedding from Redis
def get_embedding(student_id):
    data = redis_client.get(f'embedding:{student_id}')
    return json.loads(data) if data else None

# Admin-only job creation route
@app.route('/jobs/new', methods=['GET', 'POST'])
def add_job():
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    form = JobForm()
    if form.validate_on_submit():
        job = Job(title=form.title.data, description=form.description.data)
        db.session.add(job)
        db.session.commit()
        flash('Job added')
        return redirect(url_for('index'))
    return render_template('add_job.html', form=form)

# Create match route
@app.route('/matches/new', methods=['GET', 'POST'])
@login_required
def create_match():
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    students = Student.query.all()
    jobs = Job.query.all()
    form = MatchForm()
    form.student_id.choices = [(s.id, s.name) for s in students]
    form.job_id.choices = [(j.id, j.title) for j in jobs]
    if form.validate_on_submit():
        student = Student.query.get(form.student_id.data)
        job = Job.query.get(form.job_id.data)
        student_emb = get_embedding(student.id) or []
        job_emb = embed_text(job.description)
        score = cosine_similarity(student_emb, job_emb)
        match = Match(student_id=student.id, job_id=job.id, score=score)
        db.session.add(match)
        db.session.commit()
        flash('Match created')
        return redirect(url_for('index'))
    return render_template('create_match.html', form=form, students=students, jobs=jobs)

# Metrics route
@app.route('/metrics')
@login_required
def metrics():
    school = current_user.school
    student_count = Student.query.filter_by(school=school).count()
    placed_count = (
        db.session.query(Student.id)
        .join(Match, Student.id == Match.student_id)
        .filter(Student.school == school)
        .distinct()
        .count()
    )
    placement_rate = placed_count / student_count if student_count else 0
    students = Student.query.filter_by(school=school).all()
    diffs = []
    for s in students:
        first_match = (
            Match.query.filter_by(student_id=s.id).order_by(Match.created_at).first()
        )
        if first_match:
            diffs.append((first_match.created_at - s.created_at).total_seconds() / 86400)
    avg_time = sum(diffs) / len(diffs) if diffs else None
    placement_rate_str = f"{placement_rate*100:.2f}%" if student_count else "N/A"
    avg_time_str = f"{avg_time:.2f}" if avg_time is not None else "N/A"
    return render_template('metrics.html', school=school, student_count=student_count, placement_rate_str=placement_rate_str, avg_time_str=avg_time_str)

if __name__ == '__main__':
    app.run(debug=True)
