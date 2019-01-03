import log_reader
import metagame_db
import plumbing
import crayons
import logging
if __name__ == '__main__':
    plumbing.init_logging()
    mdb = metagame_db.MetagameDB()
    l = log_reader.MTGALogReader(open(log_reader.logfile, "rb"))
    for i in range(len(l.index["matches"])):
        mdb.record_game(l.analyze_game(i, 0, log_level=-1).game_record())
    logging.info("Recording finished. Exiting with %s games in store." % crayons.yellow(mdb.game_count(), bold=True))
