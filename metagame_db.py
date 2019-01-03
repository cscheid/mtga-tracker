import sqlite3
import json
import logging

##############################################################################

class MetagameDB:

    def __init__(self):
        self.con = sqlite3.connect('games.db')
        con = self.con
        cursor = con.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        if len(cursor.fetchall()) == 0:
            logging.info("database is empty! Will init database")
            self.cretae_db()
        cursor.execute("SELECT count(*) FROM games")
        logging.debug("Initialized DB.")
        logging.debug("%s games in store." % cursor.fetchall()[0][0])
    
    def __del__(self):
        self.con.close()
    
    # currently a very dumb kv store for json blobs. yay.
    def create_db(self):
        c = self.con.cursor()
        c.execute('''CREATE TABLE games(match_id text, game_id integer, content text)''')
        c.execute('''CREATE INDEX games_id_index ON games(match_id, game_id)''')
        self.con.commit()

    def game_count(self):
        con = self.con
        cursor = con.cursor()
        cursor.execute("SELECT count(*) FROM games")
        return cursor.fetchall()[0][0]
        
    def game_exists(self, match_id, game_id):
        c = self.con.cursor()
        c.execute('''SELECT * FROM games WHERE match_id=? AND game_id=?''', (match_id, game_id))
        return len(c.fetchall()) != 0

    def record_game(self, game_record):
        match_id = game_record["matchId"]
        game_id = game_record["gameId"]
        if self.game_exists(match_id, game_id):
            logging.info("Cowardly refusing to add game %s:%s which already exists." % (match_id, game_id))
            return False
        c = self.con.cursor()
        c.execute('''INSERT INTO games VALUES (?,?,?)''', (
            match_id, game_id, json.dumps(game_record)))
        self.con.commit()
        return True

    def list_all_games(self):
        c = self.con.cursor()
        c.execute('''SELECT * FROM games''')
        return list(json.loads(x[2]) for x in c.fetchall())
        
