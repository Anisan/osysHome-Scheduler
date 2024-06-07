from flask_wtf import  FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, DateTimeField
from wtforms.validators import DataRequired


class TaskForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    code = TextAreaField('Code', validators=[DataRequired()])
    crontab = StringField('Crontab')
    runtime = DateTimeField('Runtime')
    expire = DateTimeField('Expire')
    submit = SubmitField('Submit')
