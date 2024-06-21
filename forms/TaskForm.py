from flask_wtf import  FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, DateTimeLocalField
from wtforms.validators import DataRequired, Optional


class TaskForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    code = TextAreaField('Code', validators=[DataRequired()])
    crontab = StringField('Crontab',validators=[Optional()])
    runtime = DateTimeLocalField('Runtime',validators=[Optional()])
    expire = DateTimeLocalField('Expire',validators=[Optional()])
    submit = SubmitField('Submit')
