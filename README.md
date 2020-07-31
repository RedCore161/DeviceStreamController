# DeviceStreamController

This is a controller for cameras in general, but specially for raspberry-pies.

In the "config.json"-file you define your CC-Server.

Install needed packages
```
sudo apt install git ffmpeg
```


Use "crontab -e" to add it permanently to your pi-lifecircle:
``` 
@reboot /bin/sh /home/pi/DeviceStreamController/run.sh
```
Also make the file executable:
```
sudo chmod +x /home/pi/DeviceStreamController/run.sh
``` 