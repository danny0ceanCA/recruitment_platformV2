import os
import tempfile
import pytest

# skip all tests here if any of these aren’t installed
pytest.importorskip("flask")
pytest.importorskip("flask_login")
pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("redis")
pytest.importorskip("openai")
# dotenv is now optional in your app, so you don’t strictly need to skip on it

from career_platform.app import app, db, Staff, summarize_student
from career_platform.models import Student, Job, Match

@pytest.fixture
def client(tmp_path):
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{tmp_path/'test.db'}"
    with app.app_context():
        db.drop_all()
        db.create_all()
    with app.test_client() as client:
        yield client

def test_register_and_login(client):
    # Register new user
    resp = client.post('/register', data={
        'username': 'user1',
        'password': 'pass',
        'name': 'User One',
        'school': 'Test School'
    }, follow_redirects=True)
    assert b'Login' in resp.data
    with app.app_context():
        assert Staff.query.filter_by(username='user1').first() is not None

    # Login with the registered user
    resp = client.post('/login', data={
        'username': 'user1',
        'password': 'pass'
    }, follow_redirects=True)
    assert b'Logged in as user1' in resp.data

def test_summarization_without_openai(monkeypatch):
    experience = 'A' * 100
    monkeypatch.setattr('career_platform.app.openai.api_key', None, raising=False)
    summary = summarize_student('Alice', 'NY', experience)
    assert summary == f"Alice, NY: {experience[:50]}..."


def test_created_at_defaults(client):
    with app.app_context():
        s = Student(name='Alice')
        db.session.add(s)
        j = Job(title='Job1', description='d')
        db.session.add(j)
        db.session.commit()

        m = Match(student_id=s.id, job_id=j.id)
        db.session.add(m)
        db.session.commit()

        assert s.created_at is not None
        assert m.created_at is not None

def test_school_and_match_fields(client):
    client.post('/register', data={
        'username': 'admin',
        'password': 'pass',
        'name': 'Admin',
        'school': 'SchoolX',
        'is_admin': 'on'
    }, follow_redirects=True)
    client.post('/login', data={
        'username': 'admin',
        'password': 'pass'
    }, follow_redirects=True)

    client.post('/jobs/new', data={
        'title': 'Job1',
        'description': 'desc'
    }, follow_redirects=True)

    import io
    student_resp = client.post('/students/new', data={
        'name': 'Bob',
        'location': 'NY',
        'experience': 'Python',
        'resume': (io.BytesIO(b'data'), 'resume.txt')
    }, content_type='multipart/form-data', follow_redirects=True)

    with app.app_context():
        student = Student.query.filter_by(name='Bob').first()
        job = Job.query.filter_by(title='Job1').first()
        assert student.school == 'SchoolX'

    client.post('/matches/new', data={
        'student_id': student.id,
        'job_id': job.id
    }, follow_redirects=True)

    with app.app_context():
        match = Match.query.filter_by(student_id=student.id, job_id=job.id).first()
        assert isinstance(match.score, float)
        assert match.finalized is False
        assert match.archived is False

def test_forgot_password_resets_password(client):
    # create a user
    client.post('/register', data={
        'username': 'reset',
        'password': 'old',
        'name': 'Reset User',
        'school': 'Test'
    })

    with app.app_context():
        user = Staff.query.filter_by(username='reset').first()
        old_hash = user.password_hash

    client.post('/forgot-password', data={
        'username': 'reset',
        'password': 'newpass'
    }, follow_redirects=True)

    with app.app_context():
        user = Staff.query.filter_by(username='reset').first()
        assert user.password_hash != old_hash
        assert user.check_password('newpass')


def test_update_password_logged_in(client):
    client.post('/register', data={
        'username': 'update',
        'password': 'old',
        'name': 'Update User',
        'school': 'Test'
    })

    client.post('/login', data={'username': 'update', 'password': 'old'})

    with app.app_context():
        user = Staff.query.filter_by(username='update').first()
        old_hash = user.password_hash

    client.post('/update-password', data={'password': 'newpass'}, follow_redirects=True)

    with app.app_context():
        user = Staff.query.filter_by(username='update').first()
        assert user.password_hash != old_hash
        assert user.check_password('newpass')

