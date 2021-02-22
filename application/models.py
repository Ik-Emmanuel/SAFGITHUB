from werkzeug.security import generate_password_hash, check_password_hash
from application import db


class User(db.Model):

    __tablename__ = 'SAF_users_table'

    user_id = db.Column(db.Integer, primary_key=True)
    firstname = db.Column(db.String(100))
    lastname = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    pwdhash = db.Column(db.String(54))
    is_Admin = db.Column(db.Integer)
    is_super_admin = db.Column(db.Integer)
    is_Approved = db.Column(db.Integer)
    DateLoaded = db.Column(db.String(100))

    def __init__(self, firstname, lastname, email, password, is_admin, is_super_admin, is_approved, DateLoaded):
        self.firstname = firstname.title()
        self.lastname = lastname.title()
        self.email = email.lower()
        self.is_Admin = is_admin
        self.is_super_admin = is_super_admin
        self.is_Approved = is_approved
        self.DateLoaded = DateLoaded.title()
        self.set_password(password)

    def set_password(self, password):
        self.pwdhash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.pwdhash, password)

