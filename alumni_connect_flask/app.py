from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify, current_app
import sqlite3, os, json, io, datetime, csv, secrets, smtplib
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_cors import CORS
from dotenv import load_dotenv
from openpyxl import Workbook
from email.message import EmailMessage

load_dotenv()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB = os.path.join(BASE_DIR, 'alumni.db')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY','change_this_secret_for_production')
CORS(app)

EMAIL_HOST = os.environ.get('EMAIL_HOST','localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT','25'))
EMAIL_FROM = os.environ.get('EMAIL_FROM','no-reply@alumniconnect.local')

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # users table (admin/roles)
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT 'admin'
    )''')
    # alumni
    cur.execute('''CREATE TABLE IF NOT EXISTS alumni (
        id INTEGER PRIMARY KEY,
        name TEXT,
        batch TEXT,
        email TEXT,
        phone TEXT,
        company TEXT,
        bio TEXT,
        created_at TEXT
    )''')
    # events
    cur.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY,
        title TEXT,
        date TEXT,
        venue TEXT,
        description TEXT,
        created_at TEXT
    )''')
    # mentorship requests
    cur.execute('''CREATE TABLE IF NOT EXISTS mentorships (
        id INTEGER PRIMARY KEY,
        title TEXT,
        student_name TEXT,
        field TEXT,
        note TEXT,
        created_at TEXT
    )''')
    # password reset tokens
    cur.execute('''CREATE TABLE IF NOT EXISTS pw_reset_tokens (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        token TEXT,
        expires_at TEXT
    )''')
    conn.commit()
    # create default admin if not exists
    cur.execute("SELECT * FROM users WHERE username = ?", ('admin',))
    if not cur.fetchone():
        # default password: adminpass (please change)
        pw = generate_password_hash('adminpass')
        cur.execute("INSERT INTO users (username,password_hash,role) VALUES (?,?,?)", ('admin', pw, 'admin'))
        conn.commit()
    conn.close()

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('user'):
                return redirect(url_for('login', next=request.path))
            if role:
                # check role
                conn=get_db(); cur=conn.cursor()
                cur.execute("SELECT role FROM users WHERE username=?", (session.get('user'),))
                row=cur.fetchone(); conn.close()
                if not row or row['role']!=role:
                    flash('Forbidden: insufficient permissions','danger'); return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user'] = username
            flash('Logged in successfully','success')
            nxt = request.args.get('next') or url_for('index')
            return redirect(nxt)
        flash('Invalid credentials','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Logged out','info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
@login_required(role='admin')
def register_user():
    # Admin-only: create new user with role
    if request.method=='POST':
        username = request.form.get('username'); password = request.form.get('password'); role = request.form.get('role','editor')
        if not username or not password:
            flash('Provide username and password','danger'); return redirect(url_for('register_user'))
        conn=get_db(); cur=conn.cursor()
        try:
            cur.execute("INSERT INTO users (username,password_hash,role) VALUES (?,?,?)", (username, generate_password_hash(password), role))
            conn.commit(); flash('User created','success'); return redirect(url_for('index'))
        except sqlite3.IntegrityError:
            flash('Username exists','danger'); return redirect(url_for('register_user'))
    return render_template('register.html')

@app.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method=='POST':
        email = request.form.get('email')
        # find user by email in alumni table and user table mapping - for demo we assume username==email for non-admins
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (email,))
        user = cur.fetchone()
        if not user:
            # try alumni email
            cur.execute("SELECT * FROM alumni WHERE email = ?", (email,))
            alum = cur.fetchone()
            if alum:
                # try to find a user with same email as username
                cur.execute("SELECT * FROM users WHERE username = ?", (email,))
                user = cur.fetchone()
        if not user:
            flash('No user found with that email','danger'); conn.close(); return redirect(url_for('login'))
        # create token
        token = secrets.token_urlsafe(24)
        expires = (datetime.datetime.utcnow()+datetime.timedelta(hours=2)).isoformat()
        cur.execute("INSERT INTO pw_reset_tokens (user_id,token,expires_at) VALUES (?,?,?)", (user['id'], token, expires))
        conn.commit(); conn.close()
        # send email (simple SMTP)
        reset_link = url_for('reset_password', token=token, _external=True)
        try:
            send_email(email, 'Password reset', f'Click the link to reset your password: {reset_link}')
            flash('Password reset email sent (check MailHog if using dev)','info')
        except Exception as e:
            flash(f'Failed to send email: {e}','danger')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET','POST'])
def reset_password(token):
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM pw_reset_tokens WHERE token = ?", (token,))
    row = cur.fetchone()
    if not row:
        flash('Invalid or expired token','danger'); conn.close(); return redirect(url_for('login'))
    if datetime.datetime.fromisoformat(row['expires_at']) < datetime.datetime.utcnow():
        flash('Token expired','danger'); conn.close(); return redirect(url_for('login'))
    if request.method=='POST':
        new_pw = request.form.get('password')
        cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_pw), row['user_id']))
        cur.execute("DELETE FROM pw_reset_tokens WHERE id = ?", (row['id'],))
        conn.commit(); conn.close(); flash('Password updated','success'); return redirect(url_for('login'))
    conn.close(); return render_template('reset_password.html', token=token)

def send_email(to, subject, body):
    msg = EmailMessage()
    msg['From'] = EMAIL_FROM
    msg['To'] = to
    msg['Subject'] = subject
    msg.set_content(body)
    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as s:
        s.send_message(msg)

@app.route('/')
@login_required()
def index():
    return render_template('index.html')

# ----- Alumni CRUD & CSV upload -----
@app.route('/alumni')
@login_required()
def alumni_list():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM alumni ORDER BY created_at DESC")
    rows = cur.fetchall(); conn.close()
    return render_template('alumni_list.html', alumni=rows)

@app.route('/alumni/add', methods=['GET','POST'])
@login_required()
def alumni_add():
    if request.method=='POST':
        data = {k:request.form.get(k,'') for k in ('name','batch','email','phone','company','bio')}
        data['created_at'] = datetime.datetime.utcnow().isoformat()
        conn = get_db(); cur=conn.cursor()
        cur.execute("INSERT INTO alumni (name,batch,email,phone,company,bio,created_at) VALUES (?,?,?,?,?,?,?)",
                    (data['name'],data['batch'],data['email'],data['phone'],data['company'],data['bio'],data['created_at']))
        conn.commit(); conn.close()
        flash('Alumni added','success')
        return redirect(url_for('alumni_list'))
    return render_template('alumni_form.html', alumni=None)

@app.route('/alumni/upload-csv', methods=['POST'])
@login_required()
def alumni_upload_csv():
    f = request.files.get('file')
    if not f:
        flash('No file uploaded','danger'); return redirect(url_for('alumni_list'))
    stream = io.StringIO(f.stream.read().decode('utf-8'))
    reader = csv.reader(stream)
    conn=get_db(); cur=conn.cursor()
    count=0
    for row in reader:
        if not row or not row[0].strip(): continue
        name=row[0].strip(); batch=row[1].strip() if len(row)>1 else ''; email=row[2].strip() if len(row)>2 else ''; phone=row[3].strip() if len(row)>3 else ''; company=row[4].strip() if len(row)>4 else ''; bio=row[5].strip() if len(row)>5 else ''
        cur.execute("INSERT INTO alumni (name,batch,email,phone,company,bio,created_at) VALUES (?,?,?,?,?,?,?)", (name,batch,email,phone,company,bio,datetime.datetime.utcnow().isoformat()))
        count+=1
    conn.commit(); conn.close(); flash(f'Imported {count} rows','success'); return redirect(url_for('alumni_list'))

# ----- Events -----
@app.route('/events')
@login_required()
def events_list():
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM events ORDER BY date DESC")
    rows=cur.fetchall(); conn.close()
    return render_template('events_list.html', events=rows)

@app.route('/events/add', methods=['GET','POST'])
@login_required()
def event_add():
    if request.method=='POST':
        t=request.form.get('title'); date=request.form.get('date'); venue=request.form.get('venue'); desc=request.form.get('description')
        conn=get_db(); cur=conn.cursor()
        cur.execute("INSERT INTO events (title,date,venue,description,created_at) VALUES (?,?,?,?,?)",(t,date,venue,desc,datetime.datetime.utcnow().isoformat()))
        conn.commit(); conn.close(); flash('Event created','success'); return redirect(url_for('events_list'))
    return render_template('event_form.html', event=None)

# ----- Mentorship -----
@app.route('/mentorship')
@login_required()
def mentorship_list():
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM mentorships ORDER BY created_at DESC"); rows=cur.fetchall(); conn.close()
    return render_template('mentorship_list.html', requests=rows)

@app.route('/mentorship/add', methods=['GET','POST'])
@login_required()
def mentorship_add():
    if request.method=='POST':
        title=request.form.get('title'); student=request.form.get('student_name'); field=request.form.get('field'); note=request.form.get('note')
        conn=get_db(); cur=conn.cursor(); cur.execute("INSERT INTO mentorships (title,student_name,field,note,created_at) VALUES (?,?,?,?,?)",(title,student,field,note,datetime.datetime.utcnow().isoformat()))
        conn.commit(); conn.close(); flash('Request added','success'); return redirect(url_for('mentorship_list'))
    return render_template('mentorship_form.html', req=None)

# ----- Insights & export/import -----
@app.route('/insights')
@login_required()
def insights():
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT batch, COUNT(*) as cnt FROM alumni GROUP BY batch ORDER BY cnt DESC")
    by_batch = cur.fetchall()
    cur.execute("SELECT COUNT(*) as total FROM alumni"); total = cur.fetchone()['total']
    conn.close()
    return render_template('insights.html', by_batch=by_batch, total=total)

@app.route('/export/json')
@login_required()
def export_json():
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM alumni"); alumni= [dict(ix) for ix in cur.fetchall()]
    cur.execute("SELECT * FROM events"); events=[dict(ix) for ix in cur.fetchall()]
    cur.execute("SELECT * FROM mentorships"); mentorships=[dict(ix) for ix in cur.fetchall()]
    conn.close()
    data={'alumni':alumni,'events':events,'mentorships':mentorships}
    buf = io.BytesIO(); buf.write(json.dumps(data, indent=2).encode('utf-8')); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='alumni_connect_export.json', mimetype='application/json')

@app.route('/export/excel')
@login_required()
def export_excel():
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM alumni"); alumni = cur.fetchall()
    wb = Workbook(); ws = wb.active; ws.title = "Alumni"
    ws.append(['ID','Name','Batch','Email','Phone','Company','Bio','Created At'])
    for a in alumni:
        ws.append([a['id'], a['name'], a['batch'], a['email'], a['phone'], a['company'], a['bio'], a['created_at']])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='alumni.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/import/json', methods=['GET','POST'])
@login_required()
def import_json():
    if request.method=='POST':
        f = request.files.get('file')
        if not f:
            flash('No file uploaded','danger'); return redirect(url_for('index'))
        data = json.load(f.stream)
        conn=get_db(); cur=conn.cursor()
        # simple import: clear and insert
        if 'alumni' in data:
            cur.execute("DELETE FROM alumni")
            for a in data['alumni']:
                cur.execute("INSERT INTO alumni (name,batch,email,phone,company,bio,created_at) VALUES (?,?,?,?,?,?,?)",
                            (a.get('name'),a.get('batch'),a.get('email'),a.get('phone'),a.get('company'),a.get('bio'), a.get('created_at') or datetime.datetime.utcnow().isoformat()))
        if 'events' in data:
            cur.execute("DELETE FROM events")
            for e in data['events']:
                cur.execute("INSERT INTO events (title,date,venue,description,created_at) VALUES (?,?,?,?,?)",
                            (e.get('title'),e.get('date'),e.get('venue'),e.get('description'), e.get('created_at') or datetime.datetime.utcnow().isoformat()))
        if 'mentorships' in data:
            cur.execute("DELETE FROM mentorships")
            for m in data['mentorships']:
                cur.execute("INSERT INTO mentorships (title,student_name,field,note,created_at) VALUES (?,?,?,?,?)",
                            (m.get('title'),m.get('student_name'),m.get('field'),m.get('note'), m.get('created_at') or datetime.datetime.utcnow().isoformat()))
        conn.commit(); conn.close(); flash('Import complete','success'); return redirect(url_for('index'))
    return redirect(url_for('index'))

# ----- Simple JSON API endpoints -----
@app.route('/api/alumni', methods=['GET','POST'])
def api_alumni():
    if request.method=='GET':
        conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM alumni"); rows=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify(rows)
    else:
        data = request.get_json() or {}
        conn=get_db(); cur=conn.cursor()
        cur.execute("INSERT INTO alumni (name,batch,email,phone,company,bio,created_at) VALUES (?,?,?,?,?,?,?)",
                    (data.get('name'),data.get('batch'),data.get('email'),data.get('phone'),data.get('company'),data.get('bio'), datetime.datetime.utcnow().isoformat()))
        conn.commit(); conn.close(); return jsonify({'status':'ok'}), 201

@app.route('/api/events', methods=['GET','POST'])
def api_events():
    if request.method=='GET':
        conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM events"); rows=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify(rows)
    else:
        data = request.get_json() or {}
        conn=get_db(); cur=conn.cursor()
        cur.execute("INSERT INTO events (title,date,venue,description,created_at) VALUES (?,?,?,?,?)",
                    (data.get('title'),data.get('date'),data.get('venue'),data.get('description'), datetime.datetime.utcnow().isoformat()))
        conn.commit(); conn.close(); return jsonify({'status':'ok'}), 201

@app.route('/api/mentorships', methods=['GET','POST'])
def api_mentorships():
    if request.method=='GET':
        conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM mentorships"); rows=[dict(r) for r in cur.fetchall()]; conn.close(); return jsonify(rows)
    else:
        data = request.get_json() or {}
        conn=get_db(); cur=conn.cursor()
        cur.execute("INSERT INTO mentorships (title,student_name,field,note,created_at) VALUES (?,?,?,?,?)",
                    (data.get('title'),data.get('student_name'),data.get('field'),data.get('note'), datetime.datetime.utcnow().isoformat()))
        conn.commit(); conn.close(); return jsonify({'status':'ok'}), 201

if __name__=='__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
