from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    print("Dropping old tables...")
    db.drop_all()
    print("Creating fresh NetSync schema...")
    db.create_all()
    
    # Create the administrative user
    admin_user = User(
        username="admin",
        email="admin@netsync.ph",
        password_hash=generate_password_hash("admin123")
    )
    db.session.add(admin_user)
    db.session.commit()
    
    print("Database Reset Successful!")
    print("Log in with Username: admin | Password: admin123")