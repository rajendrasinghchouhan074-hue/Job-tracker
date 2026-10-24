# Job Application Tracker

A multi-user web app to track job applications: company, role, status, follow-up dates, notes and job links.

Built with Python, Flask and SQLite.

## Features
- Register, login and logout (passwords are hashed)
- Each user sees only their own data
- Add, edit and delete applications
- Dashboard with status counts
- Search and filter
- Follow-up dates (overdue ones in red)
- CSV export
- Change password
- Admin page with per-user counts

## Run locally
    pip install -r requirements.txt
    python app.py

Optional environment variables: SECRET_KEY, ADMIN_USERNAME
