import threading
import queue
import sys
import os
import time

# polling-based and ugly, but windows has terrible support for this kind of stuff
# apparently? watchdog didn't really work for me

def watch_file(filename, q, stop_box, from_position=-1):
    if from_position == -1:
        current_endpoint = os.path.getsize(filename)
    else:
        current_endpoint = 0
        
    def watch_it():
        nonlocal current_endpoint
        while True:
            file_size = os.path.getsize(filename)
            if file_size < current_endpoint:
                # file was restarted
                current_endpoint = 0
            if file_size > current_endpoint:
                with open(filename, "rb") as f:
                    f.seek(current_endpoint)
                    while True:
                        l = f.readline().decode('ascii')
                        if not l.endswith('\n'):
                            # end of file, so line might be truncated. don't report
                            break
                        q.put(l)
                        current_endpoint = f.tell()
            sys.stdout.flush()
            time.sleep(0.25)
            if stop_box[0] == False:
                break
        q.put("")
        print("Done with watching file.")
    return watch_it

class FileLike(object):
    def __init__(self, q, t, stop_box):
        self.q = q
        self.t = t
        self.stop_box = stop_box
    def seek(self, *args):
        pass
    def tell(self, *args):
        return None
    def readline(self):
        return self.q.get()
    def __iter__(self):
        return self
    def __next__(self):
        return self.q.get()
    def kill_thread(self):
        self.stop_box[0] = False

def stream_file_contents(filename, from_position=-1):
    q = queue.Queue()
    stop_box = [True]
    t = threading.Thread(target=watch_file(filename, q, stop_box, from_position))
    t.start()
    return FileLike(q, t, stop_box)
