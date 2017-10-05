import datetime
from flask import Flask, render_template, g, request, jsonify
# local libaries
from mysql import database

app = Flask(__name__)
app.config.from_pyfile('wsgi.cfg')

db = database(keep_alive=True, debug=True)
db.connect(app.config)

@app.before_request
def before_request():
    g.request_info = {
        "initiated": datetime.datetime.utcnow(),
        "completed": None,
        "browser": request.user_agent.browser
        }


@app.route("/")
def index():
    databases = db.query("show databases;")
    # tables = db.query("show tables;")
    return jsonify(databases)

@app.route("/debug/events")
def debug_events():
    return jsonify(db.event_log)

@app.route("/debug/queries")
def debug_queries():
    databases = db.query("show databases;")
    return jsonify(db.query_log)


if __name__ == "__main__":
    app.run()
