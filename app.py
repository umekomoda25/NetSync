import os
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from werkzeug.utils import secure_filename
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

# --- CONFIGURATION ---
app.config['SECRET_KEY'] = 'netsync-2026-secure-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:LupinThe3rd!@localhost:5432/netsync_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    projects = db.relationship('Project', backref='owner', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    site_name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200))
    status = db.Column(db.String(20), default='Surveying')
    photo_filename = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    materials = db.relationship('Material', backref='project', lazy=True, cascade="all, delete-orphan")
    logs = db.relationship('TaskLog', backref='project', lazy=True, cascade="all, delete-orphan")

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    item_name = db.Column(db.String(100))
    quantity_estimated = db.Column(db.Float)
    ai_prediction = db.Column(db.Float)
    unit = db.Column(db.String(20))
    unit_price = db.Column(db.Float, default=0.0)

class TaskLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    description = db.Column(db.Text)
    log_photo = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- UNIVERSAL AI FORECAST ---
def run_ai_forecast(qty):
    """Predicts required inventory with a 12% safety margin for tools and materials."""
    X = np.array([[1], [10], [50], [100], [500]])
    y = np.array([1.12, 11.2, 56.0, 112.0, 560.0]) 
    model = LinearRegression().fit(X, y)
    return float(model.predict([[qty]])[0])

# --- AUTH ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed = generate_password_hash(request.form.get('password'))
        user = User(username=request.form.get('username'), email=request.form.get('email'), password_hash=hashed)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- PROJECT MANAGEMENT ---
@app.route('/')
@login_required
def dashboard():
    projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.created_at.desc()).all()
    active = Project.query.filter(Project.user_id==current_user.id, Project.status != 'Completed').count()
    done = Project.query.filter_by(user_id=current_user.id, status='Completed').count()
    return render_template('dashboard.html', projects=projects, active_count=active, completed_count=done)

@app.route('/survey')
@login_required
def survey():
    return render_template('survey.html')

@app.route('/create-project', methods=['POST'])
@login_required
def create_project():
    file = request.files.get('site_photo')
    if file:
        fname = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        project = Project(site_name=request.form.get('site_name'), location=request.form.get('location'), 
                          photo_filename=fname, user_id=current_user.id)
        db.session.add(project)
        db.session.commit()
    return redirect(url_for('dashboard'))

# --- MATERIAL & TOOL PLANNING ---
@app.route('/evaluate/<int:project_id>')
@login_required
def evaluate(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return "Unauthorized Access", 403
    return render_template('evaluate.html', project=project)

@app.route('/add-material/<int:project_id>', methods=['POST'])
@login_required
def add_material(project_id):
    project = Project.query.get_or_404(project_id)
    qty = float(request.form.get('quantity', 0))
    mat = Material(project_id=project_id, item_name=request.form.get('item_name'),
                   quantity_estimated=qty, ai_prediction=run_ai_forecast(qty),
                   unit=request.form.get('unit'), unit_price=float(request.form.get('unit_price', 0)))
    
    if project.status == 'Surveying':
        project.status = 'Evaluating'
        
    db.session.add(mat)
    db.session.commit()
    return redirect(url_for('evaluate', project_id=project_id))

@app.route('/delete-material/<int:material_id>', methods=['POST'])
@login_required
def delete_material(material_id):
    mat = Material.query.get_or_404(material_id)
    project_id = mat.project_id
    if mat.project.user_id == current_user.id:
        db.session.delete(mat)
        db.session.commit()
    return redirect(url_for('evaluate', project_id=project_id))

# --- LOGS & REPORTS ---
@app.route('/implement/<int:project_id>')
@login_required
def implement(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return "Unauthorized Access", 403
    return render_template('implement.html', project=project)

@app.route('/add-log/<int:project_id>', methods=['POST'])
@login_required
def add_log(project_id):
    project = Project.query.get_or_404(project_id)
    desc = request.form.get('description')
    file = request.files.get('log_photo')
    filename = secure_filename(file.filename) if file and file.filename != '' else None
    if filename:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    new_log = TaskLog(project_id=project_id, description=desc, log_photo=filename)
    if project.status != 'Completed':
        project.status = 'Implementation'
    db.session.add(new_log)
    db.session.commit()
    return redirect(url_for('implement', project_id=project_id))

@app.route('/report/<int:project_id>')
@login_required
def report(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return "Unauthorized Access", 403
    total_est = sum(m.quantity_estimated * m.unit_price for m in project.materials)
    total_ai = sum(m.ai_prediction * m.unit_price for m in project.materials)
    return render_template('report.html', project=project, total_est=total_est, total_ai=total_ai, now=datetime.utcnow())

@app.route('/complete-project/<int:project_id>', methods=['POST'])
@login_required
def complete_project(project_id):
    project = Project.query.get_or_404(project_id)
    project.status = 'Completed' if project.status != 'Completed' else 'Implementation'
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete-project/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id == current_user.id:
        db.session.delete(project)
        db.session.commit()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)