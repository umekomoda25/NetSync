import os
import numpy as np
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

# --- CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:LupinThe3rd!@localhost:5432/fiber_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# --- MODELS ---
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), nullable=False)
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

with app.app_context():
    db.create_all()

# --- AI HELPER ---
def predict_material_need(estimated_qty):
    X = np.array([[50], [100], [200], [500]])
    y = np.array([55, 110, 225, 560])
    model = LinearRegression().fit(X, y)
    prediction = model.predict([[estimated_qty]])
    return float(prediction[0])

# --- ROUTES ---

@app.route('/')
def dashboard():
    all_projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template('dashboard.html', projects=all_projects)

@app.route('/survey')
def survey():
    return render_template('survey.html')

@app.route('/create-project', methods=['POST'])
def create_project():
    site_name = request.form.get('site_name')
    file = request.files.get('site_photo')
    if file and site_name:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        new_project = Project(site_name=site_name, photo_filename=filename)
        db.session.add(new_project)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete-project/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/evaluate/<int:project_id>')
def evaluate(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('evaluate.html', project=project)

@app.route('/add-material/<int:project_id>', methods=['POST'])
def add_material(project_id):
    qty = float(request.form.get('quantity', 0))
    u_price = float(request.form.get('unit_price', 0))
    prediction = predict_material_need(qty)
    new_mat = Material(project_id=project_id, item_name=request.form.get('item_name'), 
                       quantity_estimated=qty, ai_prediction=prediction, 
                       unit=request.form.get('unit'), unit_price=u_price)
    project = Project.query.get(project_id)
    project.status = 'Evaluating'
    db.session.add(new_mat)
    db.session.commit()
    return redirect(url_for('evaluate', project_id=project_id))

@app.route('/implement/<int:project_id>')
def implement(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('implement.html', project=project)

@app.route('/add-log/<int:project_id>', methods=['POST'])
def add_log(project_id):
    desc = request.form.get('description')
    file = request.files.get('log_photo')
    filename = secure_filename(file.filename) if file and file.filename != '' else None
    if filename:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    new_log = TaskLog(project_id=project_id, description=desc, log_photo=filename)
    project = Project.query.get(project_id)
    project.status = 'Implementation'
    db.session.add(new_log)
    db.session.commit()
    return redirect(url_for('implement', project_id=project_id))

@app.route('/report/<int:project_id>')
def report(project_id):
    project = Project.query.get_or_404(project_id)
    total_est = sum(m.quantity_estimated * m.unit_price for m in project.materials)
    total_ai = sum(m.ai_prediction * m.unit_price for m in project.materials)
    return render_template('report.html', project=project, total_est=total_est, total_ai=total_ai)

if __name__ == '__main__':
    app.run(debug=True)