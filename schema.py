from simple import now, bit
# SCHEMA STORE
class schema:
    def __init__ (self, localdb, mysqldb, session_uid):
        self.localdb = localdb
        self.mysqldb = mysqldb
        self.session_uid =  session_uid
        self.full_schema = None

    def load(self):
        databases = self.localdb.query("SELECT id,db_name,flag_sys FROM db_store WHERE session_uid=:uid;", {"uid": self.session_uid})
        db_dict = {}
        for db in databases:
            tables = self.localdb.query(
                "SELECT id,table_name FROM table_store WHERE session_uid=:uid AND db_id=:db_id;",
                 {"uid": self.session_uid, "db_id": db["id"]}
                 )
            table_dict = {}
            for table in tables:
                columns = self.localdb.query("""
                    SELECT id,column_name,column_type,is_nullable FROM column_store
                    WHERE session_uid=:uid AND db_id=:db_id AND table_id=:table_id;
                    """
                    , {"uid": self.session_uid, "db_id": db["id"], "table_id": table["id"]})
                table["columns"] = columns
                table_dict[table["table_name"]] = table
            db["tables"] = table_dict # add tables information to database
            db_dict[db["db_name"]] = db
        self.full_schema = db_dict
        return self.full_schema

    def mysql_purge_schema(self):
        clean_dbs = self.localdb.execute("DELETE FROM db_store WHERE session_uid=:uid;", {"uid": self.session_uid})
        clean_tables = self.localdb.execute("DELETE FROM table_store WHERE session_uid=:uid;", {"uid": self.session_uid})
        clean_columns = self.localdb.execute("DELETE FROM column_store WHERE session_uid=:uid;", {"uid": self.session_uid})

    # db_store (id integer, session_uid text, created text, db_name text)
    def mysql_refresh_dbs(self, recursive=False, purge=False, skip_system_dbs=True):
        if purge:
            self.mysql_purge_schema()

        dbs = self.mysqldb.query("SHOW DATABASES;")
        if dbs:
            databases = []
            for db in dbs:
                db_name = db["database"]
                if not db_name[:1] == "#": # Check not #lost+found database
                    if db_name in ("information_schema","mysql","performance_schema","sys"):
                        db_system =  True
                    else:
                        db_system = False
                    databases.append({"name":db_name, "system":db_system})
            databases = sorted(databases, key=lambda data: (data["system"], data["name"]))
            for db in databases:
                if not db["system"] or( db["system"] and not skip_system_dbs):
                    sql = """
                        INSERT INTO db_store (session_uid, created, db_name, flag_sys)
                        VALUES (:uid, :created, :database, :flag_sys)
                        """
                    self.localdb.execute(sql, {"uid":self.session_uid, "created":now(), "database": db["name"], "flag_sys": bit(db["system"])})
        if recursive:
            dbs = self.localdb.query("SELECT id,db_name,flag_sys FROM db_store WHERE session_uid=:uid;", {"uid":self.session_uid})
            if dbs:
                for db in dbs:
                    self.mysql_refresh_tables(db, recursive=True)

    # table_store (id integer, session_uid text, created text, db_id, integer, table_name text)
    def mysql_refresh_tables(self, db, recursive=False, purge=False):
        if purge:
            clean_tables = self.localdb.execute(
                "DELETE FROM table_store WHERE session_uid=:uid AND db_id=:db_id;",
                 {"uid":self.session_uid, "db_id": db["id"]})
            clean_columns = self.localdb.execute(
                "DELETE FROM column_store WHERE session_uid=:uid AND db_id=:db_id;",
                 {"uid":self.session_uid, "db_id": db["id"]})

        tables = self.mysqldb.query("SELECT table_name FROM information_schema.tables where table_schema=%(db_name)s;", {"db_name": db["db_name"]})
        for table in tables:
            if not table["table_name"][:2] == "x$": # Exclude views
                sql = """
                    INSERT INTO table_store (session_uid, created, db_id, table_name)
                    VALUES (:uid, :created, :db_id, :table_name)
                    """
                self.localdb.execute(sql, {"uid":self.session_uid, "created":now(), "db_id": db["id"], "table_name": table["table_name"]})
        if recursive:
            tables = self.localdb.query("SELECT id,db_id,table_name FROM table_store WHERE session_uid=:uid", {"uid":self.session_uid})
            for table in tables:
                self.mysql_refresh_columns(db, table, recursive=True)

    # column_store (id integer, session_uid text, created text, table_id, integer, field_name text)
    def mysql_refresh_columns(self, db, table, recursive=False, purge=False):
        if purge:
            clean_tables = self.localdb.execute(
                "DELETE FROM column_store WHERE session_uid=:uid AND table_id=:table_id;",
                 {"uid":self.session_uid, "table_id": table["id"]})

        columns = self.mysqldb.query("""
            SELECT column_name,column_type,is_nullable FROM information_schema.columns
            WHERE table_schema=%(db_name)s AND table_name=%(table_name)s;""",
            {"db_name": db["db_name"], "table_name": table["table_name"]})
        for column in columns:
            sql = """
                INSERT INTO column_store (session_uid, created, db_id, table_id, column_name, column_type, is_nullable)
                VALUES (:uid, :created, :db_id, :table_id, :column_name, :column_type, :is_nullable)
                """
            self.localdb.execute(sql, {"uid":self.session_uid, "created":now(), "db_id": table["db_id"], "table_id": table["id"],
                "column_name": column["column_name"], "column_type": column["column_type"], "is_nullable": bit(column["is_nullable"])})
