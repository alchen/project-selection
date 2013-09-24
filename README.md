
Project-selection
=================

Have multiple jobs for everyone and want to make them all happy? Assign projects with the Hungarian algorithm. Click on the following link to see the [demo](http://project-signup.herokuapp.com).

Like always you should use **virtualenv** when setting up your environment, and use the following commands to install the dependencies:

```
pip install -r requirements.txt
```

Put these in your `config.py`:

```
SECRET_KEY = 'a secret key here for encryption'
TWITTER_CONSUMER_KEY = 'Get this from Twitter'
TWITTER_CONSUMER_SECRET = 'same as above'
DEBUG = True
SQLALCHEMY_DATABASE_URI = 'Your database connection string here'
```
It should be self explanatory that here we use a database to store the project and use Twitter for login and identification purposes.


Now the program is ready to run,

```
python project-selection.py
```

You'd be of course free to use more advanced front-ends like `guincorn` and the other ones that best suits your need.
