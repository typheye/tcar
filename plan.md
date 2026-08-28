很好，现在回到4b
我发现磁力计校准后貌似就偷懒了，也没有同步位置，Vision视图一直是灰色扇形，修复它；
C:\Code\tcar\raspi-4b\TurboPi\Utils\mpu6050.py和C:\Code\tcar\raspi-4b\TurboPi\Utils\smpu.py都要用吗，这个文件名当时起的不好，应该按功能拆分成magnetometer.py，和mpu.py

其实我更建议抛弃旧的TurboPi（create_ap  hiwonder-toolbox  LAB_Tool 和TuboPi是原厂提供的示例代码，现在改的很乱了，况且我们也有基础了，完全可以独立）创建个C:\Code\tcar\raspi-4b\tCarCore\

init.py（总启动，初始化硬件等）

hardware\（明确按驱动分类啥的放进去）
mpu6050_quaternion.bin（陀螺仪四元数驱动）
mpu6050.py（陀螺仪驱动）
qmc5883l.py（磁力计驱动）
主板驱动应当拆散（C:\Code\tcar\raspi-4b\TurboPi\HiwonderSDK\Board.py对应接口放对应模块）：
buzzer.py（蜂鸣器驱动）
fourInfrared.py（四路巡线传感器）
servo.py（舵机驱动，最好提供接口查询当前位置，单例模式防止互串）
motor.py（运动电机驱动）
board_rgb.py（板载rgb驱动）
board_key.py（板载按键驱动，扩展版有两个板载按键,见C:\Code\tcar\raspi-4b\hiwonder-toolbox\hw_button_scan.py）
sonar.py（超声波驱动，包含其LED控制）
ps_controler.py（手柄驱动）
asr.py（一体语音交互模块驱动）
video_device.py（视频设备驱动，如相机驱动）
battery_monitor.py（电池检测驱动）

media/
servo_config.yaml（舵机出厂校准值，只读）

server/ - 服务类
server/rpc/ 文件夹-提供给机载设备的远程函数，你们直接提供网线连接
server/core/ 文件夹-核心服务，小车运动实现，日志系统等
server/api/文件夹，开放给其他平台（如win-pc）的api服务，全面了解、控制设备信息

建议所有示例文件哪怕是新线程都和init.py绑定，同生共灭；
还要我不想见到类似__init__.py这种类似文件，不要创建；
希望重新创建tcar-core.service（tCar Core Service），开机自动执行~/tCarCore/init.py（conda环境:tcar-core_env，我已创建）
原有的TurboPi暂时不要删除，先保留；

先修复磁力计，然后理一下迁移思路，我确认后你再修改