# DATABASE SETUP

import sqlite3_handler


def init_db(path):
    localdb = sqlite3_handler.database().connect(path)
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
    # Create Database_store
    # Create Table store
    localdb.close()
