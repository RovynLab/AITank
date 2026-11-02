#!/usr/bin/python3
# encoding: utf-8

import RPi.GPIO as GPIO                 # 引入GPIO模块

if __name__ == '__main__':
    ServoPin = 26
    PWMFreq = 50                        # PWM信号频率

    GPIO.setmode(GPIO.BCM)              # 使用BCM编号方式
    GPIO.setup(ServoPin, GPIO.OUT)      # 将GPIO19设置为输出模式
    pwm = GPIO.PWM(ServoPin, PWMFreq)   # 创建PWM对象，并设置频率为50
    pwm.start(0)                        # 启动PWM，并设置初始占空比0

    try:
        while True:
            # 等待输入一个0到180的角度, -1 退出
            raw = input("Pleas input the direction (-1 to quit): ")
            direction = float(raw)
            if direction == -1:
                break
            if 0 <= direction <= 180:
                duty = (1/18) * direction + 2.5   # 将角度转换为占空比
                pwm.ChangeDutyCycle(duty)         # 改变PWM占空比
            else:
                print("请输入 0-180 之间的角度 (或 -1 退出)")
    finally:
        pwm.stop()                      # 停止PWM
        GPIO.cleanup()                  # 清理释放GPIO资源，将GPIO复位