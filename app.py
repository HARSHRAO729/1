from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
import sqlite3, os, json, io, datetime, csv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB = os.path.join(BASE_DIR, 'alumni.db')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change_this_secret_for_production')

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT 'user',
        email TEXT
    );
    CREATE TABLE IF NOT EXISTS alumni (
        id INTEGER PRIMARY KEY,
        name TEXT, batch TEXT, email TEXT, phone TEXT, company TEXT, bio TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY,
        title TEXT, date TEXT, venue TEXT, description TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS mentorships (
        id INTEGER PRIMARY KEY,
        title TEXT, alumni_id INTEGER, student_name TEXT, field TEXT, note TEXT, approved INTEGER DEFAULT 1, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS mentor_applications (
        id INTEGER PRIMARY KEY,
        user_id INTEGER, name TEXT, email TEXT, field TEXT, note TEXT, status TEXT DEFAULT 'pending', created_at TEXT
    );
    """)
    cur.execute("SELECT id FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username,password_hash,role,email) VALUES (?,?,?,?)",
                    ('admin', generate_password_hash('adminpass'), 'admin', 'admin@local'))
    conn.commit(); conn.close()

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not session.get('user_id'):
                return redirect(url_for('login', next=request.path))
            if role:
                conn=get_db(); cur=conn.cursor(); cur.execute("SELECT role FROM users WHERE id=?", (session.get('user_id'),))
                row=cur.fetchone(); conn.close()
                if not row or row['role']!=role:
                    flash('Forbidden: insufficient permissions','danger'); return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

@app.context_processor
def inject_user():
    if session.get('user_id'):
        conn=get_db(); cur=conn.cursor(); cur.execute("SELECT id,username,role FROM users WHERE id=?", (session.get('user_id'),)); u=cur.fetchone(); conn.close()
        return dict(current_user=u)
    return dict(current_user=None)

@app.route('/')
def index():
    return render_template('index.html')

# Registration & login
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        username=request.form.get('username'); password=request.form.get('password'); email=request.form.get('email')
        if not username or not password or not email:
            flash('Please provide username, password and email','danger'); return redirect(url_for('register'))
        conn=get_db(); cur=conn.cursor()
        try:
            cur.execute("INSERT INTO users (username,password_hash,role,email) VALUES (?,?,?,?)", (username, generate_password_hash(password), 'user', email))
            conn.commit(); conn.close(); flash('Registration complete. Please login.','success'); return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close(); flash('Username already exists','danger'); return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username=request.form.get('username'); password=request.form.get('password')
        conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM users WHERE username=?", (username,)); user=cur.fetchone(); conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id']=user['id']; flash('Logged in successfully','success'); return redirect(url_for('index'))
        flash('Invalid credentials','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None); flash('Logged out','info'); return redirect(url_for('index'))

# Alumni CRUD
@app.route('/alumni')
@login_required()
def alumni_list():
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM alumni ORDER BY created_at DESC"); rows=cur.fetchall(); conn.close()
    return render_template('alumni_list.html', alumni=rows)

@app.route('/alumni/add', methods=['GET','POST'])
@login_required()
def alumni_add():
    if request.method=='POST':
        vals=(request.form.get('name'), request.form.get('batch'), request.form.get('email'), request.form.get('phone'), request.form.get('company'), request.form.get('bio'), datetime.datetime.utcnow().isoformat())
        conn=get_db(); cur=conn.cursor(); cur.execute("INSERT INTO alumni (name,batch,email,phone,company,bio,created_at) VALUES (?,?,?,?,?,?,?)", vals); conn.commit(); conn.close(); flash('Alumni added','success'); return redirect(url_for('alumni_list'))
    return render_template('alumni_form.html', alumni=None)

@app.route('/alumni/edit/<int:id>', methods=['GET','POST'])
@login_required()
def alumni_edit(id):
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM alumni WHERE id=?", (id,)); a=cur.fetchone()
    if not a: conn.close(); flash('Alumni not found','danger'); return redirect(url_for('alumni_list'))
    if request.method=='POST':
        cur.execute("UPDATE alumni SET name=?,batch=?,email=?,phone=?,company=?,bio=? WHERE id=?", (request.form.get('name'), request.form.get('batch'), request.form.get('email'), request.form.get('phone'), request.form.get('company'), request.form.get('bio'), id))
        conn.commit(); conn.close(); flash('Alumni updated','success'); return redirect(url_for('alumni_list'))
    conn.close(); return render_template('alumni_form.html', alumni=a)

@app.route('/alumni/delete/<int:id>', methods=['POST'])
@login_required()
def alumni_delete(id):
    conn=get_db(); cur=conn.cursor(); cur.execute("DELETE FROM alumni WHERE id=?", (id,)); conn.commit(); conn.close(); flash('Alumni removed','info'); return redirect(url_for('alumni_list'))

# Events CRUD
@app.route('/events')
@login_required()
def events_list():
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM events ORDER BY date DESC"); rows=cur.fetchall(); conn.close(); return render_template('events_list.html', events=rows)

@app.route('/events/add', methods=['GET','POST'])
@login_required()
def event_add():
    if request.method=='POST':
        conn=get_db(); cur=conn.cursor(); cur.execute("INSERT INTO events (title,date,venue,description,created_at) VALUES (?,?,?,?,?)", (request.form.get('title'), request.form.get('date'), request.form.get('venue'), request.form.get('description'), datetime.datetime.utcnow().isoformat())); conn.commit(); conn.close(); flash('Event created','success'); return redirect(url_for('events_list'))
    return render_template('event_form.html', event=None)

@app.route('/events/edit/<int:id>', methods=['GET','POST'])
@login_required()
def event_edit(id):
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM events WHERE id=?", (id,)); e=cur.fetchone()
    if not e: conn.close(); flash('Event not found','danger'); return redirect(url_for('events_list'))
    if request.method=='POST':
        cur.execute("UPDATE events SET title=?,date=?,venue=?,description=? WHERE id=?", (request.form.get('title'), request.form.get('date'), request.form.get('venue'), request.form.get('description'), id))
        conn.commit(); conn.close(); flash('Event updated','success'); return redirect(url_for('events_list'))
    conn.close(); return render_template('event_form.html', event=e)

@app.route('/events/delete/<int:id>', methods=['POST'])
@login_required()
def event_delete(id):
    conn=get_db(); cur=conn.cursor(); cur.execute("DELETE FROM events WHERE id=?", (id,)); conn.commit(); conn.close(); flash('Event removed','info'); return redirect(url_for('events_list'))

# Mentorship & applications
@app.route('/mentorship')
@login_required()
def mentorship_list():
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM mentorships ORDER BY created_at DESC"); rows=cur.fetchall(); conn.close(); return render_template('mentorship_list.html', requests=rows)

@app.route('/mentorship/add', methods=['GET','POST'])
@login_required()
def mentorship_add():
    if request.method=='POST':
        conn=get_db(); cur=conn.cursor(); cur.execute("INSERT INTO mentorships (title,alumni_id,student_name,field,note,approved,created_at) VALUES (?,?,?,?,?,?,?)", (request.form.get('title'), session.get('user_id') or 0, request.form.get('student_name'), request.form.get('field'), request.form.get('note'), 1, datetime.datetime.utcnow().isoformat())); conn.commit(); conn.close(); flash('Mentorship added','success'); return redirect(url_for('mentorship_list'))
    return render_template('mentorship_form.html', req=None)

@app.route('/mentorship/edit/<int:id>', methods=['GET','POST'])
@login_required()
def mentorship_edit(id):
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM mentorships WHERE id=?", (id,)); r=cur.fetchone()
    if not r: conn.close(); flash('Not found','danger'); return redirect(url_for('mentorship_list'))
    if request.method=='POST':
        cur.execute("UPDATE mentorships SET title=?,field=?,note=? WHERE id=?", (request.form.get('title'), request.form.get('field'), request.form.get('note'), id)); conn.commit(); conn.close(); flash('Mentorship updated','success'); return redirect(url_for('mentorship_list'))
    conn.close(); return render_template('mentorship_form.html', req=r)

@app.route('/mentorship/delete/<int:id>', methods=['POST'])
@login_required()
def mentorship_delete(id):
    conn=get_db(); cur=conn.cursor(); cur.execute("DELETE FROM mentorships WHERE id=?", (id,)); conn.commit(); conn.close(); flash('Mentorship removed','info'); return redirect(url_for('mentorship_list'))

@app.route('/apply-mentor', methods=['GET','POST'])
def apply_mentor():
    if request.method=='POST':
        conn=get_db(); cur=conn.cursor(); cur.execute("INSERT INTO mentor_applications (user_id,name,email,field,note,created_at) VALUES (?,?,?,?,?,?)", (session.get('user_id'), request.form.get('name'), request.form.get('email'), request.form.get('field'), request.form.get('note'), datetime.datetime.utcnow().isoformat())); conn.commit(); conn.close(); flash('Application submitted','success'); return redirect(url_for('index'))
    return render_template('apply_mentor.html')

@app.route('/admin/mentor-applications')
@login_required(role='admin')
def admin_mentor_applications():
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM mentor_applications ORDER BY created_at DESC"); rows=cur.fetchall(); conn.close(); return render_template('admin_applications.html', apps=rows)

@app.route('/admin/approve-mentor/<int:app_id>', methods=['POST'])
@login_required(role='admin')
def approve_mentor(app_id):
    conn=get_db(); cur=conn.cursor(); cur.execute("SELECT * FROM mentor_applications WHERE id=?", (app_id,)); app=cur.fetchone()
    if not app: conn.close(); flash('Application not found','danger'); return redirect(url_for('admin_mentor_applications'))
    cur.execute("INSERT INTO mentorships (title,alumni_id,student_name,field,note,approved,created_at) VALUES (?,?,?,?,?,?,?)", (f"Mentor: {app['name']}", app['user_id'] or 0, '', app['field'], app['note'], 1, datetime.datetime.utcnow().isoformat()))
    cur.execute("UPDATE mentor_applications SET status='approved' WHERE id=?", (app_id,)); conn.commit(); conn.close(); flash('Approved','success'); return redirect(url_for('admin_mentor_applications'))

@app.route('/admin/reject-mentor/<int:app_id>', methods=['POST'])
@login_required(role='admin')
def reject_mentor(app_id):
    conn=get_db(); cur=conn.cursor(); cur.execute("UPDATE mentor_applications SET status='rejected' WHERE id=?", (app_id,)); conn.commit(); conn.close(); flash('Rejected','info'); return redirect(url_for('admin_mentor_applications'))

if __name__=='__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0', port=5000)
