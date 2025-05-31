# Load .env if python-dotenv is available, otherwise skip
try:
    from dotenv import load_dotenv
    load_dotenv()   # pull in keys from .env into os.environ
except ImportError:
    pass   # <-- this will pull in the keys from .env into os.environ

import os
import json
import math
import secrets
import csv
import io
from flask import (
    Flask,
    request,
    redirect,
    url_for,
    render_template,
    flash,
    render_template_string,
    jsonify,
)

from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

try:
    import openai
    from openai.error import OpenAIError
except Exception:  # pragma: no cover - library may be missing
    openai = None

    class OpenAIError(Exception):
        pass
import redis
from sqlalchemy import func

from .models import db, Staff, Student, Job, Match
from .forms import (
    RegisterForm,
    LoginForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    UpdatePasswordForm,
    StudentForm,
    EditStudentForm,
    JobForm,
    EditJobForm,
    MatchForm,
    BulkUploadForm,
)

# Helper to generate embeddings via OpenAI
def embed_text(text):
    api_key = os.environ.get('OPENAI_API_KEY')
    if not openai or not api_key:
        return []
    openai.api_key = api_key
    try:
        resp = openai.Embedding.create(model='text-embedding-ada-002', input=[text])
        return resp['data'][0]['embedding']
    except OpenAIError:
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

# Send reset tokens via email or console for testing
def send_reset_email(recipient, token):
    """Send the reset token to the user.

    In testing mode the token is simply printed so tests can capture it."""
    message = f"Password reset token for {recipient}: {token}"
    print(message)

# Ensure upload directory exists
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///career.db'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure OpenAI and Redis
if openai:
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

# Forgot-password route - request a reset token
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        username = form.username.data
        user = Staff.query.filter_by(username=username).first()
        if user:
            token = secrets.token_urlsafe(16)
            redis_client.setex(f'reset:{token}', 3600, user.id)
            send_reset_email(user.email, token)
            if app.config.get('TESTING'):
                return jsonify({'token': token})
            flash('Reset instructions sent')
            return redirect(url_for('login'))
        else:
            flash('User not found')
    return render_template_string(
        '<form method="post">{{ form.csrf_token }}Username: {{ form.username }}<br>{{ form.submit }}</form>',
        form=form,
    )

# Reset password using token
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    form = ResetPasswordForm()
    user_id = redis_client.get(f'reset:{token}')
    if not user_id:
        flash('Invalid or expired token')
        return redirect(url_for('forgot_password'))
    if form.validate_on_submit():
        user = Staff.query.get(int(user_id))
        if user:
            user.set_password(form.password.data)
            db.session.commit()
            redis_client.delete(f'reset:{token}')
            flash('Password updated')
            return redirect(url_for('login'))
    return render_template_string(
        '<form method="post">{{ form.csrf_token }}New Password: {{ form.password }}<br>{{ form.submit }}</form>',
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

# Edit student
@app.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    student = Student.query.get_or_404(student_id)
    form = EditStudentForm(obj=student)
    if form.validate_on_submit():
        student.name = form.name.data
        student.location = form.location.data
        student.experience = form.experience.data
        if form.resume.data:
            file = form.resume.data
            filename = secure_filename(file.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(path)
            student.resume_path = path
        summary = summarize_student(form.name.data, form.location.data, form.experience.data)
        student.summary = summary
        db.session.commit()
        embedding = create_embedding(summary)
        store_embedding(student.id, embedding)
        flash('Student updated')
        return redirect(url_for('index'))
    return render_template('edit_student.html', form=form, student=student)

# Delete student
@app.route('/students/<int:student_id>/delete')
@login_required
def delete_student(student_id):
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted')
    return redirect(url_for('index'))

# Bulk upload students via CSV
@app.route('/students/bulk_upload', methods=['GET', 'POST'])
@login_required
def bulk_upload_students():
    form = BulkUploadForm()
    results = []
    if form.validate_on_submit():
        file = form.csv_file.data
        stream = io.StringIO(file.stream.read().decode('utf-8'))
        reader = csv.DictReader(stream)
        for row in reader:
            name = row.get('name') or ''
            location = row.get('location') or ''
            experience = row.get('experience') or ''
            resume_path = row.get('resume') or row.get('resume_path')
            if not resume_path:
                results.append(f"Missing resume for {name}")
                continue
            try:
                filename = secure_filename(os.path.basename(resume_path))
                dest_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(resume_path, 'rb') as src, open(dest_path, 'wb') as dst:
                    dst.write(src.read())
                summary = summarize_student(name, location, experience)
                student = Student(
                    name=name,
                    location=location,
                    experience=experience,
                    resume_path=dest_path,
                    summary=summary,
                    school=current_user.school,
                )
                db.session.add(student)
                db.session.commit()
                embedding = create_embedding(summary)
                store_embedding(student.id, embedding)
                results.append(f"Added {name}")
            except Exception as e:
                db.session.rollback()
                results.append(f"Failed {name}: {e}")
    return render_template('bulk_upload.html', form=form, results=results)

# Summarize student via OpenAI
def summarize_student(name, location, experience):
    if not openai or not openai.api_key:
        return f"{name}, {location}: {experience[:50]}..."
    prompt = f"Summarize student {name} from {location} with experience: {experience}"
    try:
        resp = openai.Completion.create(model='text-davinci-003', prompt=prompt, max_tokens=50)
        return resp.choices[0].text.strip()
    except OpenAIError:
        return experience[:50]

# Create embedding via OpenAI
def create_embedding(text):
    if not openai or not openai.api_key:
        return None
    try:
        resp = openai.Embedding.create(model='text-embedding-ada-002', input=text)
        return resp['data'][0]['embedding']
    except OpenAIError:
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

# Edit job
@app.route('/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    job = Job.query.get_or_404(job_id)
    form = EditJobForm(obj=job)
    if form.validate_on_submit():
        job.title = form.title.data
        job.description = form.description.data
        db.session.commit()
        flash('Job updated')
        return redirect(url_for('index'))
    return render_template('edit_job.html', form=form, job=job)

# Delete job
@app.route('/jobs/<int:job_id>/delete')
@login_required
def delete_job(job_id):
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    job = Job.query.get_or_404(job_id)
    db.session.delete(job)
    db.session.commit()
    flash('Job deleted')
    return redirect(url_for('index'))

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

    jobs = Job.query.all()
    job_stats = []
    for job in jobs:
        queued = Match.query.filter_by(job_id=job.id, finalized=False, archived=False).count()
        finalized_count = Match.query.filter_by(job_id=job.id, finalized=True, archived=False).count()
        archived = Match.query.filter_by(job_id=job.id, archived=True).count()
        job_stats.append({
            'job': job,
            'queued': queued,
            'finalized': finalized_count,
            'archived': archived,
        })

    avg_score = db.session.query(func.avg(Match.score)).filter(Match.finalized == True).scalar()
    avg_score_str = f"{avg_score:.2f}" if avg_score is not None else "N/A"

    return render_template(
        'metrics.html',
        school=school,
        student_count=student_count,
        placement_rate_str=placement_rate_str,
        avg_time_str=avg_time_str,
        job_stats=job_stats,
        avg_score_str=avg_score_str,
    )

if __name__ == '__main__':
    app.run(debug=True)
