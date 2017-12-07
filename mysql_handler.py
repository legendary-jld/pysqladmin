# import pypyodbc
import pymysql
import datetime
from collections import OrderedDict

class database:
    def __init__(self, keep_alive=False, debug=False, uri=None, event_history_length=50, query_history_length=10):
        self.created = datetime.datetime.utcnow()
        self.keep_alive = keep_alive
        self.debug = debug
        self.uri = uri
        self.event_history_length = event_history_length
        self.query_history_length = query_history_length
        self.credentials = {
            "host": "localhost",
            "port": 3306,
            "user": None,
            "pswd": None,
            "defaultdb": ""
        }
        self.connection = None
        self.query_log = [] # Rolling list of last 10 queries? # query_log.pop(0) # query_log.append(last_query)
        self.event_log = [] # Rolling list of last 50 events
        self.last_query = {
            "query-string": None,
            "initiated": None,
            "completed": None,
            "execution-time": None,
            "error": None
            }

    def connect(self, host=None, port=None, user=None, pswd=None, defaultdb=None):
        func = "mysql.database.connect()"
        if host:
            self.credentials["host"] = host
        if port:
            self.credentials["port"] = port
        if user:
            self.credentials["user"] = user
        if pswd:
            self.credentials["pswd"] = pswd
        if defaultdb:
            self.credentials["defaultdb"] = defaultdb
        #if connection_string:
        #    self.uri = connection_string
        #if not self.uri:
        #    self.report(func, "WARNING: Connection string empty")
        #    return None
        #else:
        #    self.uri = connection_string
        try:
            # self.connection = pypyodbc.connect(connection_string)
            self.connection = pymysql.connect(
                host=self.credentials["host"],
                port=self.credentials["port"],
                user=self.credentials["user"],
                passwd=self.credentials["pswd"],
                db=self.credentials["defaultdb"])
            return self
        except Exception as e:
            self.report(func, "ERROR: {0}".format(e))
        return None

    def reconnect(self):
        func = "mysql.database.reconnect()"
        self.report(func, "WARNING: Connection failed, attempting to reconnect...")
        if not self.connect():
            return None
        return True

    def execute(self, query_string, values=None):
        func = "mysql.database.execute()"
        if not self.connection:
            self.report(func, "WARNING: No open connection - use mysql.database.connect()")
            return None
        if not query_string:
            self.report(func, "WARNING: Query string empty")
            return None

        self.last_query = {
            "query-string": query_string,
            "query-initiated": datetime.datetime.utcnow(),
            "query-completed": None,
            "query-processed": None,
            "execution-time": None,
            "error": None
            }

        try:
            sqlCursor = self.connection.cursor()
        except Exception:
            self.report(func, "ERROR: Failed to create cursor")
            return None

        try:
            if values:
                sqlCursor.execute(query_string, values)
            else:
                sqlCursor.execute(query_string)
        except pymysql.err.Error as e:
            self.last_query["error"] =  e
            self.report(func, "ERROR: Query string failed to execute: {0}".format(e))
            self.report(func, "QUERY: {0}".format(query_string))
            return None
        self.last_query["query-completed"] = datetime.datetime.utcnow()

        query_duration = self.last_query["query-completed"] - self.last_query["query-initiated"]
        self.last_query["execution-time"] = "{}.{:.2}".format(query_duration.seconds, str(query_duration.microseconds*1000))

        self.connection.commit()
        sqlCursor.close()
        self.capture(self.last_query)
        return True

    def query(self, query_string, values=None, single_line=False):
        func = "mysql.database.query()"
        if not self.connection:
            self.report(func, "WARNING: No open connection - use mysql.database.connect()")
            return None
        if not query_string:
            self.report(func, "WARNING: Query string empty")
            return None

        self.last_query = {
            "query-string": query_string,
            "query-initiated": datetime.datetime.utcnow(),
            "query-completed": None,
            "query-processed": None,
            "execution-time": None,
            "error": None
            }

        try:
            sqlCursor = self.connection.cursor()
        except Exception:
            self.report(func, "ERROR: Failed to create cursor")
            return None

        try:
            if values:
                sqlCursor.execute(query_string, values)
            else:
                sqlCursor.execute(query_string)
        except pymysql.err.Error as e:
            self.last_query["error"] =  e
            self.report(func, "ERROR: Query string failed to execute: {0}".format(e))
            self.report(func, "QUERY: {0}".format(query_string))
            return None
        self.last_query["query-completed"] = datetime.datetime.utcnow()

        if sqlCursor.description:
            column_names = [column[0].lower() for column in sqlCursor.description]
        else:
            column_names = []
        if single_line:
            data = sqlCursor.fetchone()
            if data:
                records.append(dict(zip(column_names, data)))
            else:
                records = {}
        else:
            data = sqlCursor.fetchall()
            records = []
            if data:
                for row in data:
                    records.append(OrderedDict(zip(column_names, row)))
        self.last_query["query-processed"] = datetime.datetime.utcnow()

        query_duration = self.last_query["query-completed"] - self.last_query["query-initiated"]
        self.last_query["execution-time"] = "{}.{:.2}".format(query_duration.seconds, str(query_duration.microseconds*1000))
        print("Records:", records)
        sqlCursor.close()
        self.capture(self.last_query)
        return records

    def first(self, query_string):
        func = "mysql.database.first()"
        return self.query(query_string, single_line=True)

    def capture(self, query_info):
        if len(self.query_log) >= self.query_history_length:
            self.query_log.pop(0) # Exceeded history length, remove oldest item
        self.query_log.append(query_info)

    def report(self, function_desc, message):
        # warn="message" and error="message" (Warn will return less in debugging)
        if len(self.event_log) >= self.event_history_length:
            self.event_log.pop(0) # Exceeded history length, remove oldest item
        event_string = "{0} | {1}".format(function_desc, message)
        self.event_log.append(event_string)
        print(event_string)

    def close(self):
        if self.connection:
            self.connection.close()
