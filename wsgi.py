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
        else:
            print("IP NOT TRUSTED:", g.request_info["ip_address"])

    if session.get("logged_in"):
        g.credentials = get_credentials()
        if session.get("defaultdb"):
            defaultdb = session.get("defaultdb")
        else:
            defaultdb = app.config.get("DB_NAME")
        connected = get_db().connect(
            host=g.credentials["host"],
            port=int(g.credentials["port"]),
            user=g.credentials["user"],
            pswd=g.credentials["pswd"],
            defaultdb=defaultdb
            )
        if connected:
            session["connected"] = True
        else:
            session["connected"] = False
        g.schema = schema.schema(g.localdb, g.db, session.get("uid")).load()
        if not g.schema:
            # Should be a better way to implement this
            # return redirect(url_for('async_schema'))
            new_schema = schema.schema(g.localdb, g.db, session["uid"])
            new_schema.mysql_refresh_dbs(recursive=True, purge=True)
            g.schema = schema.schema(g.localdb, g.db, session.get("uid")).load()
    else:
        app_print("Not Logged In...")
        g.credentials = None

    if not session.get("csrf_token"):
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

    sql_input = ""
    for_query = False
    if request.args:
        action = request.args.get('action')
        table_id = request.args.get('table')
        db_id = request.args.get('db')
        print(action, table_id, db_id, session.get('uid'))
        if action in ("selecttop", "selectall"):
            for_query=True
            table_result = g.localdb.query(
                "SELECT table_name FROM table_store WHERE session_uid=:uid AND db_id=:db_id AND id=:table_id;",
                 {"uid": session.get("uid"), "db_id": db_id, "table_id": table_id},
                 single_line=True) # Verify table name for query
            if action == "selectall" :
                sql_input = "SELECT * FROM `{0}`;".format(table_result["table_name"])
            elif action == "selecttop":
                sql_input = "SELECT * FROM `{0}` LIMIT 100;".format(table_result["table_name"])
            query_results = g.db.query(sql_input)


    if request.form:
        csrf_token = request.form.get("csrf_token")
        if session.get("csrf_token") !=  csrf_token:
            # print("SESSION CSRF:", session.get("csrf_token"), "FORM CSRF:", csrf_token)
            abort(400)
        sql_input = request.form.get("sql_input")
        unsanitized_sql = sql_input.splitlines()
        sanitized_sql = []
        for line in unsanitized_sql:
            cleaned_line = line.strip()
            if cleaned_line[:2] == "--": # Skip single line comments
                pass
            else:
                sanitized_sql.append(cleaned_line)
        sql_input = "".join(sanitized_sql)

        sql_input = sql_input.replace(u"\u2018", "''").replace(u"\u2019", "''") # Sanitize unicode single quotes (and make them sql safe)
        sql_input = sql_input.replace(u"\u201c", '"').replace(u"\u201d", '"') # Sanitize unicode double quotes
        for uni in (u"\ufffd", u"\u25aa", u"\u2022", u"\uf0d8", u"\u2028", u"\u20ac",
            u"\u2026", u"\u2013", u"\u2502", u"\u2122", u"\ufeff", u"\u200b", u"\uf09f",
             u"\uf0fc", u"\u25cf", u"\u202c"):
            sql_input = sql_input.replace(uni, '')

        to_results = request.form.get("to_results")
        if to_results == "1":
            query_results = g.db.query(sql_input)
        else:
            query_results = None
            g.db.execute(sql_input)
        for_query = True

    if for_query:
        return render_template("query.html", sql_input=sql_input, query_results=query_results, query=g.db.last_query)
    else:
        return render_template("query.html")


@app.route("/data/db/<int:db>", methods=["GET", "POST"])
def app_data_db(db):
    if not authorized():
        redirect(url_for('index'))

    tables = g.localdb.query(
        "SELECT * FROM table_store WHERE session_uid=:uid AND db_id=:db_id;",
         {"uid": session.get("uid"), "db_id": db}
         )
    return render_template("data_db.html", tables=tables)


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


@app.route("/action/setdb", methods=["POST"])
def action_setdb():
    if request.form.values:
        session['defaultdb'] = request.form.get('defaultdb')
        new_schema = schema.schema(g.localdb, g.db, session["uid"])
        new_schema.mysql_refresh_dbs(recursive=True, purge=True)
    if request.is_xhr:
        return jsonify(success=True)
    else:
        return redirect(url_for('index'))


@app.route("/async/schema")
def async_schema():
    new_schema = schema.schema(g.localdb, g.db, session["uid"])
    new_schema.mysql_refresh_dbs(recursive=True, purge=True)

    if request.is_xhr:
        return jsonify(success=True)
    else:
        return redirect(url_for('index'))


@app.route("/async/metrics")
def async_metrics():
    db = g.localdb.first(
        "SELECT id FROM db_store WHERE session_uid=:uid AND db_name=:db_name;",
         {"uid": session.get("uid"), "db_name": session.get("defaultdb")}
         )

    tables = g.localdb.query(
        "SELECT id, table_name FROM table_store WHERE session_uid=:uid AND db_id=:db_id;",
         {"uid": session.get("uid"), "db_id": db.get("id")}
         )

    for record in tables:
        sql_input = "SELECT COUNT(*) AS `record_count` FROM `{0}`;".format(record["table_name"])
        result = g.db.first(sql_input)
        g.localdb.execute(
            "UPDATE table_store SET metric_records = :record_count WHERE id = :table_id",
            {"record_count": result["record_count"], "table_id": record.get("id")}
            )

    if request.is_xhr:
        return jsonify(success=True)
    else:
        return redirect(url_for('index'))


@app.route("/debug/events")
def debug_events():
    return render_template("debug_events.html", event_log=g.db.event_log)


@app.route("/debug/queries")
def debug_queries():
    # databases = g.db.query("show databases;")
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
