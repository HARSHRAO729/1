AlumniConnect - Flask (Local) Demo
==================================

This is a full-featured local Flask demo of the "Digital Platform for Centralized Alumni Data Management and Engagement".
It includes Admin login, Alumni CRUD, Events, Mentorship requests, Insights, and JSON import/export.

Default admin credentials:
  username: admin
  password: adminpass

**Important:** Change the default password before any real use. The app stores data in SQLite (alumni.db).
To run:
1. Create a virtual environment (recommended)
   python -m venv venv
   source venv/bin/activate   # mac/linux
   venv\Scripts\activate    # windows

2. Install requirements
   pip install -r requirements.txt

3. Run
   python app.py

Open http://127.0.0.1:5000 and login with the default admin credentials above.

Files:
- app.py - main Flask application
- alumni.db - SQLite database (created automatically)
- templates/ - Jinja2 HTML templates
- static/style.css - simple styles
- README.md - this file

If you want me to add email notifications, OAuth logins, or convert this to a docker-compose setup, tell me and I will extend it.


Added features:
- Docker & docker-compose (includes mailhog & react frontend scaffold)
- Admin user management (register users)
- Password reset via email (config SMTP via env, MailHog provided in compose)
- CSV bulk upload for alumni (via /alumni/upload-csv)
- Export to Excel (/export/excel)
- Simple JSON API endpoints (/api/*)

Use `./start.sh` to run everything with Docker Compose.
