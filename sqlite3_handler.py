import sqlite3
import datetime

class database:
    def __init__(self):
        self.created = datetime.datetime.utcnow()
        self.connection = None

    def connect(self, path="local.db"):
        func = "sqlite3.database.connect()"
        try:
            self.connection = sqlite3.connect(path)
            return self
        except Exception as e:
            self.report(func, "ERROR: {0}".format(e))
        return None

    def execute(self, query_string, values=None):
        func = "sqlite3.database.execute()"
        if not self.connection:
            self.report(func, "WARNING: No open connection - use sqlite3.database.connect()")
            return None
        if not query_string:
            self.report(func, "WARNING: Query string empty")
            return None

        try:
            sqlCursor = self.connection.cursor()
        except Exception as e:
            self.report(func, "ERROR: Failed to create cursor: {e}".format(e))
            return None

        try:
            if values:
                sqlCursor.execute(query_string, values)
            else:
                sqlCursor.execute(query_string)
        except Exception as e:
            self.report(func, "ERROR: Query string failed to execute: {0}".format(e))
            return None
        self.connection.commit()
        sqlCursor.close()
        return True

    def query(self, query_string, single_line=False):
        func = "sqlite3.database.query()"
        if not self.connection:
            self.report(func, "WARNING: No open connection - use mysql.database.connect()")
            return None
        if not query_string:
            self.report(func, "WARNING: Query string empty")
            return None

        try:
            sqlCursor = self.connection.cursor()
        except Exception as e:
            self.report(func, "ERROR: Failed to create cursor: {0}".format(e))
            return None

        try:
            sqlCursor.execute(query_string)
        except Exception as e:
            self.report(func, "ERROR: Query string failed to execute: {0}".format(e))
            return None

        column_names = [column[0] for column in sqlCursor.description]
        if single_line:
            data = sqlCursor.fetchone()
            if data:
                records = dict(zip(column_names, data))
            else:
                records = {}
                self.report(func, "WARNING: Empty result set: {0}".format(query_string))
        else:
            data = sqlCursor.fetchall()
            records = []
            if data:
                for row in data:
                    records.append(dict(zip(column_names, row)))
            else:
                self.report(func, "WARNING: Empty result set: {0}".format(query_string))

        sqlCursor.close()
        return records

    def first(self, query_string):
        func = "sqlite3.database.first()"
        return self.query(query_string, single_line=True)

    def report(self, function_desc, message):
        event_string = "{0} | {1}".format(function_desc, message)
        print(event_string)

    def close(self):
        if self.connection:
            self.connection.close()
