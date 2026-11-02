# -*- coding: utf-8 -*-
#!/usr/bin/python

import sys,os
#BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # __file__获取执行文件相对路径，整行为取上一级的上一级目录
#sys.path.append(BASE_DIR)

from flask import Flask, render_template, Response
import cv2
#from cv2 import cv2
import sys
#sys.path.append('./../')
import PTZControl as PTZ
import MecanumChasis as Mecan

class VideoCamera(object):
    def __init__(self):
        # 通过opencv获取实时视频流
        self.video = cv2.VideoCapture(0) 
    
    def __del__(self):
        self.video.release()
    
    def get_frame(self):
        success, image = self.video.read()
        # 因为opencv读取的图片并非jpeg格式，因此要用motion JPEG模式需要先将图片转码成jpg格式图片
        ret, jpeg = cv2.imencode('.jpg', image)
        return jpeg.tobytes()

app = Flask(__name__)

@app.route('/')  # 主页
def index():    # jinja2模板，具体格式保存在index.html文件中
    return render_template('index.html')

def gen(camera):
    while True:
        frame = camera.get_frame()
        # 使用generator函数输出视频流， 每次请求输出的content类型是image/jpeg
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

@app.route('/video_feed')  # 这个地址返回视频流响应
def video_feed():
    return Response(gen(VideoCamera()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')   


@app.route('/ptz/<motion>') #当前端发送的请求为/ptz/<motion>的形式时
def ptz_ctrl(motion):
    # 动作函数    
    print (motion,flush=True)
    
    if motion=="right":
        PTZ.HorIncrease(5)

    if motion=="left":
        PTZ.HorIncrease(-5)
    
    if motion=="top":
        PTZ.VerIncrease(-5)

    if motion=="buttom":
        PTZ.VerIncrease(5)


    return motion 

@app.route('/base/<motion>')#当前端发送的请求为/base/<motion>的形式时
def base_ctrl(motion):
    # 动作函数

    print(motion,flush=True)

    if motion == "b-topleft":        
        Mecan.forwardLeft()
    if motion == "b-top":
        Mecan.forward()
    if motion == "b-topright":
        Mecan.forwardRight()
    if motion == "b-left":
        Mecan.leftSlide()
    if motion == "b-right":
        Mecan.rightSlide()
    if motion == "b-stop":
        Mecan.stop()
    if motion == "b-btm":
        Mecan.backward()
    if motion == "b-btmright":
        Mecan.backwardRight()
    if motion == "b-btmleft":
        Mecan.backwardLeft()  
    if motion == "b-turnright":
        Mecan.turnRight()
    if motion == "b-turnleft":
        Mecan.turnLeft()  
          


    return motion


if __name__ == '__main__':
    
    PTZ.PTZInit()
    
    # --- P0 修复: 进程退出时释放电机 + Flask 关掉 debug 避免 I2C 被 reloader 抢占 ---
    import atexit
    atexit.register(Mecan.turnOffMotors)
    
    app.run(host='0.0.0.0', debug=False, threaded=True, port=5000)

