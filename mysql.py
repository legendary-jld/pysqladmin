# import pypyodbc
import pymysql
import datetime

class database:
    def __init__(self, keep_alive=False, debug=False, uri=None, event_history_length=50, query_history_length=10):
        self.created = datetime.datetime.utcnow()
        self.keep_alive = keep_alive
        self.debug = debug
        self.uri = uri
        self.event_history_length = event_history_length
        self.query_history_length = query_history_length
        self.connection = None
        self.query_log = [] # Rolling list of last 10 queries? # query_log.pop(0) # query_log.append(last_query)
        self.event_log = [] # Rolling list of last 50 events
        self.last_query = {
            "query-string": None,
            "initiated": None,
            "completed": None,
            "execution-time": None
            }

    def connect(self, connection_string):
        func = "mysql.database.connect()"
        if connection_string:
            self.uri = connection_string
        if not self.uri:
            self.report(func, "WARNING: Connection string empty")
            return None
        else:
            self.uri = connection_string
        try:
            # self.connection = pypyodbc.connect(connection_string)
            self.connection = pymysql.connect(host='localhost', port=5001, user='', passwd='', db='')
            return self.connection
        except Exception as e:
            self.report(func, "ERROR: {0}".format(e))
        return None

    def reconnect(self):
        func = "mysql.database.reconnect()"
        self.report(func, "WARNING: Connection failed, attempting to reconnect...")
        if not self.connect():
            return None
        return True

    def execute(self, query_string):
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
            "execution-time": None
            }

        try:
            sqlCursor = self.connection.cursor()
        except Exception:
            self.report(func, "ERROR: Failed to create cursor")
            return None

        try:
            sqlCursor.execute(query_string)
        except Exception:
            self.report(func, "ERROR: Query string failed to execute")
            return None
        sqlCursor.commit()
        self.last_query["query-completed"] = datetime.datetime.utcnow()

        query_duration = self.last_query["query-completed"] - self.last_query["query-initiated"]
        self.last_query["execution-time"] = "{}.{:.2}".format(query_duration.seconds, str(query_duration.microseconds*1000))

        sqlCursor.close()
        self.capture(self.last_query)
        return True

    def query(self, query_string, single_line=False):
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
            "execution-time": None
            }

        try:
            sqlCursor = self.connection.cursor()
        except Exception:
            self.report(func, "ERROR: Failed to create cursor")
            return None

        try:
            sqlCursor.execute(query_string)
        except Exception:
            self.report(func, "ERROR: Query string failed to execute")
            return None
        self.last_query["query-completed"] = datetime.datetime.utcnow()

        column_names = [column[0] for column in sqlCursor.description]

        records = []
        if single_line:
            records.append(dict(zip(column_names, sqlCursor.fetchone())))
        else:
            for row in sqlCursor.fetchall():
                records.append(dict(zip(column_names, row)))
        self.last_query["query-processed"] = datetime.datetime.utcnow()

        query_duration = self.last_query["query-completed"] - self.last_query["query-initiated"]
        self.last_query["execution-time"] = "{}.{:.2}".format(query_duration.seconds, str(query_duration.microseconds*1000))

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
