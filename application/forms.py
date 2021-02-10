from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from application.models import User
import re


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=15)])
    # remember_me = BooleanField("Remember Me")
    submit = SubmitField("Login")

    def validate(self):

        user = User.query.filter_by(email=self.email.data.lower()).first()

        if user and user.check_password(self.password.data):
            name = f"{user.firstname} {user.lastname}"
            is_admin = user.is_Admin
            is_super_admin = user.is_super_admin
            is_approved = user.is_Approved

            if is_admin == 1:
                is_admin = True
            else:
                is_admin = False

            if is_super_admin == 1:
                is_super_admin = True
            else:
                is_super_admin = False

            if is_approved == 1:
                is_approved = True
            else:
                is_approved = False

            result = [True, is_admin, is_approved, name, is_super_admin]
            return result
        else:

            result = [False]
            return result

    def __init__(self, *args, **kwargs):
        FlaskForm.__init__(self, *args, **kwargs)


class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=15)])
    password_confirm = PasswordField("Confirm Password", validators=[DataRequired(), Length(min=6, max=15), EqualTo('password', message='Passwords must match')])
    first_name = StringField("First Name", validators=[DataRequired(), Length(min=2, max=55)])
    last_name = StringField("Last Name", validators=[DataRequired(), Length(min=2, max=55)])
    submit = SubmitField("Register User")
    # validators.EqualTo('confirm', message='Passwords must match')

    def validate_email(self, email):

        user = User.query.filter_by(email=self.email.data.lower()).first()
        email_regex = '^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$'
        username_regex = re.compile('[@_!#$%^&*()<>?/\|}{~:]')

        if user:
            return [False, f"The Email {self.email.data} is already in use. Kindly use another Email."]

        elif username_regex.search(self.first_name.data) != None or username_regex.search(self.last_name.data) != None:
            return [False, f"Firstname/Lastname contains invalid characters. Please try again"]

        elif self.password.data != self.password_confirm.data:
            return [False, f"The passwords entered does not match. Please try again"]

        elif not re.search(email_regex, self.email.data):
            return [False, "The Email address provided is not a valid Email."]

        else:
            return [True]
