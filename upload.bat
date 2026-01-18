@echo off
scp -r "D:\Typheye\Code\tcar\raspi-z2w\gui" pi@192.168.66.2:/home/pi/

@REM scp -r "D:\Typheye\Code\tcar\raspi-z2w\gui\ui" pi@192.168.66.2:/home/pi/gui

ssh pi@192.168.66.2 "sudo systemctl stop gui-app.service && sudo systemctl start gui-app.service"


:: scp -r "D:\Typheye\Code\tcar\raspi-4b\TurboPi\Utils" pi@192.168.66.5:/home/pi/TurboPi/
:: scp -r "D:\Typheye\Code\tcar\raspi-4b\TurboPi\Functions" pi@192.168.66.3:/home/pi/TurboPi/
:: scp -r "D:\Typheye\Code\tcar\raspi-4b\TurboPi\TurboPi.py" pi@192.168.66.3:/home/pi/TurboPi/
:: scp -r "D:\Typheye\Code\tcar\raspi-4b\TurboPi\MjpgServer.py" pi@192.168.66.3:/home/pi/TurboPi/
:: ssh pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/HiwonderSDK/pyz_opera.py --servo 1 --step 50"
:: ssh pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/Utils/battery.py"
:: sudo journalctl -u gui-app.service -f