import logging
import sys

def init_logging():
    logging.basicConfig(filename='mtga-watch.log', level=logging.DEBUG)
    logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    
