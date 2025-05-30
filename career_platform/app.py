import os
import json
import math
from flask import Flask, request, redirect, url_for, render_template_string, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename
import openai
import redis

from .models import db, Staff, Student, Job, Match

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
# Allow SECRET_KEY configuration via the environment for better security
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///career.db'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

openai.api_key = os.environ.get('OPENAI_API_KEY')
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Staff.query.get(int(user_id))

@app.before_first_request
def create_tables():
    db.create_all()

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        school = request.form['school']
        is_admin = 'is_admin' in request.form
        if Staff.query.filter_by(username=username).first():
            flash('User exists')
        else:
            user = Staff(username=username, name=name, school=school, is_admin=is_admin)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Registered')
            return redirect(url_for('login'))
    return render_template_string('''
        <form method="post">
            Username: <input name="username"><br>
            Password: <input name="password" type="password"><br>
            Name: <input name="name"><br>
            School: <input name="school"><br>
            Admin: <input type="checkbox" name="is_admin"><br>
            <input type="submit" value="Register">
        </form>
    ''')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Staff.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template_string('''
        <form method="post">
            Username: <input name="username"><br>
            Password: <input name="password" type="password"><br>
            <input type="submit" value="Login">
        </form>
    ''')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    students = Student.query.all()
    jobs = Job.query.all()
    matches = Match.query.all()
    return render_template_string('''
        <p>Logged in as {{current_user.username}}</p>
        <p><a href="{{url_for('add_student')}}">Add Student</a> |
        <a href="{{url_for('add_job')}}">Add Job</a> |
        <a href="{{url_for('create_match')}}">Create Match</a> |
        <a href="{{url_for('metrics')}}">Metrics</a> |
        <a href="{{url_for('logout')}}">Logout</a></p>
        <h3>Students</h3>
        <ul>{% for s in students %}<li>{{s.name}} - {{s.summary}}</li>{% endfor %}</ul>
        <h3>Jobs</h3>
        <ul>{% for j in jobs %}<li>{{j.title}}</li>{% endfor %}</ul>
        <h3>Matches</h3>
        <ul>{% for m in matches %}<li>{{m.student.name}} -> {{m.job.title}}</li>{% endfor %}</ul>
    ''', students=students, jobs=jobs, matches=matches)

# Add student with resume upload
@app.route('/students/new', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        experience = request.form['experience']
        file = request.files['resume']
        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)
        summary = summarize_student(name, location, experience)
        student = Student(
            name=name,
            location=location,
            experience=experience,
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
    return render_template_string('''
        <form method="post" enctype="multipart/form-data">
            Name: <input name="name"><br>
            Location: <input name="location"><br>
            Experience: <textarea name="experience"></textarea><br>
            Resume: <input type="file" name="resume"><br>
            <input type="submit" value="Add">
        </form>
    ''')

# OpenAI summarization

def summarize_student(name, location, experience):
    if not openai.api_key:
        return f"{name}, {location}: {experience[:50]}..."
    prompt = f"Summarize student {name} from {location} with experience: {experience}"
    try:
        resp = openai.Completion.create(model='text-davinci-003', prompt=prompt, max_tokens=50)
        return resp.choices[0].text.strip()
    except Exception:
        return experience[:50]

def create_embedding(text):
    if not openai.api_key:
        return None
    try:
        resp = openai.Embedding.create(model='text-embedding-ada-002', input=text)
        return resp['data'][0]['embedding']
    except Exception:
        return None

def store_embedding(student_id, embedding):
    if embedding is not None:
        redis_client.set(f'embedding:{student_id}', json.dumps(embedding))

def get_embedding(student_id):
    data = redis_client.get(f'embedding:{student_id}')
    if data:
        return json.loads(data)
    return None

def compute_similarity(vec1, vec2):
    if not vec1 or not vec2:
        return 0.0
    dot = sum(a*b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a*a for a in vec1))
    norm2 = math.sqrt(sum(b*b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

# Admin-only job creation
@app.route('/jobs/new', methods=['GET', 'POST'])
@login_required
def add_job():
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        job = Job(title=title, description=description)
        db.session.add(job)
        db.session.commit()
        flash('Job added')
        return redirect(url_for('index'))
    return render_template_string('''
        <form method="post">
            Title: <input name="title"><br>
            Description: <textarea name="description"></textarea><br>
            <input type="submit" value="Add Job">
        </form>
    ''')

# Match students to jobs
@app.route('/matches/new', methods=['GET', 'POST'])
@login_required
def create_match():
    if not current_user.is_admin:
        flash('Admins only')
        return redirect(url_for('index'))
    students = Student.query.all()
    jobs = Job.query.all()
    if request.method == 'POST':
        student_id = request.form['student_id']
        job_id = request.form['job_id']
        match = Match(student_id=student_id, job_id=job_id)
        db.session.add(match)
        db.session.commit()
        flash('Match created')
        return redirect(url_for('index'))
    return render_template_string('''
        <form method="post">
            Student: <select name="student_id">{% for s in students %}<option value="{{s.id}}">{{s.name}}</option>{% endfor %}</select><br>
            Job: <select name="job_id">{% for j in jobs %}<option value="{{j.id}}">{{j.title}}</option>{% endfor %}</select><br>
            <input type="submit" value="Create Match">
        </form>
    ''', students=students, jobs=jobs)

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
            Match.query.filter_by(student_id=s.id)
            .order_by(Match.created_at)
            .first()
        )
        if first_match:
            diffs.append((first_match.created_at - s.created_at).total_seconds() / 86400)

    avg_time = sum(diffs) / len(diffs) if diffs else None
    placement_rate_str = f"{placement_rate*100:.2f}%" if student_count else "N/A"
    avg_time_str = f"{avg_time:.2f}" if avg_time is not None else "N/A"

    return render_template_string('''
        <h3>Metrics for {{ school }}</h3>
        <table border="1">
            <tr><th>Student Count</th><td>{{ student_count }}</td></tr>
            <tr><th>Placement Rate</th><td>{{ placement_rate_str }}</td></tr>
            <tr><th>Avg Days to Placement</th><td>{{ avg_time_str }}</td></tr>
        </table>
        <p><a href="{{ url_for('index') }}">Back</a></p>
    ''', school=school, student_count=student_count,
           placement_rate_str=placement_rate_str, avg_time_str=avg_time_str)

if __name__ == '__main__':
    app.run(debug=True)
