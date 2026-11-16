# Exam Portal

A role-based online examination portal built with Flask and PostgreSQL. It is designed for GitHub + Render deployment.

## Features
- Admin, Teacher and Student roles
- Admin creates teacher/student accounts
- Teachers create exams and manage MCQ questions
- Timed exams with server-side deadline checks and automatic submission on the next request
- Per-exam multiple-attempt setting
- Separate result record for every attempt
- Student dashboard and attempt history
- Password hashing, CSRF protection, role checks and timed password-reset tokens

## Run locally
1. Install Python 3.10+.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set `SECRET_KEY` and `ADMIN_PASSWORD`.
4. Run:
   ```bash
   python app.py
   ```
5. Open http://127.0.0.1:5000

The app creates database tables and the initial admin account on first startup. Change the initial admin password immediately after first login.

## Deploy on Render
1. Push this folder to a GitHub repository.
2. In Render, choose **New + → Blueprint**, connect the repository and deploy `render.yaml`.
3. Set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `MAIL_DEFAULT_SENDER` in the Render environment.
4. For Gmail, use a Google **App Password** (not your normal Gmail password); enable 2-Step Verification first.
5. Open the deployed URL and sign in with the admin credentials configured in Render.

Render's free database/service availability and persistence policies can change. For production, use a paid PostgreSQL instance with backups. Never commit `.env` or real credentials.

## Important MVP notes
- Questions are multiple-choice (single correct answer).
- The server enforces exam end time when the student submits or requests the exam page. Browser-side countdown is for user experience, not the security boundary.
- Password reset requires working SMTP settings. If SMTP is not configured, the app displays a configuration error rather than exposing reset tokens.
- This is a starter MVP. Before a high-stakes production launch, add automated tests, rate limiting, audit logs, monitoring, privacy/retention policies, and independent security review.

## Main routes
- `/login`, `/logout`, `/forgot-password`, `/reset-password/<token>`
- `/admin`, `/admin/users`
- `/teacher`, `/teacher/exams/new`, `/teacher/exams/<id>/questions`
- `/student`, `/exam/<id>/start`, `/attempt/<id>`, `/attempt/<id>/submit`
