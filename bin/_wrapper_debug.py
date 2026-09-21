import runpy, sys, traceback, time
from datetime import datetime
logp = r"C:\Kopied\kopied.log"
def w(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] WRAPPER: {msg}\n"
    try:
        open(logp,"a",encoding="utf-8").write(line)
    except Exception:
        pass
w(f"starting pid={os.getpid() if (os:=__import__('os')) else '?'}")
try:
    sys.argv = [r"C:\Kopied\bin\kopied.py"]
    runpy.run_path(r"C:\Kopied\bin\kopied.py", run_name="__main__")
    w("exited normally")
except SystemExit as e:
    w(f"SystemExit {e.code}")
except Exception:
    w("exception:\n" + traceback.format_exc())
