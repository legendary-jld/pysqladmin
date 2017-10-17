import datetime

def now(): # quick utcnow()
    return datetime.datetime.utcnow()

def bit(value): # boolean to int
    if value:
        return 1
    else:
        return 0
