# DATABASE SETUP
import sqlite3_handler


def init_db(path):
    localdb = sqlite3_handler.database().connect(path)
    print("FIRST RUN: Creating cred_store table...")
    sql="""
        CREATE TABLE cred_store(
            id integer PRIMARY KEY,
            session_uid text NOT NULL,
            created text NOT NULL,
            db_host text,
            db_port text,
            db_user text,
            db_pswd text,
            db_db text)
        """
    localdb.execute(sql)

    print("Creating db_store table...")
    sql="""
        CREATE TABLE db_store(
            id integer PRIMARY KEY,
            session_uid text NOT NULL,
            created text NOT NULL,
            db_name text)
        """
    localdb.execute(sql)

    print("Creating table_store table...")
    sql="""
        CREATE TABLE table_store(
            id integer PRIMARY KEY,
            session_uid text NOT NULL,
            created text NOT NULL,
            db_id integer NOT NULL,
            table_name text)
        """
    localdb.execute(sql)
    localdb.close()
