import os
import tempfile
import pytest

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
