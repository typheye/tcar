import time
import HiwonderSDK.Board as Board


def init(timer=0.08):
    Board.setBuzzer(0)
    Board.setBuzzer(1)
    time.sleep(timer)
    Board.setBuzzer(0)

def keydown_PSControler():
    Board.setBuzzer(0)
    Board.setBuzzer(1)
    time.sleep(0.01)
    Board.setBuzzer(0)

def keydown_combination_PSControler():
    Board.setBuzzer(0)
    Board.setBuzzer(1)
    time.sleep(0.05)
    Board.setBuzzer(0)
