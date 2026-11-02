#!/usr/bin/python3
# encoding: utf-8

PI =  3.14159265358979

_A = 0.14  / 2  # meter
_B = 0.135 / 2  # meter
_R = 0.06  / 2  # meter


### Inverse kinematic implementation of X shape four-wheels mecanum chasis  

###   v1 = vy - vx + ω * (a + b) 
###   v2 = vy + vx - ω * (a + b) 
###   v3 = vy - vx - ω * (a + b) 
###   v4 = vy + vx + ω * (a + b) 
def Kin_Inverse(vx, vy, ω):

    v1 = vy - vx + ω * ( _A + _B )
    v2 = vy + vx - ω * ( _A + _B ) 
    v3 = vy - vx - ω * ( _A + _B )
    v4 = vy + vx + ω * ( _A + _B ) 

    return v1, v2, v3, v4


### v to RMP
### rpm = v / 2 / PI / R
def vToRPM(v):
    return v / 2 / PI / _R


if __name__ == '__main__':
    v1, v2, v3, v4 = Kin_Inverse(10,0,0)
    print(v1, v2, v3, v4)
    v1, v2, v3, v4 = Kin_Inverse(0,1,0)
    print(v1, v2, v3, v4)
    v1, v2, v3, v4 = Kin_Inverse(1,1,0)
    print(v1, v2, v3, v4)
    v1, v2, v3, v4 = Kin_Inverse(0,0,1)
    print(v1, v2, v3, v4)
    print(vToRPM(v1),vToRPM(v2),vToRPM(v3),vToRPM(v4))

    # result
    # 1.0 1.0 1.0 1.0
    # -1.0 1.0 -1.0 1.0
    # 0.0 2.0 0.0 2.0
    # 0.1375 -0.1375 -0.1375 0.1375
    # 0.7294601558378545 -0.7294601558378545 -0.7294601558378545 0.7294601558378545

