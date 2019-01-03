import sqlite3


##############################################################################

class MetagameDB:

    def __init__(self):
        con = sqlite3.connect('games.db')
        cursor = con.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        print(cursor.fetchall())
        
        
