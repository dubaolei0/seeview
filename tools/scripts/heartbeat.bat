@echo off
REM 知识库心跳通知
REM 把这个 .bat 文件放在方便的位置，然后用 Windows 计划任务定时执行
REM 或者直接双击测试

py -3 "\\192.168.0.165\数学组\_共享文件夹\tools\scripts\heartbeat.py" "\\192.168.0.165\数学组\_共享文件夹"
