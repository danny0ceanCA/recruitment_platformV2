from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, TextAreaField, FileField, SelectField, SubmitField
from wtforms.validators import DataRequired

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    first_name = StringField('First Name')
    last_name = StringField('Last Name')
    email = StringField('Email')
    name = StringField('Name', validators=[DataRequired()])
    school = StringField('School', validators=[DataRequired()])
    is_admin = BooleanField('Admin')
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class ForgotPasswordForm(FlaskForm):
    """Request a password reset token."""
    username = StringField('Username', validators=[DataRequired()])
    submit = SubmitField('Request Reset')


class ResetPasswordForm(FlaskForm):
    """Reset the password using a valid token."""
    password = PasswordField('New Password', validators=[DataRequired()])
    submit = SubmitField('Reset Password')

class UpdatePasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired()])
    submit = SubmitField('Update Password')

class StudentForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    location = StringField('Location', validators=[DataRequired()])
    experience = TextAreaField('Experience', validators=[DataRequired()])
    resume = FileField('Resume', validators=[DataRequired()])
    submit = SubmitField('Add')

class JobForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    submit = SubmitField('Add Job')

class MatchForm(FlaskForm):
    student_id = SelectField('Student', coerce=int, validators=[DataRequired()])
    job_id = SelectField('Job', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Create Match')


class BulkUploadForm(FlaskForm):
    """Upload a CSV file of students."""
    csv_file = FileField('CSV File', validators=[DataRequired()])
    submit = SubmitField('Upload')
