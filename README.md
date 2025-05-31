# Career Platform

This project provides a small internal tool for staff to manage students, resumes, and internal job postings. It also integrates with OpenAI to summarize student profiles and supports matching students to jobs.

## Setup

1. Create a Python virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Set your OpenAI API key, Flask `SECRET_KEY`, and optional Redis connection in the environment. A valid `OPENAI_API_KEY` is required for the application to generate summaries and embeddings:

```bash
export OPENAI_API_KEY=your-key
# Flask session secret
export SECRET_KEY=your-secret
# Redis configuration (defaults shown)
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0
```

3. Run the application:

```bash
python -m career_platform.app
```

The application creates `career.db` and an `uploads/` folder in the project directory.
If you update the models, delete the existing `career.db` to recreate the schema.

## Usage

- Register a staff account at `/register`. Check "Admin" for accounts that can post jobs and create matches.
- Log in via `/login`.
- Add students with resume uploads at `/students/new`.
- Admins can add jobs at `/jobs/new` and create matches at `/matches/new`.
- Summaries of students are generated automatically using OpenAI when adding a student.
- Student summaries are embedded using the OpenAI embeddings API to enable similarity scoring.
- Admins can review queued matches at `/admin/matches`, ordered by similarity score, and finalize or archive them.


Student resumes and summaries are stored in the database and `uploads/` folder. Jobs and matches are visible only to authenticated users, with job creation and matching restricted to admins.

## Scripts

Use `promote_admin.py` to grant admin rights to an existing staff account:

```bash
python scripts/promote_admin.py <username-or-email>
```
