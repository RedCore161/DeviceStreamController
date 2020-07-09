import json
import shlex
import subprocess
import threading
import time

import requests

# Loading config
# =====================================

with open('config.json') as f:
    CONFIG = json.load(f)

SERVER_IP = CONFIG["ip"]
STREAM_KEY = CONFIG["stream"]
BASE_URL = CONFIG["url"]

# Setting up parameters
# =====================================

URL = '{}get'.format(BASE_URL)
URL_CLEAR = '{}clear'.format(BASE_URL)
URL_PING = '{}ping'.format(BASE_URL)

SLEEP_TIME = 5
RECORD_TIME = 180

# Known commands
# =====================================

PING = 0
START_PI_CAMERA = 1
STOP_PI_CAMERA = 2
START_WEB_CAMERA = 11
STOP_WEB_CAMERA = 12
PERFORM_UPDATE = 100
RESTART = 200

# =====================================


class StreamCommand(threading.Thread):
    """
    wrapper-class to execute a command in a fire-and-forget thread
    """

    def __init__(self, _cmd=None, _wait=0):
        """

        :param _cmd: command to execute
        :param _wait: wait before another action will start
        """
        self.success = _cmd is not None
        self.cmd = _cmd
        self.wait = _wait
        self.stdout = None
        self.stderr = None
        threading.Thread.__init__(self)

    def run(self):
        if self.cmd is not None:
            p = subprocess.Popen(shlex.split(self.cmd),
                                 shell=False,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

            self.stdout, self.stderr = p.communicate()
        print("Command DONE!", self.cmd)

    def __str__(self):
        return "{},{},{},{}".format(self.success, self.cmd, "", "")


def evaluate_command(cmd) -> StreamCommand:
    if cmd['cmd'] == START_PI_CAMERA:

        # See https://www.raspberrypi.org/forums/viewtopic.php?t=45368
        exe = "raspivid -o - -vf -hf -fps 30 -b 6000000 | ffmpeg -re -ar 44100 " + \
              "-ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero -f h264 -i - " + \
              "-vcodec copy -acodec aac -ab 128k -g 50 -strict experimental -f flv rtmp://{}/app/{}".format(SERVER_IP, STREAM_KEY)
        return StreamCommand(exe, RECORD_TIME)

    elif cmd['cmd'] == STOP_PI_CAMERA:
        exe = 'killall raspivid'
        return StreamCommand(exe, 1)

    elif cmd['cmd'] == START_WEB_CAMERA:
        exe = "ffmpeg -re -f video4linux2 -i /dev/video1 -c:v h264 -c:a aac -f flv rtmp://{}/app/{}".format(SERVER_IP, STREAM_KEY)
        return StreamCommand(exe, RECORD_TIME)

    elif cmd['cmd'] == STOP_WEB_CAMERA:
        exe = 'killall ffmpeg'
        return StreamCommand(exe, 1)

    elif cmd['cmd'] == PERFORM_UPDATE:
        pass
        # todo perform fetch
        # restart

    elif cmd['cmd'] == RESTART:
        pass

    elif cmd['cmd'] == PING:
        pass

    return StreamCommand(None)


def main():

    while True:
        try:
            r = requests.get(URL, params={'key': STREAM_KEY})
            cmds = json.loads(r.content)

            if cmds['success']:
                for cmd in cmds['data']:
                    print("Command: ", cmd)
                    stream_command = evaluate_command(cmd)
                    if stream_command.success:
                        requests.post(URL_CLEAR, data={'id': cmd['id'], 'key': STREAM_KEY})
                        stream_command.start()
            else:
                print("Empty")
                requests.post(URL_PING, data={'key': STREAM_KEY})

        except ConnectionError:
            print("Fehler")
            pass

        time.sleep(SLEEP_TIME)


if __name__ == '__main__':
    main()
