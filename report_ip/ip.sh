#/bin/bash

source_path = /home/pi/ip_report        # 开机脚本存放路径

sleep 15            # 延时等待系统开机并联网完成

cd $source_path

uname -n > ip.txt

echo "\r\n"

ifconfig >> ip.txt

python3 autoemail.py

