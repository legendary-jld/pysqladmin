import os, datetime, uuid
from flask import Flask, render_template, g, request, \
    session, redirect, url_for, jsonify, abort
from Crypto.Cipher import AES
# local libaries below
from simple import now, bit
import setup, schema, mysql_handler, sqlite3_handler

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
    if session.get("OPENSHIFT"):
        app_print("LOAD OPENSHIFT CREDENTIALS")
        credentials = {
            "host": app.config.get('DB_HOST'),
            "port": app.config.get('DB_PORT'),
            "user": app.config.get('DB_USER'),
            "pswd": app.config.get('DB_PASS')
        }
        return credentials
    else:
        app_print("LOAD LOCAL CREDENTIALS")
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
        "initiated": datetime.datetime.utcnow(),
        "ip_address": request.headers.get("x-forwarded-for") # For Openshift v2, (app.py - tornado must be set to forward these headers)
        }

    if not session.get("logged_in"):
        if g.request_info["ip_address"] in app.config.get("TRUSTED_IP_ADDRESSES"):
            # app_print("PASSED AS TRUSTED IP")
            if not session.get("OPENSHIFT") and app.config.get("OPENSHIFT_BUILD_NAMESPACE"):
                # app_print("RECOGNIZED AS OPENSHIFT")
                session["OPENSHIFT"] = True
                session["OPENSHIFT_VERSION"] = 3
                session["logged_in"] = True
                session_uid = "{ip}:{id}".format(ip=g.request_info["ip_address"], id=str(uuid.uuid4())) #Assign to BOTH variables
                session["uid"] = session_uid

    if session.get("logged_in"):
        g.credentials = get_credentials()
        connected = get_db().connect(
            host=g.credentials["host"],
            port=int(g.credentials["port"]),
            user=g.credentials["user"],
            pswd=g.credentials["pswd"]
            )
        if connected:
            session["connected"] = True
        else:
            session["connected"] = False
        g.schema = schema.schema(g.localdb, g.db, session.get("uid")).load()
    else:
        app_print("Not Logged In...")
        g.credentials = None

    if not session.get("csrf_token"):
        # print("OLD SESSION TOKEN:", session.get('csrf_token'))
        session["csrf_token"] = "csrf_{0}".format(str(uuid.uuid4()))
        # print("NEW SESSION TOKEN:", session.get('csrf_token'))

    # app_print(session)


@app.teardown_appcontext
def teardown_appcontext(exception):
    if getattr(g, 'localdb', None) is not None:
        g.localdb.close()
    if getattr(g, 'db', None) is not None:
        g.db.close()


@app.route("/")
def index():
    if not authorized():
        return render_template("login.html")

    return render_template("base_nav.html")


@app.route("/query", methods=["GET", "POST"])
def app_query():
    if not authorized():
        redirect(url_for('index'))

    if request.form:
        csrf_token = request.form.get("csrf_token")
        if session.get("csrf_token") !=  csrf_token:
            # print("SESSION CSRF:", session.get("csrf_token"))
            # print("FORM CSRF:", csrf_token)
            abort(400)
        sql_input = request.form.get("sql_input")
        to_results = request.form.get("to_results")
        if to_results == "1":
            query_results = g.db.query(sql_input)
        else:
            query_results = None
            g.db.execute(sql_input)
        return render_template("query.html", query_results=query_results, query=g.db.last_query)


    return render_template("query.html")


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

@app.route("/async/schema")
def async_schema():
    new_schema = schema.schema(g.localdb, g.db, session["uid"])
    new_schema.mysql_refresh_dbs(recursive=True, purge=True)
    return jsonify(success=True)

@app.route("/debug/events")
def debug_events():
    return render_template("debug_events.html", event_log=g.db.event_log)


@app.route("/debug/queries")
def debug_queries():
    databases = g.db.query("show databases;")
    return jsonify(g.db.query_log)


def authorized():
    if session.get("logged_in") and g.credentials:
        return True
    else:
        return False


def app_print(message):
    print(now().strftime("%b-%d %H-%M-%S |"), "PySQL: ", message)


@app.errorhandler(500)
def internal_server_error_500(error):
    app_print(str(error))
    return str(error)


if __name__ == "__main__":
    if app.config["DEBUG"] == False:
        app.run(ssl_context='adhoc')
    else:
        app.run()
