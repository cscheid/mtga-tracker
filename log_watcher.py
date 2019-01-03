# from watchdog.events import FileSystemEventHandler
# from watchdog.observers import Observer
import watchdog
import os
import pickle
import hashlib
import json
import sys
import time
import threading

logdir = os.getenv("APPDATA")+"\\..\\LocalLow\\Wizards Of The Coast\\MTGA\\"
logfile = os.getenv("APPDATA")+"\..\LocalLow\Wizards Of The Coast\MTGA\output_log.txt"
pickle_file = logfile[:-4] + ".pickle"

# ##############################################################################

# class MyEventHandler(FileSystemEventHandler):
#     def on_modified(self, event):
#         print("Modified!", event)

# event_handler = MyEventHandler()

# if __name__ == '__main__':
#     observer = Observer()
#     observer.schedule(event_handler, logdir, recursive=True)
#     observer.start()
#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         observer.stop()
#     observer.join()

def worker():
    while True:
        print("\r                                                \r",     end='')
        print("Current output.txt size: %s" % os.path.getsize(logfile),   end='')
        sys.stdout.flush()
        time.sleep(0.25)
    return

t = threading.Thread(target=worker)
t.start()
t.join()

