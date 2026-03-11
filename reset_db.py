from app import app, db

with app.app_context():
    print("Dropping old tables...")
    db.drop_all()
    print("Creating fresh NetSync schema...")
    db.create_all()
    print("Ready! Now register a new account at /register.")