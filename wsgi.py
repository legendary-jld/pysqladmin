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
    setup.init_db(DB_PATH)


def get_db():
    db = getattr(g, 'db', None)
    if db is None:
        g.db = mysql_handler.database(keep_alive=True, debug=True)
        return g.db
    return g.db


def get_credentials():
    g.localdb = sqlite3_handler.database().connect(DB_PATH)
    cred_store = g.localdb.first("SELECT * FROM cred_store WHERE session_uid='{uid}'".format(uid=session.get("uid")))
    if cred_store:
        app_print("Credentials found...")
        e = AES.new(app.config["SECRET_KEY"], AES.MODE_CFB, app.config["AES_IV"])
        credentials = {
            "host": e.decrypt(cred_store["db_host"]).decode(),
            "port": e.decrypt(cred_store["db_port"]).decode(),
            "user": e.decrypt(cred_store["db_user"]).decode(),
            "pswd": e.decrypt(cred_store["db_pswd"]).decode()
        }
        return credentials
    else:
        return None


def store_credentials(ip, host, port, user, pswd):
    app_print("Saving new credentials...")
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
    # print("PyMy: ", session_uid)


@app.before_request
def before_request():
    g.request_info = {
        "browser": request.user_agent.browser,
        "initiated": datetime.datetime.utcnow()
        }
    if session.get("logged_in"):
        g.credentials = get_credentials()
        get_db().connect(
            host=g.credentials["host"],
            port=int(g.credentials["port"]),
            user=g.credentials["user"],
            pswd=g.credentials["pswd"]
            )
        app_print("Logged In...")
    else:
        app_print("Not Logged In...")
        g.credentials = None

    if session.get("csrf_token") is None:
        session["csrf_token"] = str(uuid.uuid4())

    # app_print(session)


@app.teardown_appcontext
def teardown_appcontext(exception):
    if getattr(g, 'localdb', None) is not None:
        g.localdb.close()
    if getattr(g, 'db', None) is not None:
        g.db.close()


@app.route("/")
def index():
    if session.get("logged_in") and g.credentials:
        dbs = g.db.query("SHOW DATABASES;")
        databases = []
        if dbs:
            for db in dbs:
                db_name = db["database"]
                if not db_name[:1] == "#":
                    if db_name in ("information_schema","mysql","performance_schema","sys") or db_name[:1] == "#":
                        db_system =  True
                    else:
                        db_system = False
                    databases.append({"name":db_name, "system":db_system})
            databases = sorted(databases, key=lambda data: (data["system"], data["name"]))
        return render_template("dashboard.html", databases=databases)
    else:
        return render_template("login.html")


@app.route("/login", methods=["POST"])
def app_login():
    ip_address = request.form.get("ip_address")
    db_host = request.form.get("db_host")
    db_port = request.form.get("db_port")
    user_login = request.form.get("user_login")
    user_pswd = request.form.get("user_password")
    if get_db().connect(host=db_host, port=int(db_port), user=user_login, pswd=user_pswd):
        app_print("Connected to database...")
        store_credentials(ip=ip_address, host=db_host, port=db_port, user=user_login, pswd=user_pswd)
        session["logged_in"] = True
    return redirect(url_for("index"))

@app.route("/logout")
def app_logout():
    session.clear()
    return redirect(url_for('index'))

@app.route("/debug/events")
def debug_events():
    return jsonify(g.db.event_log)


@app.route("/debug/queries")
def debug_queries():
    databases = g.db.query("show databases;")
    return jsonify(g.db.query_log)

def now():
    return datetime.datetime.utcnow()

def app_print(message):
    print(now().strftime("%b-%d %H-%M-%S |"), "PyMy: ", message)

if __name__ == "__main__":
    if app.config["DEBUG"] == False:
        app.run(ssl_context='adhoc')
    else:
        app.run()
