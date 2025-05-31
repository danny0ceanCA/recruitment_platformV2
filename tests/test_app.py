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

from career_platform.app import app, db, Staff, summarize_student, create_embedding
from career_platform.models import Student, Job, Match

@pytest.fixture
def client(tmp_path):
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
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
        'first_name': 'User',
        'last_name': 'One',
        'email': 'user1@example.com',
        'name': 'User One',
        'school': 'Test School'
    }, follow_redirects=True)
    assert b'Login' in resp.data
    with app.app_context():
        staff = Staff.query.filter_by(username='user1').first()
        assert staff is not None
        assert staff.first_name == 'User'
        assert staff.last_name == 'One'
        assert staff.email == 'user1@example.com'

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
        'first_name': 'Admin',
        'last_name': 'User',
        'email': 'admin@example.com',
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
        'first_name': 'Reset',
        'last_name': 'User',
        'email': 'reset@example.com',
        'name': 'Reset User',
        'school': 'Test'
    })

    with app.app_context():
        user = Staff.query.filter_by(username='reset').first()
        old_hash = user.password_hash

    resp = client.post('/forgot-password', data={'username': 'reset'})
    token = resp.get_json()['token']

    client.post(f'/reset-password/{token}', data={'password': 'newpass'}, follow_redirects=True)

    with app.app_context():
        user = Staff.query.filter_by(username='reset').first()
        assert user.password_hash != old_hash
        assert user.check_password('newpass')


def test_update_password_logged_in(client):
    client.post('/register', data={
        'username': 'update',
        'password': 'old',
        'first_name': 'Update',
        'last_name': 'User',
        'email': 'update@example.com',
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


def test_openai_summary_and_embedding(monkeypatch):
    import openai

    # provide API key
    monkeypatch.setattr(openai, 'api_key', 'test-key', raising=False)

    class FakeResp:
        def __init__(self, text=None, emb=None):
            self.choices = [type('Choice', (), {'text': text})()] if text else []
            self.data = [{'embedding': emb}] if emb else []

    def fake_completion_create(**kwargs):
        return FakeResp(text='summary')

    def fake_embedding_create(**kwargs):
        return {'data': [{'embedding': [1.0, 2.0]}]}

    monkeypatch.setattr(openai, 'Completion', type('C', (), {'create': staticmethod(fake_completion_create)}))
    monkeypatch.setattr(openai, 'Embedding', type('E', (), {'create': staticmethod(fake_embedding_create)}))

    summary = summarize_student('Foo', 'Bar', 'Baz')
    assert summary == 'summary'
    embedding = create_embedding('text')
    assert embedding == [1.0, 2.0]
=======
def test_metrics_calculations(client):
    client.post('/register', data={
        'username': 'adminm',
        'password': 'pass',
        'first_name': 'Admin',
        'last_name': 'User',
        'email': 'adminm@example.com',
        'name': 'Admin',
        'school': 'MetricsU',
        'is_admin': 'on'
    }, follow_redirects=True)

    client.post('/login', data={'username': 'adminm', 'password': 'pass'}, follow_redirects=True)

    client.post('/jobs/new', data={'title': 'Job1', 'description': 'd'}, follow_redirects=True)

    import io
    client.post('/students/new', data={
        'name': 'A',
        'location': 'NY',
        'experience': 'exp',
        'resume': (io.BytesIO(b'data'), 'r1.txt')
    }, content_type='multipart/form-data', follow_redirects=True)

    client.post('/students/new', data={
        'name': 'B',
        'location': 'NY',
        'experience': 'exp',
        'resume': (io.BytesIO(b'data'), 'r2.txt')
    }, content_type='multipart/form-data', follow_redirects=True)

    with app.app_context():
        job = Job.query.filter_by(title='Job1').first()
        s1 = Student.query.filter_by(name='A').first()
        s2 = Student.query.filter_by(name='B').first()

    client.post('/matches/new', data={'student_id': s1.id, 'job_id': job.id}, follow_redirects=True)
    resp = client.post('/matches/new', data={'student_id': s2.id, 'job_id': job.id}, follow_redirects=True)
    with app.app_context():
        m2 = Match.query.filter_by(student_id=s2.id, job_id=job.id).order_by(Match.id.desc()).first()
    client.get(f'/matches/{m2.id}/finalize', follow_redirects=True)

    resp = client.post('/matches/new', data={'student_id': s1.id, 'job_id': job.id}, follow_redirects=True)
    with app.app_context():
        m3 = Match.query.filter_by(student_id=s1.id).order_by(Match.id.desc()).first()
    client.get(f'/matches/{m3.id}/archive', follow_redirects=True)

    metrics_resp = client.get('/metrics')
    text = metrics_resp.get_data(as_text=True)
    assert 'Avg Finalized Score' in text
    assert 'Job1' in text
    assert '<td>1</td><td>1</td><td>1</td>' in text.replace('\n', '')

