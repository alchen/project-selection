import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy.ext.associationproxy import association_proxy
from flask.ext.login import LoginManager, current_user, login_required
from flask.ext.login import logout_user, login_user
from flask.ext.oauth import OAuth
from flask.ext.seasurf import SeaSurf
from munkres import Munkres

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config.from_pyfile('config.py')

csrf = SeaSurf(app)
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.setup_app(app)

oauth = OAuth()
twitter = oauth.remote_app(
    'twitter',
    base_url='https://api.twitter.com/1.1/',
    request_token_url='https://api.twitter.com/oauth/request_token',
    access_token_url='https://api.twitter.com/oauth/access_token',
    authorize_url='https://api.twitter.com/oauth/authorize',
    consumer_key=app.config['TWITTER_CONSUMER_KEY'],
    consumer_secret=app.config['TWITTER_CONSUMER_SECRET']
)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(24), unique=True, nullable=False)
    oauth_token = db.Column(db.String(200), nullable=False)
    oauth_secret = db.Column(db.String(200), nullable=False)

    def get_id(self):
        return self.id

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def is_authenticated(self):
        return True

    def __repr__(self):
        return '%s' % self.name


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(500), unique=True, nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __repr__(self):
        return '%s' % self.name


class Priority(db.Model):
    project_id = db.Column(db.Integer,
                           db.ForeignKey('project.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    priority = db.Column(db.Integer, nullable=False)


@app.route('/')
def show_index():
    if current_user.is_authenticated():
        projects = db.session.query(Project.name,
                                    User.name.label('assignee'),
                                    Priority.priority).\
            outerjoin(User).\
            outerjoin(Priority, db.and_(Project.id == Priority.project_id,
                                        current_user.id == Priority.user_id)).\
            group_by(Project.id, User.id, Priority.priority).\
            order_by(Project.id).all()
        return render_template('list.html', projects=projects)
    else:
        projects = db.session.query(Project.name,
                                    User.name.label('assignee')).\
            outerjoin(User).\
            group_by(Project.id, User.id).\
            order_by(Project.id).all()
        return render_template('prompt.html', projects=projects)


@login_required
@app.route('/new', methods=['POST', 'GET'])
def new_project():
    if request.method == 'GET':
        return render_template('new_project.html')
    else:
        project_name = request.form['project_name']
        db.session.add(Project(name=project_name))
        db.session.commit()
        flash('You just successfully added a new project: %s' % project_name)
        return redirect(url_for('show_index'))


@login_required
@app.route('/set', methods=['POST', 'GET'])
def set_priorities():
    if request.method == 'GET':
        projects = db.session.query(Project.id, Project.name,
                                    Priority.priority).\
            outerjoin(Priority, db.and_(Project.id == Priority.project_id,
                                        current_user.id == Priority.user_id)).\
            group_by(Project.id, Priority.priority).\
            order_by(Project.id).all()
        num_projects = len(projects)
        return render_template('set_priorities.html', projects=projects,
                               num_projects=num_projects)
    else:
        project_ids = []
        project_priorities = []

        for field, value in request.form.items():
            if (field.startswith('project_') and field[8:].isdigit()
                    and value.isdigit() and value > '0'):
                project_ids.append(int(field[8:]))
                project_priorities.append(int(value))

        if len(project_priorities) != len(set(project_priorities)):
            flash('Remember projects cannot have the same priorities.')
            return redirect(url_for('set_priorities'))
        else:
            db.session.query(Priority.user_id).\
                filter(Priority.user_id == current_user.id).\
                delete(synchronize_session=False)
            for project_id, project_priority in zip(project_ids,
                                                    project_priorities):
                new_priority = Priority(user_id=current_user.id,
                                        project_id=project_id,
                                        priority=project_priority)
                db.session.add(new_priority)

        db.session.commit()

        return redirect(url_for('show_index'))


@login_required
@app.route('/assign')
def assign_projects():
    projects = Project.query.join(Priority).order_by(Project.id).all()
    users = User.query.join(Priority).order_by(User.id).all()
    user_ids = [user.id for user in users]
    default_priority = len(projects) + 1
    matrix = []

    for project in projects:
        priority_query = db.session.query(User.id, Priority.priority).\
            outerjoin(Priority, db.and_(User.id == Priority.user_id,
                                        Priority.project_id == project.id)).\
            filter(User.id.in_(user_ids)).\
            order_by(User.id).all()
        priorities = [user_priority_tuple.priority
                      if user_priority_tuple.priority is not None
                      else default_priority
                      for user_priority_tuple in priority_query]
        matrix.append(priorities)

    if len(matrix) != 0:
        db.session.query(Project).update({Project.assignee_id: None})
        m = Munkres()
        indexes = m.compute(matrix)
        for row, column in indexes:
            projects[row].assignee_id = user_ids[column]
        db.session.commit()

    flash('Project assignments updated.')
    return redirect(url_for('show_index'))


@login_manager.user_loader
def load_user(id):
    return User.query.get(id)


@twitter.tokengetter
def get_twitter_token():
    if current_user.is_authenticated():
        return (current_user.oauth_token, current_user.oauth_secret)
    else:
        return None


@app.route('/login')
def login():
    if current_user.is_authenticated():
        return redirect('/')
    else:
        return twitter.authorize(
            callback=url_for(
                'oauth_authorized',
                next=request.args.get('next') or request.referrer or None
            )
        )


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect('/')


@app.route('/oauth-authorized')
@twitter.authorized_handler
def oauth_authorized(resp):
    next_url = request.args.get('next') or url_for('show_index')
    if resp is None:
        flash('You are denied the request to sign in.')
        return redirect(next_url)

    this_account = User.query.filter_by(name=resp['screen_name']).first()
    if this_account is None:
        new_account = User(
            name=resp['screen_name'],
            oauth_token=resp['oauth_token'],
            oauth_secret=resp['oauth_token_secret']
        )
        db.session.add(new_account)
        db.session.commit()
        this_account = new_account
    else:
        this_account.name = resp['screen_name']
        this_account.oauth_token = resp['oauth_token']
        this_account.oauth_secret = resp['oauth_token_secret']
        db.session.commit()

    login_user(this_account)

    return redirect(next_url)

#db.drop_all()
db.create_all()

if __name__ == '__main__':
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
