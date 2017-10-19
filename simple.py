import datetime

def now(): # quick utcnow()
    return datetime.datetime.utcnow()

def bit(value): # boolean to int
    if isinstance(value, str):
        if value.lower() in ("yes", "y", "true", "1"):
            return 1
        else:
            return 0
    else:
        if value:
            return 1
        else:
            return 0
