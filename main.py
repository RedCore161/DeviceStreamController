import datetime
import json
import math
import os
import queue
import shlex
import time
import requests

from subprocess import check_call
from threading import Thread

# Loading config
# =====================================

with open('config.json') as f:
    CONFIG = json.load(f)

SERVER_IP = CONFIG.get("stream_ip")
STREAM_KEY = CONFIG.get("stream_key")
BASE_URL = CONFIG.get("url")
DEVICE = CONFIG.get("device", "/dev/video0")
SLEEP_TIME = CONFIG.get("sleep_time", 25)

# Setting up parameters
# =====================================

URL_FETCH = f'{BASE_URL}fetch/'
URL_CLEAR = f'{BASE_URL}clear/'
URL_PING = f'{BASE_URL}ping/'
URL_UPLOAD = f'{BASE_URL}upload/'

RECORD_TIME = 300

STILL_NAME = "still.jpg"
SNAP_NAME = "snap.mp4"

# Known commands
# =====================================

START_CAMERA = 1
STOP_FFMPEG = 2

START_STREAM = 100

STILL_IMAGE = 200

PERFORM_UPDATE = 500
SHUTDOWN = 501
PING = 502


# =====================================


class StreamCommand(object):
    """
    wrapper-class to execute a command in a fire-and-forget thread
    """

    def __init__(self, _cmd, cmd_id=0, _upload_file=None, instant=False):
        """
        :param _cmd: command to execute
        """
        self.cmd_id = cmd_id
        self.cmd = _cmd
        self.upload_file = _upload_file
        self.stdout = None
        self.stderr = None
        self.token = None
        self.instant = instant

    def has_cmd(self):
        return self.cmd is not None

    def is_instant(self):
        return self.instant

    def run_instant(self):
        if self.has_cmd():
            result = run_process(self.cmd)
            if result > 0:
                print(f"[ERROR] Instant-Command failed!")
                return

            print("Instant-Command DONE!")

    def run(self):
        if self.has_cmd():

            result = run_process(self.cmd)
            if result > 0:
                print(f"[ERROR] Command failed!")
            else:
                print("Command DONE!")

            print("self.upload_file", self.upload_file)

            if self.upload_file:
                print("Starting Upload!")
                tries = 10
                while not os.path.exists(self.upload_file) and tries > 0:
                    print("Waiting for file creation...")
                    time.sleep(3)
                    tries -= 1

                if os.path.exists(self.upload_file):
                    tries = 10
                    while os.path.getsize(self.upload_file) < 100 and tries > 0:
                        print("Waiting for file writting done")
                        time.sleep(3)
                        tries -= 1

                    print("SIZE:", os.path.getsize(self.upload_file))
                    time.sleep(10)
                    print("SIZE:", os.path.getsize(self.upload_file))

                    if tries > 0:
                        result = requests.post(URL_UPLOAD,
                                               files={'file': open(self.upload_file, 'rb')},
                                               data={"token": self.token, "key": STREAM_KEY,
                                                     "filesize": os.path.getsize(self.upload_file)}
                                               )
                        print("Upload Done!", result.request)
                        print("Upload Done!", result.__dict__)
            else:
                print("[ERROR] No upload-file was created!")

    def __str__(self):
        return f"{self.cmd_id} => {self.cmd}"


# ======================================================================================================================


class CallMotherShip(Thread):

    def __init__(self, q):
        Thread.__init__(self)
        self.last_action_time = datetime.datetime.now() - datetime.timedelta(minutes=5)
        self.daemon = True
        self.queue = q

    def calc_delay(self):
        """ Dynamic sleep-calculation depending on day-time and last command-execution """

        _max = 400
        _min = SLEEP_TIME
        now = datetime.datetime.now()

        fac = min(math.log2((now - self.last_action_time).seconds + 1) / 10 + 0.2, 1)

        delay = int((_max * math.pow(abs(((now.hour * 60 + now.minute) / 720) - 1), 8) + _min) * fac)
        print(f"Delay: {delay}")
        return delay

    def run(self):
        while True:
            try:
                response = requests.post(URL_FETCH, data={'key': STREAM_KEY})
                cmds = response.json()
                response.close()

                for cmd in cmds:
                    message(f"Command: '{cmd}'")
                    #TODO is top command?

                    sc = build_command(cmd)
                    if sc.is_instant():
                        sc.run_instant()
                    else:
                        self.queue.put(sc)

            except Exception as e:
                message(f"Error: {e}")

            time.sleep(self.calc_delay())


# ======================================================================================================================


def run_process(cmd):
    print(f"Run Command: {cmd}")
    return check_call(shlex.split(cmd))


def build_ffmpeg_params(params):
    build = []

    print("params", params)

    if params.get("vf", False):
        build.append("-vf vflip")

    if params.get("hf", False):
        build.append("-vf hflip")

    if params.get("duration", False):
        build.append(f"-t {params['duration']}")
    else:
        build.append(f"-t {RECORD_TIME}")

    # https://www.linuxuprising.com/2020/01/ffmpeg-how-to-crop-videos-with-examples.html
    if params.get("width", 0) > 0 and params.get("height", 0) > 0:
        w = float(params.get("width")) / 100.0
        h = float(params.get("height")) / 100.0
        x = float(params.get("x")) / 100.0
        y = float(params.get("y")) / 100.0
        build.append(f"-vf crop=w=iw*{w}:h=ih*{h}:x=iw*{x}:y=ih*{y}")


    #build.append(f"-vf drawtext=\"expansion=strftime:fontsize=24:fontcolor=red:shadowcolor=black:shadowx=2:shadowy=1:text='%Y-%m-%d\ %H\\\\:%M\\\\:%S':x=10:y=10\"")


    return ' '.join(build)


def build_command(cmd) -> StreamCommand:
    params = cmd.get("params", {})

    if cmd['cmd'] == START_CAMERA:
        exe = f"ffmpeg -hide_banner -f video4linux2 -i {DEVICE} {build_ffmpeg_params(params)} -y {SNAP_NAME}"
        return StreamCommand(exe, cmd_id=cmd['id'], _upload_file=SNAP_NAME)

    elif cmd['cmd'] == START_STREAM:
        # exe = f"ffmpeg -re -f video4linux2 -i {DEVICE} -c:v h264 -c:a aac -f flv rtmp://{SERVER_IP}/app/{STREAM_KEY}"
        exe = f"ffmpeg -hide_banner -f video4linux2 -i {DEVICE} {build_ffmpeg_params(params)} -c:v h264 -c:a aac -f flv rtmp://{SERVER_IP}/app/{STREAM_KEY}"
        return StreamCommand(exe, cmd_id=cmd['id'])

    elif cmd['cmd'] == STILL_IMAGE:
        exe = f"ffmpeg -hide_banner -f video4linux2 -i {DEVICE} {build_ffmpeg_params(params)} -vframes 1 -y {STILL_NAME}"
        return StreamCommand(exe, cmd_id=cmd['id'], _upload_file=STILL_NAME)

    elif cmd['cmd'] == STOP_FFMPEG:
        exe = 'killall ffmpeg'
        return StreamCommand(exe, instant=True)

    elif cmd['cmd'] == PERFORM_UPDATE:
        exe = './updateController.sh'
        return StreamCommand(exe, instant=True, cmd_id=cmd['id'])

    elif cmd['cmd'] == SHUTDOWN:
        exe = 'sudo shutdown -P'
        return StreamCommand(exe, instant=True, cmd_id=cmd['id'])

    elif cmd['cmd'] == PING:
        return StreamCommand("ls", cmd_id=cmd['id'])

    return StreamCommand(None)


def message(msg):
    print(msg)
    with open(f"logs/log-{datetime.datetime.now().strftime('%Y-%m-%d')}.txt", "a+") as file:
        file.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\t{msg}\n")


def verify_config():
    mandatory = [
        # Add more mandatory configs here
        ('stream_ip', SERVER_IP), ('stream_key', STREAM_KEY), ('url', BASE_URL)
    ]

    for name, cmd in mandatory:
        if cmd is None:
            msg = f"[ERROR] Missing config: '{name}'"
            message(msg)
            raise KeyError(msg)


# ======================================================================================================================


def main():
    verify_config()

    q = queue.Queue()

    thread = CallMotherShip(q)
    thread.start()

    while True:
        stream_command = q.get()

        print(f"Got Command: {stream_command}")

        if stream_command.has_cmd():

            # Send Confirmation
            response = requests.post(URL_CLEAR, data={'id': stream_command.cmd_id, 'key': STREAM_KEY})
            stream_command.token = response.json()['token']
            response.close()

            thread.last_action_time = datetime.datetime.now()
            stream_command.run()
            del stream_command


if __name__ == '__main__':
    main()
