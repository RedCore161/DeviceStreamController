import json
import shlex
import subprocess
import threading
import time

import requests

# Loading config
# =====================================
from urllib3 import HTTPConnectionPool

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

SLEEP_TIME = 10
RECORD_TIME = 300

# Known commands
# =====================================

START_PI_CAMERA = 1
STOP_PI_CAMERA = 2

START_WEB_CAMERA = 11
STOP_WEB_CAMERA = 12

PING = 0
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
        self.cmd = _cmd
        self.wait = _wait
        self.stdout = None
        self.stderr = None
        threading.Thread.__init__(self)

    def has_cmd(self):
        return self.cmd is not None

    def run(self):
        if self.cmd is not None:
            p = subprocess.Popen(shlex.split(self.cmd),
                                 shell=False,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

            #self.stdout, self.stderr = p.communicate()
        print("Command DONE!", self.cmd)

    def __str__(self):
        return "{},{},{},{}".format(self.success, self.cmd, "", "")


def evaluate_command(cmd) -> StreamCommand:

    if cmd['cmd'] == START_PI_CAMERA:

        # See https://www.raspberrypi.org/forums/viewtopic.php?t=45368
        exe = "raspivid -n -o - -vf -hf | ffmpeg -re -ar 44100 " + \
              "-ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero -f h264 -i - " + \
              "-vcodec copy -acodec aac -ab 128k -g 50 -strict experimental -f flv rtmp://{}/app/{}".format(SERVER_IP, STREAM_KEY) +\
              " >> /dev/null  &"

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

    elif cmd['cmd'] == PERFORM_UPDATE or cmd['cmd'] == RESTART:
        exe = 'sudo ./updateController.sh'
        return StreamCommand(exe, 1)

    elif cmd['cmd'] == PING:
        pass

    return StreamCommand(None)


def message(file, msg):
    print(msg)
    file.write("{}\t{}\n".format(time.time(), msg))


def main():

    #s = requests.session()
    #s.config['keep_alive'] = False

    with open("boots.txt", "a+") as file:
        message(file, "Booting!")

    while True:
        with open("log.txt", "a+") as file:
            try:

                r = requests.get(URL, params={'key': STREAM_KEY})
                cmds = json.loads(r.content)
                r.close()

                if cmds['success']:
                    for cmd in cmds['data']:

                        message(file, "Command: {}".format(cmd))
                        stream_command = evaluate_command(cmd)

                        if stream_command.has_cmd():
                            # Send Acknowlegment
                            r = requests.post(URL_CLEAR, data={'id': cmd['id'], 'key': STREAM_KEY})
                            r.close()

                            #Start Command-Execution
                            stream_command.start()


                else:
                    message(file, "Empty")
                    r = requests.post(URL_PING, data={'key': STREAM_KEY})
                    r.close()

            except Exception as e:
                message(file, "Error: {}".format(e))

        time.sleep(SLEEP_TIME)


if __name__ == '__main__':
    main()
