import json
import os
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

URL = f'{BASE_URL}get'
URL_CLEAR = f'{BASE_URL}clear'
URL_PING = f'{BASE_URL}ping'
URL_UPLOAD = f'{BASE_URL}upload'

SLEEP_TIME = 30
RECORD_TIME = 300

STILL_NAME = "still.jpg"
SNAP_NAME = "snap.mp4"

# Known commands
# =====================================

START_PI_CAMERA = 1
STOP_PI_CAMERA = 2
SNAPVID_PI_CAMERA = 51
STILL_PI_CAMERA = 52

START_WEB_CAMERA = 11
STOP_WEB_CAMERA = 12

PING = 0
PERFORM_UPDATE = 100


# =====================================


class StreamCommand(threading.Thread):
    """
    wrapper-class to execute a command in a fire-and-forget thread
    """

    def __init__(self, _cmd=None, _wait=0, _upload_file=None):
        """
        :param _cmd: command to execute
        :param _wait: wait before another action will start
        """
        self.cmd = _cmd
        self.wait = _wait
        self.upload_file = _upload_file
        self.stdout = None
        self.stderr = None
        self.token = None
        threading.Thread.__init__(self)

    def has_cmd(self):
        return self.cmd is not None

    def run(self):
        if self.cmd is not None:
            last = None
            for cmd in self.cmd.split("|"):
                last = run_process(cmd, last)

            print("Waiting..", self.wait)
            time.sleep(self.wait+4)
            print("Command DONE!", self.cmd)

            if self.upload_file:
                print("Starting Upload!")
                tries = 10
                while not os.path.exists(self.upload_file) and tries > 0:
                    print("Waiting for file creation...")
                    time.sleep(1)
                    tries -= 1

                if os.path.exists(self.upload_file):
                    tries = 10
                    while os.path.getsize(self.upload_file) < 100 and tries > 0:
                        print("Waiting for file writting done")
                        time.sleep(1)
                        tries -= 1

                    time.sleep(10)

                    if tries > 0:
                        requests.post(URL_UPLOAD,
                                      files={'file': open(self.upload_file, 'rb')},
                                      data={"token": self.token, "key": STREAM_KEY, "filesize": os.path.getsize(self.upload_file)}
                                      )
                        #os.remove(self.upload_file)
                        print("Upload Done!")

    def __str__(self):
        return "{},{},{}".format(self.cmd, "", "")


def run_process(cmd, last_pro):
    if last_pro is None:
        p = subprocess.Popen(shlex.split(cmd),
                             shell=False,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    else:
        p = subprocess.Popen(shlex.split(cmd),
                             shell=False,
                             stdin=last_pro.stdout,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    return p


def evaluate_command(cmd, params=None) -> StreamCommand:
    if cmd['cmd'] == START_PI_CAMERA:

        # See https://www.raspberrypi.org/forums/viewtopic.php?t=45368
        exe = "raspivid -n -t 0 -o - -vf -hf | ffmpeg -re -ar 44100 " + \
              "-ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero -f h264 -i - " + \
              "-vcodec copy -acodec aac -ab 128k -g 50 -strict experimental -f flv rtmp://{}/app/{}".format(SERVER_IP,
                                                                                                            STREAM_KEY)

        return StreamCommand(exe, RECORD_TIME)

    elif cmd['cmd'] == STOP_PI_CAMERA:
        exe = 'killall raspivid'
        return StreamCommand(exe, 1)

    elif cmd['cmd'] == SNAPVID_PI_CAMERA:
        t = 8
        _t = t * 1000
        w, h = 1600, 900
        w, h = 1280, 720
        '''
        exe = f"raspivid -n -t {_t} -o - -vf -hf -w {w} -h {h} -fps 25 -p 0,0,{w},{h} | ffmpeg -re -ar 44100 -y " + \
              f"-ac 2 -acodec pcm_s16le -f s16le -ac 2 -i /dev/zero -f h264 -i pipe:0 -c:v libx264 {SNAP_NAME}"
        '''

        exe = f'raspivid -n -t {_t} -o - -vf -hf -w {w} -h {h} -fps 16 -p 0,0,{w},{h} | ' \
              f'ffmpeg -i pipe:0 -y -c:v libx264 {SNAP_NAME}'

        return StreamCommand(exe, _wait=t, _upload_file=SNAP_NAME)

    elif cmd['cmd'] == STILL_PI_CAMERA:
        print("STILL", params)
        exe = f'raspistill -vf -hf -o {STILL_NAME}'
        return StreamCommand(exe, _wait=10, _upload_file=STILL_NAME)

    elif cmd['cmd'] == START_WEB_CAMERA:
        exe = "ffmpeg -re -f video4linux2 -i /dev/video1 -c:v h264 -c:a aac -f flv rtmp://{}/app/{}".format(SERVER_IP,
                                                                                                            STREAM_KEY)
        return StreamCommand(exe, RECORD_TIME)

    elif cmd['cmd'] == STOP_WEB_CAMERA:
        exe = 'killall ffmpeg'
        return StreamCommand(exe, 1)

    elif cmd['cmd'] == PERFORM_UPDATE:
        exe = 'sudo ./updateController.sh'
        return StreamCommand(exe, 1)

    elif cmd['cmd'] == PING:
        pass

    return StreamCommand(None)


def message(file, msg):
    print(msg)
    file.write("{}\t{}\n".format(time.time(), msg))


def main():
    # s = requests.session()
    # s.config['keep_alive'] = False

    with open("boots.txt", "a+") as file:
        message(file, "Booting!")

    while True:
        with open("log.txt", "a+") as file:
            try:

                response = requests.get(URL, params={'key': STREAM_KEY})
                cmds = response.json()
                response.close()

                if cmds['success']:
                    for cmd in cmds['data']:

                        message(file, "Command: {}".format(cmd))
                        stream_command = evaluate_command(cmd)  # cmds['params']

                        if stream_command.has_cmd():
                            # Send Acknowlegment
                            response = requests.post(URL_CLEAR, data={'id': cmd['id'], 'key': STREAM_KEY})
                            stream_command.token = response.json()['token']
                            response.close()

                            # Start Command-Execution
                            stream_command.start()

                else:
                    message(file, "Empty")
                    # r = requests.post(URL_PING, data={'key': STREAM_KEY})
                    # r.close()

            except Exception as e:
                message(file, "Error: {}".format(e))

        time.sleep(SLEEP_TIME)


if __name__ == '__main__':
    main()
