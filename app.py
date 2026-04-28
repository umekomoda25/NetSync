import os
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from werkzeug.utils import secure_filename
from functools import wraps

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

# --- ROLE CONSTANTS ---
ROLE_ADMIN = 'admin'
ROLE_PROJECT_MANAGER = 'project_manager'
ROLE_TEAM_LEADER = 'team_leader'

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default=ROLE_TEAM_LEADER)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    middle_name = db.Column(db.String(100), nullable=True)
    contact_number = db.Column(db.String(30), nullable=True)
    is_archived = db.Column(db.Boolean, default=False)

    def display_name(self):
        if self.first_name and self.last_name:
            mi = f" {self.middle_name[0]}." if self.middle_name else ""
            return f"{self.last_name},{mi} {self.first_name}"
        return self.username

    def can_manage_users(self):
        return self.role in [ROLE_ADMIN, ROLE_PROJECT_MANAGER]

    def can_manage_projects(self):
        return self.role in [ROLE_ADMIN, ROLE_PROJECT_MANAGER]

    def can_mark_complete(self):
        return self.role in [ROLE_ADMIN, ROLE_PROJECT_MANAGER]

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='New')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    photo_filename = db.Column(db.String(200), nullable=True)
    floor_area = db.Column(db.String(100), nullable=True)
    survey_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    materials = db.relationship('Material', backref='project', lazy=True, cascade="all, delete-orphan")
    logs = db.relationship('TaskLog', backref='project', lazy=True, cascade="all, delete-orphan")

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    quantity_estimated = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False, default='unit')
    unit_price = db.Column(db.Float, nullable=False)
    ai_prediction = db.Column(db.Float, nullable=True)

class TaskLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    materials_used = db.Column(db.String(500), nullable=True)
    log_photo = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GlobalInventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False, default='General')
    description = db.Column(db.String(300), nullable=True)
    unit_price = db.Column(db.Float, nullable=False)
    unit_label = db.Column(db.String(50), nullable=False, default='unit')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- DECORATORS ---
def manager_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_manage_projects():
            flash('Access denied: insufficient permissions.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def user_manager_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_manage_users():
            flash('Access denied: insufficient permissions.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# --- ROUTES ---

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and not user.is_archived and check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    projects = Project.query.filter_by(user_id=current_user.id).all()
    indicators = {}
    for p in projects:
        indicators[p.id] = {
            'log_count': len(p.logs),
            'material_count': len(p.materials)
        }
    return render_template('dashboard.html', projects=projects, indicators=indicators)

@app.route('/create-project', methods=['GET', 'POST'])
@login_required
@manager_required
def create_project():
    if request.method == 'POST':
        new_project = Project(
            site_name=request.form.get('site_name'),
            location=request.form.get('location'),
            description=request.form.get('description'),
            status='New',
            user_id=current_user.id
        )
        db.session.add(new_project)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('create.html')

@app.route('/edit-project/<int:project_id>', methods=['GET', 'POST'])
@login_required
@manager_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return "Unauthorized Access", 403
    if request.method == 'POST':
        project.site_name = request.form.get('site_name')
        project.location = request.form.get('location')
        project.description = request.form.get('description')
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('edit.html', project=project)

@app.route('/survey/<int:project_id>', methods=['GET', 'POST'])
@login_required
def survey_project(project_id):
    project = Project.query.get_or_404(project_id)
    if request.method == 'POST':
        file = request.files.get('site_photo')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            project.photo_filename = filename
        project.floor_area = request.form.get('floor_area')
        project.survey_note = request.form.get('survey_note')
        project.status = 'Surveyed'
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('survey.html', project=project)

@app.route('/evaluate/<int:project_id>', methods=['GET', 'POST'])
@login_required
def evaluate(project_id):
    project = Project.query.get_or_404(project_id)
    # Load global inventory for the searchable dropdown
    inventory_items = GlobalInventoryItem.query.order_by(GlobalInventoryItem.category, GlobalInventoryItem.item_name).all()
    if request.method == 'POST':
        item = request.form.get('item_name')
        qty = float(request.form.get('quantity'))
        unit = request.form.get('unit') or 'unit'
        price = float(request.form.get('unit_price'))
        prediction = qty * 1.12
        new_material = Material(
            project_id=project_id, item_name=item,
            quantity_estimated=qty, unit=unit,
            unit_price=price, ai_prediction=prediction
        )
        if project.status == 'New' or project.status == 'Surveyed':
            project.status = 'Surveyed'
        db.session.add(new_material)
        db.session.commit()
        return redirect(url_for('evaluate', project_id=project_id))
    return render_template('evaluate.html', project=project, inventory_items=inventory_items)

@app.route('/delete-material/<int:material_id>', methods=['POST'])
@login_required
def delete_material(material_id):
    mat = Material.query.get_or_404(material_id)
    project_id = mat.project_id
    db.session.delete(mat)
    db.session.commit()
    return redirect(url_for('evaluate', project_id=project_id))

@app.route('/implement/<int:project_id>')
@login_required
def implement(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('implement.html', project=project)

@app.route('/add-log/<int:project_id>', methods=['POST'])
@login_required
def add_log(project_id):
    project = Project.query.get_or_404(project_id)
    desc = request.form.get('description')
    materials_used = request.form.get('materials_used')
    file = request.files.get('log_photo')
    filename = secure_filename(file.filename) if file and file.filename != '' else None
    if filename:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    new_log = TaskLog(project_id=project_id, description=desc,
                      materials_used=materials_used, log_photo=filename)
    if project.status != 'Completed':
        project.status = 'Implementing'
    db.session.add(new_log)
    db.session.commit()
    return redirect(url_for('implement', project_id=project_id))

@app.route('/complete-project/<int:project_id>', methods=['POST'])
@login_required
def complete_project(project_id):
    if not current_user.can_mark_complete():
        flash('Access denied: only Project Managers and Admins can mark projects complete.')
        return redirect(url_for('implement', project_id=project_id))
    project = Project.query.get_or_404(project_id)
    project.status = 'Implementing' if project.status == 'Completed' else 'Completed'
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/report/<int:project_id>')
@login_required
def report(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return "Unauthorized Access", 403
    total_est = sum(m.quantity_estimated * m.unit_price for m in project.materials)
    total_ai = sum(m.ai_prediction * m.unit_price for m in project.materials)
    return render_template('report.html', project=project,
                           total_est=total_est, total_ai=total_ai, now=datetime.utcnow())

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

# ─── GLOBAL INVENTORY ─────────────────────────────────────────────────────────

@app.route('/inventory', methods=['GET', 'POST'])
@login_required
def inventory():
    if request.method == 'POST':
        item = GlobalInventoryItem(
            item_name=request.form.get('item_name'),
            category=request.form.get('category', 'General'),
            description=request.form.get('description', ''),
            unit_price=float(request.form.get('unit_price')),
            unit_label=request.form.get('unit_label', 'unit')
        )
        db.session.add(item)
        db.session.commit()
        return redirect(url_for('inventory'))
    # Gather all project materials to show alongside global inventory
    all_project_materials = Material.query.join(Project).filter(
        Project.user_id == current_user.id
    ).all()
    items = GlobalInventoryItem.query.order_by(GlobalInventoryItem.category, GlobalInventoryItem.item_name).all()
    return render_template('inventory.html', items=items, project_materials=all_project_materials)

@app.route('/inventory/edit/<int:item_id>', methods=['POST'])
@login_required
def edit_inventory_item(item_id):
    item = GlobalInventoryItem.query.get_or_404(item_id)
    item.item_name = request.form.get('item_name', item.item_name)
    item.category = request.form.get('category', item.category)
    item.description = request.form.get('description', item.description)
    item.unit_price = float(request.form.get('unit_price', item.unit_price))
    item.unit_label = request.form.get('unit_label', item.unit_label)
    db.session.commit()
    return redirect(url_for('inventory'))

@app.route('/inventory/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_inventory_item(item_id):
    item = GlobalInventoryItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('inventory'))

# API: inventory as JSON for evaluate.html dropdown
@app.route('/api/inventory')
@login_required
def api_inventory():
    items = GlobalInventoryItem.query.order_by(GlobalInventoryItem.category, GlobalInventoryItem.item_name).all()
    return jsonify([{
        'id': i.id, 'item_name': i.item_name, 'category': i.category,
        'description': i.description, 'unit_price': i.unit_price, 'unit_label': i.unit_label
    } for i in items])

# ─── PROJECT MATERIAL API ─────────────────────────────────────────────────────

@app.route('/api/project-materials/<int:project_id>')
@login_required
def api_project_materials(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify({'materials': [{
        'id': m.id, 'item_name': m.item_name,
        'quantity_estimated': m.quantity_estimated,
        'unit': m.unit, 'unit_price': m.unit_price,
        'ai_prediction': m.ai_prediction
    } for m in project.materials]})

@app.route('/api/update-material-quantities', methods=['POST'])
@login_required
def api_update_material_quantities():
    payload = request.get_json()
    for upd in payload.get('updates', []):
        mat = Material.query.get(int(upd['id']))
        if mat and mat.project.user_id == current_user.id:
            mat.quantity_estimated = float(upd['quantity'])
            mat.ai_prediction = float(upd['quantity']) * 1.12
    db.session.commit()
    return jsonify({'success': True})

# ─── USER MANAGEMENT ─────────────────────────────────────────────────────────

@app.route('/adduser', methods=['GET', 'POST'])
@login_required
@user_manager_required
def add_users():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email') or f"{username}@netsync.local"
        password = request.form.get('password')
        role = request.form.get('role', ROLE_TEAM_LEADER)
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('add_users'))
        new_user = User(
            username=username, email=email,
            password_hash=generate_password_hash(password),
            role=role,
            first_name=request.form.get('first_name', ''),
            last_name=request.form.get('last_name', ''),
            middle_name=request.form.get('middle_name', ''),
            contact_number=request.form.get('contact_number', '')
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('add_users'))

    active_users = User.query.filter_by(is_archived=False).all()
    archived_users = User.query.filter_by(is_archived=True).all()
    return render_template('users.html', users=active_users, archived_users=archived_users)

@app.route('/edit-user/<int:user_id>', methods=['POST'])
@login_required
@user_manager_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    user.first_name = request.form.get('first_name', user.first_name)
    user.last_name = request.form.get('last_name', user.last_name)
    user.middle_name = request.form.get('middle_name', user.middle_name)
    user.contact_number = request.form.get('contact_number', user.contact_number)
    user.username = request.form.get('username', user.username)
    user.role = request.form.get('role', user.role)
    new_pass = request.form.get('password')
    if new_pass:
        user.password_hash = generate_password_hash(new_pass)
    db.session.commit()
    return redirect(url_for('add_users'))

@app.route('/delete-user/<int:user_id>', methods=['POST'])
@login_required
@user_manager_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot delete your own account.")
        return redirect(url_for('add_users'))
    user.is_archived = True
    db.session.commit()
    return redirect(url_for('add_users'))

@app.route('/restore-user/<int:user_id>', methods=['POST'])
@login_required
@user_manager_required
def restore_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_archived = False
    db.session.commit()
    return redirect(url_for('add_users'))

if __name__ == '__main__':
    app.run(debug=True)
