import os, datetime, uuid
from flask import Flask, render_template, g, request, \
    session, redirect, url_for, jsonify
from Crypto.Cipher import AES
# local libaries
import setup
import mysql_handler
import sqlite3_handler

app = Flask(__name__)
app.config.from_pyfile('wsgi.cfg')
DB_PATH = "local.db"

if not os.path.isfile(DB_PATH):
    setup.init_db()


def get_db():
    print("GETTING DB")
    db = getattr(g, 'db', None)
    if db is None:
        g.db = mysql_handler.database(keep_alive=True, debug=True)
    return g.db


def get_credentials():
    print("GETTING CREDENTIALS")
    g.localdb = sqlite3_handler.database().connect(DB_PATH)
    cred_store = g.localdb.first("SELECT * FROM cred_store WHERE session_uid='{uid}'".format(uid=session.get("uid")))
    if cred_store:
        e = AES.new(app.config["SECRET_KEY"], AES.MODE_CFB, app.config["AES_IV"])
        credentials = {
            "host": e.decrypt(cred_store["db_host"]),
            "port": e.decrypt(cred_store["db_port"]),
            "user": e.decrypt(cred_store["db_user"]),
            "pswd": e.decrypt(cred_store["db_pswd"])
        }
        return credentials
    else:
        return None


def store_credentials(ip, host, port, user, pswd):
    print("STORING CREDENTIALS")
    g.localdb = sqlite3_handler.database().connect(DB_PATH)
    session_uid = "{ip}:{id}".format(ip=ip,id=str(uuid.uuid4())) #Assign to BOTH variables
    sql = """
        INSERT INTO cred_store (session_uid, created, db_host, db_port, db_user, db_pswd)
        VALUES (:uid, :created, :host, :port, :user, :pswd)
        """
    e = AES.new(app.config["SECRET_KEY"], AES.MODE_CFB, app.config["AES_IV"])
    g.localdb.execute(sql, {
        "uid":session_uid, "created":now(),
        "host":e.encrypt(host), "port":e.encrypt(port),
        "user":e.encrypt(user), "pswd":e.encrypt(pswd)
        })
    session["uid"] = session_uid
    print(session_uid)


@app.before_request
def before_request():
    g.request_info = {
        "browser": request.user_agent.browser,
        "initiated": datetime.datetime.utcnow()
        }
    if session.get("logged_in"):
        g.credentials = get_credentials()
        get_db()
    else:
        g.credentials = None

    if not session.get("csrf_token"):
        session["csrf_token"] = str(uuid.uuid4())


@app.teardown_appcontext
def teardown_appcontext(exception):
    if getattr(g, 'localdb', None) is not None:
        g.localdb.close()
    if getattr(g, 'db', None) is not None:
        g.db.close()


@app.route("/")
def index():
    if session.get("logged_in") and g.db.connection:
        return render_template("dashboard.html")
    else:
        return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    ip_address = request.form.get("ip_address")
    db_host = request.form.get("db_host")
    db_port = request.form.get("db_port")
    user_login = request.form.get("user_login")
    user_pswd = request.form.get("user_password")
    if get_db().connect(host=db_host, port=int(db_port), user=user_login, pswd=user_pswd):
        store_credentials(ip=ip_address, host=db_host, port=db_port, user=user_login, pswd=user_pswd)
        session["logged_in"] = True
    return redirect(url_for("index"))

def now():
    return datetime.datetime.utcnow()

@app.route("/debug/events")
def debug_events():
    return jsonify(g.db.event_log)


@app.route("/debug/queries")
def debug_queries():
    databases = g.db.query("show databases;")
    return jsonify(g.db.query_log)


if __name__ == "__main__":
    app.run()
