#!/usr/bin/python3
# coding=utf8
# 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偞鐗犻、鏇㈡晝閳ь剛澹曢崷顓犵＜閻庯綆鍋撶槐鈺傜箾瀹割喕绨奸柡鍛叀閺屾稑鈽夐崣妯煎嚬闂佽楠搁…宄邦潖濞差亝顥堟繛鎴炴皑閻ゅ嫰姊虹粙鍖℃敾婵炲弶绮撻獮? smpus_win.py

import sys
import socket
import struct
import math
import time
import urllib.request
import urllib.error
import threading
from collections import deque
from pathlib import Path
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *


# ============ UDP============
class UDPReceiver(QThread):
    data_received = pyqtSignal(list)
    connection_status = pyqtSignal(bool)
    calibration_status = pyqtSignal(str)
    battery_status = pyqtSignal(float, float)
    network_delay = pyqtSignal(float)
    
    def __init__(self, ip='192.168.66.3', port=8888):
        super().__init__()
        self.ip = ip
        self.port = port
        self.running = True
        self.active = True
        self.connected = False
        self.sock = None
        self.last_calibration_status = None
        self.last_calibration_poll = 0.0

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.5)
            print(f"Connecting server: {self.ip}:{self.port}")
            
            while self.running:
                if not self.active:
                    self.msleep(100)
                    continue
                try:
                    request_started = time.monotonic()
                    self.sock.sendto(b'get_data', (self.ip, self.port))
                    try:
                        data, addr = self.sock.recvfrom(1024)
                        self.network_delay.emit((time.monotonic() - request_started) * 1000.0)
                        if len(data) == 68:
                            values = list(struct.unpack('!17f', data))
                            self.data_received.emit(values)
                            if not self.connected:
                                self.connected = True
                                self.connection_status.emit(True)
                                print("Connected")
                        elif len(data) == 64:
                            values = list(struct.unpack('!16f', data))
                            self.data_received.emit(values)
                            if not self.connected:
                                self.connected = True
                                self.connection_status.emit(True)
                                print("Connected")
                        elif len(data) == 60:
                            values = list(struct.unpack('!15f', data))
                            self.data_received.emit(values)
                            if not self.connected:
                                self.connected = True
                                self.connection_status.emit(True)
                                print("Connected")
                        elif len(data) == 56:
                            values = list(struct.unpack('!14f', data))
                            self.data_received.emit(values)
                            if not self.connected:
                                self.connected = True
                                self.connection_status.emit(True)
                                print("Connected")
                        elif len(data) == 40:
                            values = list(struct.unpack('!10f', data))
                            self.data_received.emit(values)
                            if not self.connected:
                                self.connected = True
                                self.connection_status.emit(True)
                                print("Connected")
                        now = time.monotonic()
                        if now - self.last_calibration_poll >= 0.25:
                            self.last_calibration_poll = now
                            self.sock.sendto(b'calibration_status', (self.ip, self.port))
                            try:
                                status_data, _ = self.sock.recvfrom(256)
                                status = status_data.decode('utf-8', errors='replace')
                                if status != self.last_calibration_status:
                                    self.last_calibration_status = status
                                    self.calibration_status.emit(status)
                            except (socket.timeout, UnicodeDecodeError):
                                pass
                            self.sock.sendto(b'battery_status', (self.ip, self.port))
                            try:
                                battery_data, _ = self.sock.recvfrom(256)
                                voltage_text, percent_text = battery_data.decode().split(',', 1)
                                self.battery_status.emit(float(voltage_text), float(percent_text))
                            except (socket.timeout, UnicodeDecodeError, ValueError):
                                pass
                        self.msleep(20)
                    except socket.timeout:
                        if self.connected:
                            self.connected = False
                            self.connection_status.emit(False)
                except socket.error:
                    time.sleep(1)
        except Exception as e:
            print(f"闂傚倸鍊搁崐鎼佸磹閹间礁纾归柣鎴ｅГ閸婂潡鏌ㄩ弮鍫熸殰闁稿鎸剧划顓炩槈濡顦╅梺绋款儜缁绘繈寮婚弴鐔虹闁绘劦鍓氶悵锕傛⒑? {e}")
        finally:
            if self.sock:
                self.sock.close()

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()

    def set_active(self, active):
        self.active = bool(active)


class CameraReceiver(QThread):
    frame_received = pyqtSignal(QImage)
    connection_status = pyqtSignal(bool)

    def __init__(self, url="http://192.168.66.3:8080/?action=stream", max_fps=15,
                 latest_only=False):
        super().__init__()
        self.url = url
        self.max_fps = max_fps
        self.running = True
        self.active = True
        self.connected = False
        self.latest_only = latest_only
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._latest_sequence = 0
        self._latest_delay_ms = 0.0

    def _set_connected(self, connected):
        if self.connected != connected:
            self.connected = connected
            self.connection_status.emit(connected)

    def run(self):
        frame_interval = 1.0 / max(1, self.max_fps)
        while self.running:
            if not self.active:
                self._set_connected(False)
                self.msleep(100)
                continue
            try:
                request = urllib.request.Request(
                    self.url,
                    headers={
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                        "Connection": "close",
                        "User-Agent": "tCarKit/1.0",
                    },
                )
                with urllib.request.urlopen(request, timeout=1.5) as response:
                    buffer = bytearray()
                    last_emit = 0.0
                    frame_started = time.monotonic()
                    pending_frame_timestamp = None
                    pending_server_sequence = None
                    last_server_sequence = None
                    clock_offset_s = None
                    while self.running and self.active:
                        read_chunk = getattr(response, "read1", response.read)
                        chunk = read_chunk(32768)
                        if not chunk:
                            break
                        buffer.extend(chunk)

                        while self.running and self.active:
                            start = buffer.find(b'\xff\xd8')
                            if start < 0:
                                if len(buffer) > 65536:
                                    del buffer[:-2]
                                break
                            if start:
                                header = bytes(buffer[:start])
                                marker = b'X-Frame-Time: '
                                timestamp_start = header.rfind(marker)
                                if timestamp_start >= 0:
                                    timestamp_start += len(marker)
                                    timestamp_end = header.find(b'\r\n', timestamp_start)
                                    try:
                                        pending_frame_timestamp = float(
                                            header[timestamp_start:timestamp_end]
                                        )
                                    except (TypeError, ValueError):
                                        pending_frame_timestamp = None
                                sequence_marker = b'X-Frame-Sequence: '
                                sequence_start = header.rfind(sequence_marker)
                                if sequence_start >= 0:
                                    sequence_start += len(sequence_marker)
                                    sequence_end = header.find(b'\r\n', sequence_start)
                                    try:
                                        pending_server_sequence = int(
                                            header[sequence_start:sequence_end]
                                        )
                                    except (TypeError, ValueError):
                                        pending_server_sequence = None
                                del buffer[:start]
                                frame_started = time.monotonic()
                            end = buffer.find(b'\xff\xd9', 2)
                            if end < 0:
                                break

                            jpg = bytes(buffer[:end + 2])
                            del buffer[:end + 2]
                            now = time.monotonic()
                            if (pending_server_sequence is not None and
                                    pending_server_sequence == last_server_sequence):
                                continue
                            if now - last_emit < frame_interval:
                                continue
                            image = QImage.fromData(jpg, "JPG")
                            if not image.isNull():
                                self._set_connected(True)
                                if self.latest_only:
                                    with self._frame_lock:
                                        self._latest_frame = image
                                        self._latest_sequence += 1
                                        if pending_frame_timestamp is not None:
                                            observed_offset = time.time() - pending_frame_timestamp
                                            if (clock_offset_s is None or
                                                    observed_offset < clock_offset_s):
                                                clock_offset_s = observed_offset
                                            self._latest_delay_ms = max(
                                                0.0,
                                                (observed_offset - clock_offset_s) * 1000.0,
                                            )
                                        else:
                                            self._latest_delay_ms = (
                                                time.monotonic() - frame_started
                                            ) * 1000.0
                                else:
                                    self.frame_received.emit(image)
                                last_emit = now
                                last_server_sequence = pending_server_sequence
                            frame_started = time.monotonic()
                            pending_frame_timestamp = None
                            pending_server_sequence = None
                        if len(buffer) > 512 * 1024:
                            buffer.clear()
            except (OSError, ValueError, urllib.error.URLError):
                self._set_connected(False)
                self.msleep(250)

        self._set_connected(False)

    def take_latest_frame(self, after_sequence=0):
        with self._frame_lock:
            if self._latest_sequence <= after_sequence or self._latest_frame is None:
                return None
            return self._latest_sequence, self._latest_frame, self._latest_delay_ms

    def stop(self):
        self.running = False

    def set_active(self, active):
        self.active = bool(active)


# ============ OpenGL 缂傚倸鍊搁崐鎼佸磹閹间礁纾归柣鎴ｅГ閸婂潡鏌ㄩ弴鐐测偓鍫曞焵椤掆偓閸熷磭绮诲☉妯锋婵☆垳鈷堝Σ顖涚節閻㈤潧浠﹂柛銊ㄦ硾椤繈濡歌娑撳秹鏌￠崒娑崇穿鐟滅増甯楅弲鏌ユ煕濞戝崬鏋︾痪顓涘亾濠碉紕鍋戦崐鎰板疾濠婂牊鍋傞柨鐔哄Т閽冪喓鎲搁幋鐘典笉婵炴垯鍨圭粻濠氭煛閸屾ê鍔氱憸鐗堝哺濮婄粯鎷呴搹鐟扮闂佸憡姊瑰ú鐔煎箖濡警娼╅悹楦挎閻涖儵姊虹化鏇炲⒉缂佸甯￠幃锟犲即閵忥紕鍘撻梺瀹犳〃缁€渚€寮搁妶鍡欑闁割偆鍠愮粈鍫㈢磼?============
class ThirdPersonView(QGLWidget):
    VEHICLE_MODEL_SIZE = 2.2

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 缂傚倸鍊搁崐鎼佸磹閹间礁纾归柣鎴ｅГ閸婂潡鏌ㄩ弴鐐测偓鎼佹嫅閻斿吋鐓忓┑鐐靛亾濞呮捇鏌℃担绋款伃闁哄本鐩崺鍕礃椤忎焦顫嶉梻浣芥閸熶即宕伴弽顓炶摕闁挎繂顦Λ姗€鏌熺粙鍧楊€楅柡鍡楃墛缁绘繂鈻撻崹顔句画闂佺懓鎲℃繛濠傤嚕婵犳碍鍋勯柣鎾虫捣椤斿姊鸿ぐ鎺戜喊闁告挻绋戣闁靛繈鍨荤壕钘壝归敐鍛棌婵℃彃鎲￠妵鍕即閵娿儱绠诲┑?(闂傚倸鍊搁崐鎼佸磹閻戣姤鍊块柨鏇炲€哥粻鏍煕椤愶絾绀€缁炬儳娼″娲敆閳ь剛绮旂€靛摜涓嶉悷娆忓娴滄粓鏌熼弶璺ㄥ煟婵＄虎鍣ｉ弻?
        self.cube_x = 0.0
        self.cube_y = 0.0
        self.cube_z = 0.0
        
        # 缂傚倸鍊搁崐鎼佸磹閹间礁纾归柣鎴ｅГ閸婂潡鏌ㄩ弴鐐测偓鎼佹嫅閻斿吋鐓忓┑鐐靛亾濞呮捇鏌℃担绋款伃闁哄本鐩崺鍕礃椤忎焦顫嶉梻浣芥閸熶即宕伴弽顓炶摕闁挎繂顦Λ姗€鏌熺粙鍧楊€楅柡鍡楃墛缁绘繂鈻撻崹顔句画闂佺懓鎲℃繛濠傤嚕婵犳碍鍋勯柛蹇曞帶閳ь剟鏀遍妵鍕箳閸℃ぞ澹曟俊鐐€戦崕鎶藉磻閻愬搫桅闁告洦鍨扮粻濠氭煕濡ゅ啫浠уù鐘哄亹缁?(闂傚倸鍊搁崐鎼佸磹閻戣姤鍊块柨鏇炲€归崕鎴犳喐閻楀牆绗掗柛銊ュ€块幃褰掑炊椤忓秵鈷栭梺鍛婄箓鐎氱兘鎮￠崼鏇熺厱?050闂傚倸鍊搁崐鎼佸磹閻戣姤鍤勯柛顐ｆ磸閳ь兛鐒︾换婵嬪炊閵娿儱澹掗梻浣规偠閸庢椽宕滃▎鎴犵焼闁告劦鍠楅悡蹇撯攽閻愭垵鍟弳娆戠磼?
        self.cube_yaw = 0.0
        self.cube_pitch = 0.0
        self.cube_roll = 0.0
        
        self.target_cube_yaw = 0.0
        self.target_cube_pitch = 0.0
        self.target_cube_roll = 0.0
        self.cube_quat = [1.0, 0.0, 0.0, 0.0]
        self.target_cube_quat = [1.0, 0.0, 0.0, 0.0]
        self.has_quaternion = False
        
        # 闂傚倸鍊搁崐宄懊归崶顒夋晪鐟滃繘鍩€椤掍胶鈻撻柡鍛箘閸掓帒鈻庨幘宕囶唺濠德板€撻悞锕€鈻嶉弮鍫熲拻闁稿本鐟ㄩ崗灞俱亜椤撶偟澧︽い銏＄墵瀹曘劑顢涘鍛帬闂備浇宕甸崰鎰珶閸℃稑姹查柨鏃傛櫕缁♀偓闂傚倸鐗婃笟妤呭磿閹扮増鐓曢悗锝庡亜婵秹鏌″畝瀣М妤犵偛顑夊顕€鍩€椤掆偓閳诲秹宕ㄩ鑲╂嚀椤劑宕奸姀銏℃瘒闂備礁鎼惌澶岀礊娴ｅ壊鍤曟い鎺戝閸ㄥ倹銇勯弬鍨缓闁宠桨绶″〒濠氭煏閸繃顥為柣鎾卞劦閺屻劑寮撮妸銈夊仐閻庢鍠涢褔鍩ユ径濠庢建闁糕剝鐟ュ鎶芥⒒娴ｅ憡鍟為柛鏃撻檮缁傚秹鎮欓崫鍕槷濡炪倖姊婚埛鍫濄€掓繝姘厪闁割偅绻堥妤€霉濠婂嫮绠栭柕鍥у婵℃悂濡烽敂缁橈紗婵°倗濮烽崑娑樜涘┑鍡╁殨妞ゆ洍鍋撶€规洖銈搁幃銏ゅ川婵犲嫬绲鹃梻鍌氬€风粈渚€宕ョ€ｎ偆顩插ù鐘差儏绾惧潡鏌＄仦璇插姶闁轰礁锕﹂埀顒€绠嶉崕閬嵥囨导鏉戠厱?(闂傚倸鍊搁崐鎼佸磹閻戣姤鍊块柨鏇楀亾妞ゎ亜鍟村畷褰掝敋閸涱垰濮洪梻浣侯潒閸曞灚鐣剁紓浣插亾濠㈣埖鍔栭崐鐢告煥濠靛棝顎楀褎褰冮埞鎴︻敊閹稿海褰ч梺闈涙搐鐎氫即鐛幒妤€绠ｆ繝鍨姃閹綁姊绘担鍛婂暈闁荤喆鍎甸弫鍐敂閸繆鎽曞┑鐐村灟閸ㄥ湱绮荤紒妯圭箚闁绘劙娼ф禍鐐亜閿曞偆妫戠紒?
        self.ax = 0.0
        self.ay = 0.0
        self.az = 0.0
        self.mag_yaw = float("nan")
        self.pitch = 0.0
        self.roll = 0.0
        self.yaw = 0.0
        
        # 闂傚倸鍊搁崐鎼佸磹閻戣姤鍤勯柛顐ｆ磸閳ь兛鐒︾换婵嬪磻閼恒儳娲寸€规洜鍠栭、妯衡槈濡懓顥氭繝娈垮枟椤洭宕㈣閺呭墎鈧數纭堕崑鎾舵喆閸曨剛顦ㄥ┑鐐插级閻楃娀鏁愰悙娴嬫斀闁割偆鍠庣壕顖炴⒑閸涘﹦绠撻悗姘煎枦閵囨劖寰勬繛鐐杸闁圭儤濞婂畷鎰樄婵﹣绮欏畷鐔碱敍閿濆棙娅堟繝鐢靛仜濡霉濮樿埖鍊垮ù鐘差儐閻撱儵鏌ｉ弬鎸庢儓鐎涙繄绱?(濠电姷鏁告慨鐢割敊閺嶎厼绐楁俊銈傚亾闁伙絿鍏樺畷绋课旈埀顒€顔忓┑鍥ヤ簻闁圭偓鍓氬褏绱撳鍕獢鐎殿喖顭烽弫鎰緞婵犲倸鏁ら梻浣圭湽閸ㄥ寮灞稿徍婵犲痉鏉库偓妤佹叏閻戣棄纾婚柣鎰仛閺嗘粓鏌ｉ弬娆炬祲闁搞儺鍓欓拑鐔兼煏婢舵稑顩柛?
        self.cam_yaw = 45.0
        self.cam_pitch = 30.0
        self.cam_distance = 8.0
        
        # 濠电姷鏁告慨鐢割敊閺嶎厼绐楁俊銈傚亾闁伙絿鍏樺畷绋课旈埀顒€顔忓┑鍥ヤ簻闁圭偓鍓氬褏绱撳鍕獢鐎殿喖顭烽弫鎰緞婵犲倸鏁ら梻浣圭湽閸ㄥ寮灞稿徍婵犲痉鏉库偓妤佹叏閻戣棄纾绘繛鎴炵瀹曞弶淇婇娆掝劅闁搞倖娲熼弻娑欑節閸曨偅鐝″┑鈩冨絻椤兘骞?
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.is_dragging = False
        
        # 闂傚倸鍊搁崐鐑芥倿閿曞倹鍎戠憸鐗堝笒閺勩儵鏌涢弴銊ョ仩闁搞劌鍊块獮鏍庨鈧俊鑲┾偓鐟版啞缁诲啴濡甸崟顖氱妞ゆ牗顨呮禍楣冩煙?
        self.frame_count = 0
        self.last_fps_update = time.time()
        self.current_fps = 0
        self.clear_color = (0.1176, 0.1176, 0.1176, 1.0)
        self.vehicle_color = (0.64, 0.66, 0.70)
        (
            self.vehicle_triangles,
            self.vehicle_feature_edges,
            self.vehicle_front_z,
        ) = self._load_vehicle_mesh()
        self.vehicle_display_list = None
        self.vehicle_edge_display_list = None
        
        self.setMinimumSize(800, 600)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        
        # 60fps
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def set_cube_angles(self, yaw, pitch, roll):
        """Set cube attitude from Euler fallback angles."""
        # Yaw: 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偛顦甸弫鎾绘偐閸愯弓鐢婚梻浣瑰濞叉牠宕愯ぐ鎺戠；閻庯綆鍠楅悡娑㈡煕閵夈垺娅呴柛鎾讳憾閺?(PC缂傚倸鍊搁崐鎼佸磹閹间礁纾归柣鎴ｅГ閸婂潡鏌ㄩ弴妤€浜鹃柧鑽ゅ仱閻擃偊宕堕妸褉妲堥梺鎼炲妼閸婂綊濡甸崟顖氬唨闁靛ě鍛帓缂傚倷鑳舵慨鐢稿蓟閵娾斁鈧箓宕稿Δ浣告疂闂傚倸鐗婄粙鎴︼綖瀹€鈧槐鎺楀箚瑜嶉埛鏃傜磼椤曞懎鐏︽鐐茬墦婵℃悂濡锋惔锝呮瀾鐎垫澘瀚划娆撳箰鎼粹€冲缂傚倸鍊搁崐宄懊归崶銊ｄ粓缂佸娉曢弳鍡涙煙闂傚顦﹂柦鍐枛閺屻劑鎮㈤崫鍕戙垽鏌?
        self.target_cube_yaw = yaw
        # 濠电姷鏁告慨鐑藉极閹间礁纾绘繛鎴欏灪閸嬨倝鏌曟繛鐐珔闁告艾缍婇獮鏍庨鈧俊鑲╃棯閹呯Ш闁哄备鈧磭鏆ゆい鏂垮悑閸ｇ儤绻涢崼銉х暫婵﹤鎼叅閻犲洩寮撶花浠嬫⒑闂堟稒澶勯柟鍓叉h闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偛顦甸弫宥夊礋椤愩垻浜伴柣搴″帨閸嬫捇鏌涢弴鐐典粵闁哄懌鍨藉铏光偓鍦У椤忕娀鎮介婊呪攳
        # Pitch闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偞鐗犻、鏇㈡晝閳ь剛澹曢悷鎵虫斀闁绘ê鐤囨竟妯肩磼閻橀潧鈻堥柡宀€鍠栭獮鎴﹀箛闂堟稒顔勭紓鍌欒兌婵敻鎮уΔ鍐╁床婵犻潧娲ㄧ弧鈧梺绋挎湰缁矂銆傚ú顏呪拺婵炶尪顕ч獮妤併亜閵娿儻韬€殿喖顭烽崹鎯х暦閸ャ劍顔撴俊鐐€栧濠氬储瑜斿鍐测枎閹惧鍘?(濠电姷鏁告慨鐑藉极閹间礁纾块柟瀵稿Т缁躲倝鏌﹀Ο渚＆鐟滅増甯掔壕濂告煟閹邦垰鐨洪柣娑栧劦濮婃椽宕崟顓涙瀱闂佸憡蓱濡啫鐣烽崼鏇ㄦ晢闁逞屽墴閹锋垿鎮㈤崗鑲╁帾婵犮垼娉涢悧鍡涘礉濠婂嫨浜滈柕澶涘缁犵偞鎱ㄦ繝鍐┿仢闁圭绻濇俊鍫曞川椤斿彞绨存繝鐢靛Л閹峰啴宕熼崹顐ゆ澒闁诲氦顫夊ú姗€宕濋弽顐ｅ床婵犻潧妫鈺傘亜閹捐泛孝妤犵偛鐗婄换婵嬫偨闂堟稐绮跺┑鈽嗗亝椤ㄥ牓骞戦姀銈呯闁瑰濮甸惁鎾剁磽閸屾艾鈧悂宕愭搴㈩偨闁跨喓濮甸崑鍌氼熆鐠虹儤婀扮€规洖寮剁换婵嬫濞戝崬鍓扮紓浣哄У瀹€鎼佸蓟濞戙垹绠涢梻鍫熺⊕閻忓牏绱撴担鎻掍壕闁诲函缍嗛崑浣圭濠婂牊鐓涚€广儱鍟俊濂告煕閻樿櫕绀堢紒杈ㄥ笚椤垿寮介敂鎯у毈濠?
        self.target_cube_pitch = pitch
        self.target_cube_roll = roll

    def set_dark_theme(self, dark):
        value = 30.0 / 255.0 if dark else 0.94
        self.clear_color = (value, value, value, 1.0)
        self.vehicle_color = (
            (0.64, 0.66, 0.70) if dark else (0.38, 0.40, 0.44)
        )
        if self.isValid():
            self.makeCurrent()
            glClearColor(*self.clear_color)
            self.doneCurrent()
        self.update()

    def set_cube_quaternion(self, qw, qx, qy, qz):
        norm = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
        if norm <= 0.0:
            return
        # 4B publishes the quaternion in tCar's standard vehicle axes.
        self.target_cube_quat = [qw / norm, qx / norm, qy / norm, qz / norm]
        self.has_quaternion = True

    def _slerp_quat(self, a, b, t):
        dot = sum(a[i] * b[i] for i in range(4))
        if dot < 0.0:
            b = [-v for v in b]
            dot = -dot
        if dot > 0.9995:
            q = [a[i] + (b[i] - a[i]) * t for i in range(4)]
            norm = math.sqrt(sum(v * v for v in q))
            return [v / norm for v in q]
        theta_0 = math.acos(max(-1.0, min(1.0, dot)))
        theta = theta_0 * t
        sin_theta = math.sin(theta)
        sin_theta_0 = math.sin(theta_0)
        s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
        s1 = sin_theta / sin_theta_0
        return [s0 * a[i] + s1 * b[i] for i in range(4)]

    def _quat_to_gl_matrix(self, q):
        qw, qx, qy, qz = q
        r00 = 1.0 - 2.0 * (qy * qy + qz * qz)
        r01 = 2.0 * (qx * qy - qz * qw)
        r02 = 2.0 * (qx * qz + qy * qw)
        r10 = 2.0 * (qx * qy + qz * qw)
        r11 = 1.0 - 2.0 * (qx * qx + qz * qz)
        r12 = 2.0 * (qy * qz - qx * qw)
        r20 = 2.0 * (qx * qz - qy * qw)
        r21 = 2.0 * (qy * qz + qx * qw)
        r22 = 1.0 - 2.0 * (qx * qx + qy * qy)

        return [
            r00, r10, r20, 0.0,
            r01, r11, r21, 0.0,
            r02, r12, r22, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]

    def set_sensor_data(self, pitch, roll, yaw, ax, ay, az, mag_yaw=float("nan")):
        """Render the OpenGL scene."""
        self.pitch = pitch
        self.roll = roll
        self.yaw = yaw
        self.ax = ax
        self.ay = ay
        self.az = az
        self.mag_yaw = mag_yaw

    def initializeGL(self):
        glClearColor(*self.clear_color)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_BLEND)
        glEnable(GL_NORMALIZE)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.08, 0.08, 0.09, 1.0])
        glLightfv(GL_LIGHT0, GL_POSITION, [4.0, 7.0, 6.0, 0.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.04, 0.04, 0.04, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.95, 0.95, 0.92, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.55, 0.55, 0.52, 1.0])

        glLightfv(GL_LIGHT1, GL_POSITION, [-5.0, 3.0, -4.0, 0.0])
        glLightfv(GL_LIGHT1, GL_AMBIENT, [0.0, 0.0, 0.0, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.36, 0.40, 0.48, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [0.12, 0.14, 0.18, 1.0])
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.32, 0.34, 0.38, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 42.0)
        self._compile_vehicle_display_list()

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, w/h, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.last_mouse_x = event.x()
            self.last_mouse_y = event.y()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            dx = event.x() - self.last_mouse_x
            dy = event.y() - self.last_mouse_y
            self.cam_yaw += dx * 0.3
            self.cam_pitch += dy * 0.3
            self.cam_pitch = max(5.0, min(85.0, self.cam_pitch))
            self.last_mouse_x = event.x()
            self.last_mouse_y = event.y()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.cam_distance -= delta * 0.01
        self.cam_distance = max(2.0, min(20.0, self.cam_distance))

    def paintGL(self):
        # 婵犵數濮撮惀澶愬级鎼存挸浜炬俊銈勭劍閸欏繘鏌ｉ幋锝嗩棄缁炬儳顭烽弻锝呂熼懡銈冨仦闂佸搫顑呯粔褰掑蓟閿熺姴鐐婇柍杞扮悼閵忋倖鐓曢柕濠忓缁犵偤鏌＄仦璇插鐎殿噮鍣ｅ畷鍫曗€栭鑺ュ磳闁哄本绋戦埢搴ょ疀閺囩媭鍟嬮梻浣告惈閻ジ宕伴幘璺哄灊婵炲棙鍨跺畷澶愭煏婵炲灝鍔氶柟鐣屾暬濮?
        smooth = 0.25
        self.cube_yaw += (self.target_cube_yaw - self.cube_yaw) * smooth
        self.cube_pitch += (self.target_cube_pitch - self.cube_pitch) * smooth
        self.cube_roll += (self.target_cube_roll - self.cube_roll) * smooth
        if self.has_quaternion:
            self.cube_quat = self._slerp_quat(self.cube_quat, self.target_cube_quat, smooth)
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # 缂傚倸鍊搁崐鎼佸磹閹间礁纾归柣鎴ｅГ閸婂潡鏌ㄩ弴鐐测偓鍫曞焵椤掆偓閸熷磭绮诲☉妯锋婵☆垳鈷堝Σ顖涚節閻㈤潧浠﹂柛銊ㄦ硾椤繈濡歌娑撳秹鏌￠崒娑崇穿鐟滅増甯楅弲鏌ユ煕濞戝崬鏋︾痪顓涘亾濠碉紕鍋戦崐鎰板疾濠婂牊鍋傞柨鐔哄Т閽冪喓鎲搁幋鐘典笉婵炴垯鍨圭粻濠氭煛閸屾ê鍔氱憸鐗堝哺濮婄粯鎷呴搹鐟扮闂佸憡姊瑰ú鐔肩嵁閺嶎収鏁冮柕鍫濇矗缁楀鈹戦悙鍙夆枙濞存粍绻堥幃锟犲即閵忥紕鍘搁梺鎼炲劘閸庤鲸淇婇悡骞熺懓顭ㄩ崟顓犵厜闂佸搫鏈惄顖炵嵁濮椻偓閹瑩鎸婃径澶婂灊闂?
        cam_x = self.cube_x + self.cam_distance * math.sin(math.radians(self.cam_yaw)) * math.cos(math.radians(self.cam_pitch))
        cam_y = self.cube_y + self.cam_distance * math.sin(math.radians(self.cam_pitch))
        cam_z = self.cube_z + self.cam_distance * math.cos(math.radians(self.cam_yaw)) * math.cos(math.radians(self.cam_pitch))
        
        gluLookAt(cam_x, cam_y, cam_z,
                  self.cube_x, self.cube_y, self.cube_z,
                  0, 1, 0)
        
        # 缂傚倸鍊搁崐鎼佸磹閹间礁纾归柟闂寸绾惧綊鏌ｉ幋锝呅撻柛濠傛健閺屻劑寮撮悙娴嬪亾瑜版帒鐤炬い蹇撶墛閳锋帒霉閿濆牊顏犻柕鍡楋躬閺岋繝宕ㄩ鍓х厜闂侀潧妫楅崯鏉戠暦婵傜顫呴柍钘夋缂嶆姊绘担鍛婃儓闁哥噥鍋婇幃褔宕卞▎鎴滅瑝闂佹寧绻傞ˇ浼存偂閻斿吋鐓欓柟娈垮枛椤ｅ吋绻涢幊宄板娴?+ 闂傚倸鍊搁崐鎼佸磹閻戣姤鍤勯柛顐ｆ穿缂嶆牠鎮楅敐搴℃灈缂佲偓鐎ｎ偁浜滈柟鎵虫櫅閻掔儤绻涢崗鍏碱棃婵﹦绮幏鍛存惞閻熸壆顐奸梻浣虹帛椤ㄥ繘宕㈤幆褜鍤楀┑鐘叉搐缁犳氨鎲稿鍫熷€?(闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偛顦甸崹楣冨箛娴ｇ懓鍏婇梻渚€娼ц噹闁告洦鍓氶鍥ㄧ節瀵伴攱婢橀埀顒佹礋楠炲﹥鎯旈敐鍥紡?
        self.draw_grid_with_axes()
        
        # 缂傚倸鍊搁崐鎼佸磹閹间礁纾归柟闂寸绾惧綊鏌ｉ幋锝呅撻柛濠傛健閺屻劑寮撮悙娴嬪亾瑜版帒鐤炬い蹇撶墛閳锋帒霉閿濆牊顏犻柕鍡楋躬閺岋繝宕ㄩ鍓х厜闂侀潧妫楅崯鏉戠暦婵傜顫呴柣妯垮皺娴滀即姊绘担绋挎毐闁圭⒈鍋婂畷顖炴偐鐠囪尙锛涢梺鐟板⒔缁垶寮查弻銉ョ缂侇喖鍘滈崑鎾绘嚑椤掆偓閸ゎ剟姊婚崒娆掑厡缂侇噮鍨堕獮鎰節濮橆厼浠梺闈涱槴閺呮粎绮?(婵犵數濮烽弫鍛婃叏閻㈠壊鏁婇柡宥庡幖缁愭淇婇妶鍛殲鐎规洘鐓￠弻鐔兼焽閿曗偓閺嬨倗绱掗埀顒佺節閸嬵垰缍婇弫鎰板川椤撗勵棏闂備胶绮敮濠勫垝濞嗘挸钃熼柨婵嗘啒閺冨牆鐒垫い鎺戝閸嬪绻濇繝鍌氭殧闁逞屽墯鐢€崇暦婵傜鍗抽柣鏂挎惈楠炲牓姊绘担鍛婃儓婵炲眰鍨藉畷婵嗙暆閸曨偄鍤戝┑鐐村灦閻燂絾绂?
        self.draw_vehicle_model()
        
        # 闂傚倸鍊搁崐鎼佸磹閻戣姤鍤勯柛顐ｆ穿缂嶆牠鎮楅敐搴℃灈缂佲偓鐎ｎ偁浜滈柟鎵虫櫅閻掔儤绻涢崗鍏碱棃婵﹦绮幏鍛存惞閻熸壆顐奸梻浣虹帛椤ㄥ繘宕㈤幆褜鍤楀┑鐘叉搐缁犳氨鎲稿鍫熷€块柤鎭掑劘娴滄粓鐓崶銊﹀鞍妞ゃ儲鍨块弻娑氣偓锝庡亝鐏忣參鏌嶉挊澶樻Ц闁宠绉归、妯款槺闂侇収鍨堕弻鐔碱敍濞嗘垹鐛㈤悗瑙勬礈閸忔﹢銆佸鈧幃鈺冨枈婢跺苯绨ラ梻鍌氬€风欢姘跺焵椤掑倸浠滈柤娲诲灡閺呭墎鈧數纭堕崑鎾舵喆閸曨剙顦╅梺绋款儏閿曘倝鎮鹃悜鑺ュ亜缁炬媽椴搁弲銏ゆ⒑缁嬫寧婀版慨妯稿妿缁?
        # The Home scene intentionally has no screen-space orientation widget.
        
        # 闂傚倸鍊搁崐鐑芥倿閿曞倹鍎戠憸鐗堝笒閺勩儵鏌涢弴銊ョ仩闁搞劌鍊块獮鏍庨鈧俊鑲┾偓鐟版啞缁诲啴濡甸崟顖氱妞ゆ牗顨呮禍楣冩煙?
        self.frame_count += 1
        if time.time() - self.last_fps_update > 1.0:
            self.current_fps = self.frame_count
            self.frame_count = 0
            self.last_fps_update = time.time()

    @staticmethod
    def _draw_cone(tip, base, radial_u, radial_v, radius, segments=16):
        """Draw a closed solid cone between a base plane and its tip."""
        ring = []
        for index in range(segments):
            angle = 2.0 * math.pi * index / segments
            cos_a = math.cos(angle) * radius
            sin_a = math.sin(angle) * radius
            ring.append(tuple(
                base[axis] + radial_u[axis] * cos_a + radial_v[axis] * sin_a
                for axis in range(3)
            ))
        glBegin(GL_TRIANGLES)
        for index, point in enumerate(ring):
            next_point = ring[(index + 1) % segments]
            glVertex3f(*tip)
            glVertex3f(*point)
            glVertex3f(*next_point)
        glEnd()
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(*base)
        for index in range(segments, -1, -1):
            glVertex3f(*ring[index % segments])
        glEnd()

    @classmethod
    def _load_vehicle_mesh(cls):
        """Load, center, scale and align the binary STL with vehicle axes."""
        if hasattr(sys, "_MEIPASS"):
            model_path = Path(sys._MEIPASS) / "tcarkit" / "assets" / "tCar.STL"
        else:
            model_path = Path(__file__).resolve().parent.parent / "assets" / "tCar.STL"

        try:
            payload = model_path.read_bytes()
            if len(payload) < 84:
                raise ValueError("STL header is incomplete")
            triangle_count = struct.unpack_from("<I", payload, 80)[0]
            if len(payload) != 84 + triangle_count * 50:
                raise ValueError("Only binary STL models are supported")

            source = []
            bounds_min = [float("inf")] * 3
            bounds_max = [float("-inf")] * 3
            signed_volume = 0.0
            centroid_sum = [0.0, 0.0, 0.0]
            for index in range(triangle_count):
                values = struct.unpack_from("<12fH", payload, 84 + index * 50)
                vertices = (values[3:6], values[6:9], values[9:12])
                source.append(vertices)
                for vertex in vertices:
                    for axis in range(3):
                        bounds_min[axis] = min(bounds_min[axis], vertex[axis])
                        bounds_max[axis] = max(bounds_max[axis], vertex[axis])

                a, b, c = vertices
                volume = (
                    a[0] * (b[1] * c[2] - b[2] * c[1])
                    - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])
                ) / 6.0
                signed_volume += volume
                for axis in range(3):
                    centroid_sum[axis] += volume * sum(
                        vertex[axis] for vertex in vertices
                    ) / 4.0

            if abs(signed_volume) > 1e-6:
                center = [value / signed_volume for value in centroid_sum]
            else:
                center = [
                    (bounds_min[axis] + bounds_max[axis]) * 0.5
                    for axis in range(3)
                ]
            source_size = max(
                bounds_max[axis] - bounds_min[axis] for axis in range(3)
            )
            scale = cls.VEHICLE_MODEL_SIZE / source_size

            # The model uses X for width, Y for height and Z for length.
            # Flip X together with forward Z so the transform stays
            # right-handed instead of mirroring the vehicle left-to-right.
            triangles = []
            for vertices in source:
                transformed = [
                    (
                        -(vertex[0] - center[0]) * scale,
                        (vertex[1] - center[1]) * scale,
                        -(vertex[2] - center[2]) * scale,
                    )
                    for vertex in vertices
                ]
                a, b, c = transformed
                edge_ab = tuple(b[i] - a[i] for i in range(3))
                edge_ac = tuple(c[i] - a[i] for i in range(3))
                normal = (
                    edge_ab[1] * edge_ac[2] - edge_ab[2] * edge_ac[1],
                    edge_ab[2] * edge_ac[0] - edge_ab[0] * edge_ac[2],
                    edge_ab[0] * edge_ac[1] - edge_ab[1] * edge_ac[0],
                )
                length = math.sqrt(sum(value * value for value in normal))
                if length > 1e-9:
                    normal = tuple(value / length for value in normal)
                triangles.append((normal, transformed))

            # STL has no explicit topology. Rebuild shared edges and retain
            # only open boundaries and hard creases, excluding triangulation
            # diagonals and the small facets that form curved surfaces.
            edge_map = {}
            for normal, vertices in triangles:
                for start, end in (
                    (vertices[0], vertices[1]),
                    (vertices[1], vertices[2]),
                    (vertices[2], vertices[0]),
                ):
                    start_key = tuple(round(value, 5) for value in start)
                    end_key = tuple(round(value, 5) for value in end)
                    key = tuple(sorted((start_key, end_key)))
                    entry = edge_map.setdefault(key, [start, end, []])
                    entry[2].append(normal)

            crease_cosine = math.cos(math.radians(24.0))
            feature_edges = []
            for start, end, normals in edge_map.values():
                is_feature = len(normals) == 1
                if not is_feature:
                    for first in range(len(normals)):
                        for second in range(first + 1, len(normals)):
                            dot = sum(
                                normals[first][axis] * normals[second][axis]
                                for axis in range(3)
                            )
                            if dot < crease_cosine:
                                is_feature = True
                                break
                        if is_feature:
                            break
                if is_feature:
                    feature_edges.append((start, end))

            front_z = -(bounds_max[2] - center[2]) * scale
            return triangles, feature_edges, front_z
        except Exception as exc:
            print(f"Unable to load tCar.STL: {exc}")
            return [], [], -0.6

    def draw_vehicle_model(self):
        """Draw the centered tCar mesh and its existing yellow front arrow."""
        glPushMatrix()
        glTranslatef(self.cube_x, self.cube_y, self.cube_z)
        if self.has_quaternion:
            glMultMatrixf(self._quat_to_gl_matrix(self.cube_quat))
            self.cube_yaw = 0.0
            self.cube_pitch = 0.0
            self.cube_roll = 0.0
        glRotatef(self.cube_yaw, 0, 1, 0)
        glRotatef(self.cube_pitch, 1, 0, 0)
        glRotatef(self.cube_roll, 0, 0, 1)

        glColor3f(*self.vehicle_color)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)
        if self.vehicle_display_list is not None:
            glCallList(self.vehicle_display_list)
        else:
            self._draw_vehicle_triangles()
        glDisable(GL_POLYGON_OFFSET_FILL)

        glDisable(GL_LIGHTING)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        glColor4f(0.055, 0.06, 0.07, 0.88)
        glLineWidth(1.15)
        if self.vehicle_edge_display_list is not None:
            glCallList(self.vehicle_edge_display_list)
        else:
            self._draw_vehicle_feature_edges()

        arrow_base = self.vehicle_front_z - 0.16
        arrow_tip = arrow_base - 0.34
        glColor4f(1.0, 0.9, 0.0, 0.95)
        glLineWidth(3.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, self.vehicle_front_z)
        glVertex3f(0, 0, arrow_base)
        glEnd()
        self._draw_cone(
            (0, 0, arrow_tip), (0, 0, arrow_base),
            (1, 0, 0), (0, 1, 0), 0.10,
        )
        glDisable(GL_LINE_SMOOTH)
        glEnable(GL_LIGHTING)
        glPopMatrix()

    def _draw_vehicle_triangles(self):
        glBegin(GL_TRIANGLES)
        for normal, vertices in self.vehicle_triangles:
            glNormal3f(*normal)
            for vertex in vertices:
                glVertex3f(*vertex)
        glEnd()

    def _compile_vehicle_display_list(self):
        if not self.vehicle_triangles:
            return
        display_list = glGenLists(1)
        if not display_list:
            return
        glNewList(display_list, GL_COMPILE)
        self._draw_vehicle_triangles()
        glEndList()
        self.vehicle_display_list = display_list

        if self.vehicle_feature_edges:
            edge_display_list = glGenLists(1)
            if edge_display_list:
                glNewList(edge_display_list, GL_COMPILE)
                self._draw_vehicle_feature_edges()
                glEndList()
                self.vehicle_edge_display_list = edge_display_list

    def _draw_vehicle_feature_edges(self):
        glBegin(GL_LINES)
        for start, end in self.vehicle_feature_edges:
            glVertex3f(*start)
            glVertex3f(*end)
        glEnd()

    def draw_grid_with_axes(self):
        """Draw ground grid and world axes."""
        glDisable(GL_LIGHTING)
        
        # ===== 缂傚倸鍊搁崐鎼佸磹閹间礁纾归柟闂寸绾惧綊鏌熼梻瀵割槮闁汇値鍠楅妵鍕冀椤愵澀绮堕梺鎼炲妼閸婂潡寮诲☉銏╂晝闁挎繂妫涢ˇ銊╂⒑?=====
        glColor4f(0.15, 0.2, 0.3, 0.6)
        glLineWidth(1.0)
        
        grid_size = 10
        spacing = 0.5
        
        glBegin(GL_LINES)
        for i in range(-grid_size, grid_size + 1):
            pos = i * spacing
            glVertex3f(pos, -0.5, -grid_size * spacing)
            glVertex3f(pos, -0.5, grid_size * spacing)
            glVertex3f(-grid_size * spacing, -0.5, pos)
            glVertex3f(grid_size * spacing, -0.5, pos)
        glEnd()
        
        # ===== 闂傚倸鍊搁崐鎼佸磹閻戣姤鍤勯柛顐ｆ穿缂嶆牠鎮楅敐搴℃灈缂佲偓鐎ｎ偁浜滈柟鎵虫櫅閻掔儤绻涢崗鍏碱棃婵﹦绮幏鍛存惞閻熸壆顐奸梻浣虹帛椤ㄥ繘宕㈤幆褜鍤楀┑鐘叉搐缁犳氨鎲稿鍫熷€?(闂傚倸鍊搁崐鎼佸磹妞嬪孩顐芥慨姗嗗墻閻掍粙鏌ゆ慨鎰偓鏍偓姘煼閺岋綁寮崒姘粯缂備讲鍋撳鑸靛姈閸婂爼鏌ｉ幇顒傛憼闁诲浚鍣ｉ弻銈夊级閹稿骸浠撮梺鍝勭灱閸犳挾妲愰幒妤€顫呴柣妯虹－娴滆埖淇婇悙顏勨偓鎴﹀磿闁秵鍋嬪┑鐘叉搐妗呴梺鍛婃处閸ㄥジ寮崘鈹夸簻闁规壋鏅涢悘鈺冪磼閻樺樊鐓兼慨? =====
        axis_len = 3.0
        arrow = 0.28
        arrow_radius = 0.09
        
        # X闂?(缂傚倸鍊搁崐鎼佸磹閹间礁纾圭€瑰嫰鍋婂〒濠氭煙閻戞﹩娈旂紒鈧€ｎ偅鍙忔俊鐐额嚙娴滈箖鎮楃憴鍕缂傚秴锕ら悾宄拔旈崨顔兼異闂佸啿鎼崯顐ｎ殽? - 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偞鐗犻、鏇㈡晜閽樺缃曞┑鐘垫暩婵鈧凹鍘奸悾鐑藉蓟閵夛妇鍘遍柣蹇曞仜婢х晫绱撳顑?
        glColor4f(1.0, 0.1, 0.1, 0.9)
        glLineWidth(3.0)
        glBegin(GL_LINES)
        glVertex3f(0, -0.48, 0)
        glVertex3f(axis_len, -0.48, 0)
        glEnd()
        self._draw_cone(
            (axis_len, -0.48, 0), (axis_len - arrow, -0.48, 0),
            (0, 1, 0), (0, 0, 1), arrow_radius,
        )
        
        # Y闂?(缂傚倸鍊搁崐鎼佸磹閹间礁纾归柟闂寸绾惧湱鈧懓瀚崳纾嬨亹閹烘垹鍊炲銈嗗坊閸嬫挾鐥幑鎰《缂佽鲸鎸婚幏鍛嫚閿涘嫬濮洪梻? - 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偞鐗犻、鏇㈡晜閽樺缃曞┑鐘垫暩婵鈧凹鍘奸悾鐑藉蓟閵夛妇鍘遍柣蹇曞仜婢т粙鍩婇弴鐔虹?(Z闂傚倸鍊搁崐宄懊归崶褏鏆﹂柛顭戝亝閸欏繘鏌ｉ姀銏╃劸缂佲偓婢跺绻嗛柕鍫濇噺閸ｅ湱绱掗幇顓ф疁闁哄瞼鍠栭幃褔宕奸悢鍝勫殥闂備浇妫勯崯浼村窗閺嶎厼钃熼柨婵嗩槸缁秹鏌涚仦鎹愬濞寸姵锕㈤弻?
        glColor4f(0.1, 1.0, 0.1, 0.9)
        glLineWidth(3.0)
        glBegin(GL_LINES)
        glVertex3f(0, -0.48, 0)
        glVertex3f(0, -0.48, -axis_len)
        glEnd()
        self._draw_cone(
            (0, -0.48, -axis_len), (0, -0.48, -axis_len + arrow),
            (1, 0, 0), (0, 1, 0), arrow_radius,
        )
        
        # ===== Z闂?(闂傚倸鍊搁崐鎼佸磹瀹勬噴褰掑炊椤剚鐩畷鐔碱敍濮樿鲸鐒炬俊鐐€栭悧妤冨垝瀹ュ懐鏆﹂柡灞诲劜閻撴洟鏌嶉埡浣告灓闁绘帊绮欓弻? - 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偞鐗犻、鏇㈡晜閽樺缃曞┑鐘垫暩婵鈧凹鍘奸悾鐑藉蓟閵夛妇鍘撻悷婊勭矒瀹曟粌鈽夊顓ф綗?=====
        glColor4f(0.1, 0.1, 1.0, 0.9)
        glLineWidth(3.0)
        glBegin(GL_LINES)
        glVertex3f(0, -0.48, 0)
        glVertex3f(0, axis_len - 0.48, 0)
        glEnd()
        self._draw_cone(
            (0, axis_len - 0.48, 0), (0, axis_len - 0.48 - arrow, 0),
            (1, 0, 0), (0, 0, 1), arrow_radius,
        )
        
        # 濠电姷鏁告慨鐑藉极閹间礁纾婚柣鎰惈閸ㄥ倿鏌涢锝嗙缂佺姴缍婇弻宥夊传閸曨剙娅ｉ梺绋胯閸旀垿寮婚妶鍚ゅ湱鈧綆鍋呴悵鏍磽娴ｇ懓鏁剧紒鐘冲灱閻忓啴姊洪幐搴ｇ畵闁瑰啿閰ｅ鍐测枎閹惧鍘遍梺纭呭焽閸斿本绂嶆ィ鍐┾拻闁稿本鐟ч崝宥夋煙椤旇偐鍩ｇ€规洘娲熼幃婊兾熺喊杈ㄩ敜闂備礁澹婇崑鍛洪弽顓熷殝?
        glColor4f(1.0, 1.0, 1.0, 0.5)
        glPointSize(4)
        glBegin(GL_POINTS)
        glVertex3f(0, -0.48, 0)
        glEnd()
        
        glEnable(GL_LIGHTING)

    def draw_cube(self):
        """Draw the attitude cube."""
        size = 0.6
        h = size
        
        v = [
            [-h, -h, -h], [h, -h, -h], [h, h, -h], [-h, h, -h],
            [-h, -h, h], [h, -h, h], [h, h, h], [-h, h, h]
        ]
        
        gray = (0.4, 0.4, 0.4)
        faces = [
            ([0, 1, 2, 3], (1.0, 0.85, 0.0), (0, 0, -1)),  # 婵犵數濮烽弫鍛婃叏閻㈠壊鏁婇柡宥庡幖缁愭淇婇妶鍛殲鐎规洘鐓￠弻鐔兼焽閿曗偓閺嬨倗绱掗埀顒佺節閸嬵垰缍婇弫鎰板川椤撗勵棏闂?- 濠电姷鏁告慨鐢割敊閺嶎厼绐楁俊銈呭暞閺嗘粍淇婇妶鍛殶闁活厽鐟╅弻鐔衡偓鐢殿焾琚ラ梺绋款儐閹告悂锝炲┑瀣亗閹艰揪绲奸悽鑽ょ磽?
            ([4, 5, 6, 7], gray, (0, 0, 1)),               # 闂傚倸鍊搁崐鎼佸磹閻戣姤鍤勯柛顐ｆ礀閸屻劎鎲搁弬璺ㄦ殾妞ゆ牜鍋涢柨銈嗕繆閵堝嫮顦﹂柛鎾崇秺濮婅櫣绮欓幐搴㈡嫳闂佸憡鍨电紞濠囧箖?- 闂傚倸鍊搁崐鎼佸磹瀹勬噴褰掑炊椤掑鏅悷婊冪箻楠炴垿濮€閵堝懐顓洪梺缁樺姈瑜板啴鎮樻笟鈧娲礂闂傜鍩呴梺绋垮婵炲﹪骞?
            ([0, 1, 5, 4], gray, (0, -1, 0)),              # 闂傚倸鍊搁崐椋庣矆娴ｉ潻鑰块梺顒€绉撮崒銊ф喐閺冨牆绠栨繛宸簻鎯熼梺闈涱槸閸燁垰顪冩禒瀣畺闁靛骏绱曢梽鍕熆鐠洪缚瀚板┑?- 闂傚倸鍊搁崐鎼佸磹瀹勬噴褰掑炊椤掑鏅悷婊冪箻楠炴垿濮€閵堝懐顓洪梺缁樺姈瑜板啴鎮樻笟鈧娲礂闂傜鍩呴梺绋垮婵炲﹪骞?
            ([2, 3, 7, 6], gray, (0, 1, 0)),               # 濠电姷鏁告慨鐑姐€傞鐐潟闁哄洢鍨圭壕濠氭煙鏉堝墽鐣辩痪鎯х秺閺岋繝宕堕妷銉т痪闂佺顑呴ˇ鐢稿蓟閿濆绠婚柛鎰皺濡蹭即姊?- 闂傚倸鍊搁崐鎼佸磹瀹勬噴褰掑炊椤掑鏅悷婊冪箻楠炴垿濮€閵堝懐顓洪梺缁樺姈瑜板啴鎮樻笟鈧娲礂闂傜鍩呴梺绋垮婵炲﹪骞?
            ([0, 3, 7, 4], gray, (-1, 0, 0)),              # 闂傚倸鍊峰ù鍥敋瑜庨〃銉╁传閵壯咁槸婵犵數濮撮崑鍡涙倿娴犲鐓犲┑顔藉姇閳ь剚顨嗙粙澶婎吋婢跺鍘甸梺缁樺姦閸撴瑦鏅堕鐐寸厽?- 闂傚倸鍊搁崐鎼佸磹瀹勬噴褰掑炊椤掑鏅悷婊冪箻楠炴垿濮€閵堝懐顓洪梺缁樺姈瑜板啴鎮樻笟鈧娲礂闂傜鍩呴梺绋垮婵炲﹪骞?
            ([1, 2, 6, 5], gray, (1, 0, 0)),               # 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偛顦甸弫鎾绘偐閸愯弓鐢婚梻浣瑰濮婂寮查銈囦笉闁诡垎鈧弨浠嬫煟濡绲诲ù婊呭仱閺?- 闂傚倸鍊搁崐鎼佸磹瀹勬噴褰掑炊椤掑鏅悷婊冪箻楠炴垿濮€閵堝懐顓洪梺缁樺姈瑜板啴鎮樻笟鈧娲礂闂傜鍩呴梺绋垮婵炲﹪骞?
        ]
        
        glPushMatrix()
        glTranslatef(self.cube_x, self.cube_y, self.cube_z)
        if self.has_quaternion:
            glMultMatrixf(self._quat_to_gl_matrix(self.cube_quat))
            self.cube_yaw = 0.0
            self.cube_pitch = 0.0
            self.cube_roll = 0.0
        
        glRotatef(self.cube_yaw, 0, 1, 0)      # Yaw (缂傚倸鍊搁崐鎼佸磹閹间礁纾归柟闂寸绾惧綊鏌ｉ幋锝呅撻柛濠傛健閺屻劑寮村Δ鈧禍楣冩煕濡ゅ懍鎲鹃柡灞诲姂閹垽宕崟鎴欏灮缁?
        glRotatef(self.cube_pitch, 1, 0, 0)    # Pitch (缂傚倸鍊搁崐鎼佸磹閹间礁纾归柟闂寸绾惧綊鏌ｉ幋锝呅撻柛濠傛健閺屻劑寮村Δ鈧禍楣冩煕濡ゅ嫰鍝虹紒缁樼箞濡啫鈽夐崡鐐插缂? - 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偛顦甸弫鎾绘偐閼碱剦鍞堕梻浣告啞缁哄潡宕曢幎鑺ュ剹闁瑰墽绮悡娆戠磽娴ｉ潧鐏╅柡瀣〒缁辨帡鎮╁畷鍥ь潷婵烇絽娲ら敃顏呬繆閸洖绀嬫い鏃傚帶鐢垶姊绘担鍝ワ紞闁硅櫕鎸剧划鏃堟偨缁嬭锕傛煕閺囥劌鐏犻柛鎰ㄥ亾闂備線娼ц噹闁告洦鍋呴悵顖炴⒒?
        glRotatef(self.cube_roll, 0, 0, 1)     # Roll (缂傚倸鍊搁崐鎼佸磹閹间礁纾归柟闂寸绾惧綊鏌ｉ幋锝呅撻柛濠傛健閺屻劑寮村Δ鈧禍楣冩煕濡ゅ懍鎲鹃柡灞炬礉缁犳稓鈧綆浜栭崑鎾诲即閻樺灚锛? - 闂傚倸鍊峰ù鍥敋瑜庨〃銉╁传閵壯咁槸婵犵數濮撮崑鍡涙倿娴犲鐓犲┑顔藉姇閳ь剚顨嗙粙澶婎吋婢跺鍘甸柡澶婄墕婢х晫绮婂畡鎳婄懓顭ㄩ崘顏喰ㄩ梺鍝勬湰缁嬫垿鍩ユ径濠庢建闁割偅绻傞～鐘绘⒒娴ｈ棄鍚归柛鐘查閿曘垽鏌嗗鍛枀濠殿喗绻傞惉濂告偪閳ь剙鈹戦悙鏉戠仸闁荤喆鍎甸崺鈧?
        
        for face, color, normal in faces:
            glBegin(GL_QUADS)
            glNormal3f(*normal)
            glColor3f(*color)
            for idx in face:
                glVertex3f(*v[idx])
            glEnd()
        
        # 闂傚倸鍊搁崐椋庣矆娓氣偓楠炴牠顢曚綅閸ヮ剦鏁嶉柣鎰綑娴滈亶姊虹憴鍕凡閹煎瓨绮庣槐鐐哄冀瑜滈悢鍡涙煠閹间焦娑у┑顔煎€块弻?
        glDisable(GL_LIGHTING)
        glLineWidth(1.0)
        glColor4f(0.3, 0.3, 0.4, 0.3)
        edges = [
            (0,1), (1,2), (2,3), (3,0),
            (4,5), (5,6), (6,7), (7,4),
            (0,4), (1,5), (2,6), (3,7)
        ]
        glBegin(GL_LINES)
        for edge in edges:
            for idx in edge:
                glVertex3f(*v[idx])
        glEnd()
        glEnable(GL_LIGHTING)
        
        glDisable(GL_LIGHTING)
        glColor4f(1.0, 0.9, 0.0, 0.9)
        glLineWidth(3.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, -h)
        glVertex3f(0, 0, -h - 0.28)
        glEnd()
        self._draw_cone(
            (0, 0, -h - 0.52), (0, 0, -h - 0.28),
            (1, 0, 0), (0, 1, 0), 0.09,
        )
        glEnable(GL_LIGHTING)
        
        glPopMatrix()

    def draw_axes_indicator(self):
        """Draw the small screen-space axes indicator."""
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        w, h = self.width(), self.height()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        cx = w - 80
        cy = h - 80
        radius = 30
        
        glColor4f(0.0, 0.0, 0.0, 0.5)
        glBegin(GL_TRIANGLE_FAN)
        for i in range(36):
            angle = 2 * math.pi * i / 36
            glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        glEnd()
        
        # X闂?(缂? - 闂?
        glColor4f(1.0, 0.2, 0.2, 0.9)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glVertex2f(cx, cy)
        glVertex2f(cx + radius * 0.8, cy)
        glEnd()
        glPointSize(4)
        glBegin(GL_POINTS)
        glVertex2f(cx + radius * 0.9, cy)
        glEnd()
        
        # Y闂?(缂? - 濠?(闂傚倸鍊搁崐宄懊归崶顒夋晪鐟滃秹婀侀梺缁樺灱濡嫰寮告笟鈧弻鐔兼⒒鐎靛壊妲紓浣哄Х婵炩偓闁哄瞼鍠栭幃娆擃敆閳ь剟宕濈捄琛℃斀妞ゆ棁妫勯埢鏇㈡煛鐏炲墽鈽夐柍璇叉唉缁犳盯鏁愰崰鑸姂濮婂搫鐣烽崶鈺佺濠碘槅鍋勯崯鏉戭嚕婵犳艾鐏抽柟棰佺閹垿鏌熼懖鈺勊夐柍褜鍓濈亸娆撳礄鐟欏嫮绡€闁汇垽娼ф禒婊堟煙閸愯尙绠伴悡銈夋煟閺冨倸甯堕柦鍐枛閺屻劌鈹戦崱鈺傂﹂柟顖滃枛濮婃椽妫冨☉杈ㄐら梺绋挎唉濞呮洜绮嬪澶嬪€烽柣鎴炃氶幏?
        glColor4f(0.2, 1.0, 0.2, 0.9)
        glBegin(GL_LINES)
        glVertex2f(cx, cy)
        glVertex2f(cx, cy - radius * 0.8)
        glEnd()
        glBegin(GL_POINTS)
        glVertex2f(cx, cy - radius * 0.9)
        glEnd()
        
        # Z闂?(闂? - 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偞鐗犻、鏇㈡晝閳ь剛澹曡ぐ鎺撶厱闁挎棁顕ч獮鏍煕閵婏妇绠橀柍褜鍓欓崢婊堝磻閹剧粯鐓曢柡鍥ュ妼娴滅偤鏌?(闂傚倸鍊搁崐宄懊归崶顒夋晪鐟滃秹婀侀梺缁樺灱濡嫰寮告笟鈧弻鐔兼⒒鐎靛壊妲紓浣哄Х婵炩偓闁哄瞼鍠栭幃娆擃敆閳ь剟宕濈捄琛℃斀妞ゆ棁妫勯埢鏇㈡煛鐏炲墽鈽夐柍璇叉唉缁犳盯鏁愰崰鑸姂濮婂搫鐣烽崶鈺佺濠碘槅鍋勯崯鏉戭嚕婵犳艾鐏抽柟棰佺閹垿鏌熼懖鈺勊夐柍褜鍓濈亸娆撳礄鐟欏嫮绡€闁汇垽娼ф禒婊堟煙閸愯尙绠伴悡銈夋煟閺冨倸甯堕柦鍐枛閺屻劌鈹戦崱鈺傂﹂柟顖滃枛濮婃椽妫冨☉杈ㄐら梺绋挎唉濞呮洜绮嬪鍛瀻闁瑰墽琛ラ幏?
        glColor4f(0.2, 0.2, 1.0, 0.9)
        glBegin(GL_LINES)
        glVertex2f(cx, cy)
        glVertex2f(cx + radius * 0.5 * 0.707, cy + radius * 0.5 * 0.707)
        glEnd()
        glBegin(GL_POINTS)
        glVertex2f(cx + radius * 0.5 * 0.707, cy + radius * 0.5 * 0.707)
        glEnd()
        
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)


# ============ 濠电姷鏁告慨鐑藉极閹间礁纾婚柣鎰惈閸ㄥ倿鏌涢锝嗙缂佺姵褰冮湁闁挎繂鎳忛幉鎼佹煛閸☆厾鐣甸柡宀嬬秮婵偓闁绘ê鍟块弳鍫ユ⒑缁嬫鍎愰柨鏇樺灲瀵寮撮悢椋庣獮闂佺硶鍓濊摫闁绘繃妫冨?============
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Third Person - MPU6050 Attitude Viewer")
        self.setGeometry(50, 50, 1100, 750)
        
        self.setStyleSheet("""
            QMainWindow { background-color: #0a0a12; }
            QLabel {
                background: rgba(0,0,0,0.4);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 15px;
            }
        """)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        
        view_container = QWidget()
        view_layout = QGridLayout(view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)
        self.gl_view = ThirdPersonView()
        view_layout.addWidget(self.gl_view, 0, 0)
        layout.addWidget(view_container, 1)

        self.camera_label = QLabel()
        self.camera_label.setFixedSize(240, 180)
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("background: #111; border: 1px solid #555;")
        self.camera_label.setText("Camera offline")
        view_layout.addWidget(self.camera_label, 0, 0, Qt.AlignTop | Qt.AlignRight)
        self.camera_thread = CameraReceiver()
        self.camera_thread.frame_received.connect(self.update_camera)
        self.camera_thread.start()
        
        # ===== 濠电姷鏁告慨鐑藉极閹间礁纾块柟瀵稿Т缁躲倝鏌﹀Ο渚＆婵炲樊浜濋崑鎰版偣閸ヮ亜鐨烘い锔诲幖閳规垿鎮╃紒妯婚敪濠电偛鐪伴崐婵嬨€佸鑸电劶鐎广儱妫涢崢鍗炩攽閻愭潙鐏︽い顓炴喘楠炴鎮╅悙鎴掔盎闂侀潧顦崕铏櫠閿曞倹鐓涢悘鐐靛亾缁€澶岀磼閻樺磭鈯曠紒缁樼箞瀹曟帒顫濋敐鍡楃彾缂?=====
        info_panel = QWidget()
        info_layout = QHBoxLayout(info_panel)
        info_layout.setSpacing(15)
        
        self.yaw_label = QLabel("Yaw: 0.0 deg")
        self.yaw_label.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 16px; min-width: 130px;")
        info_layout.addWidget(self.yaw_label)

        self.mag_label = QLabel("Mag: --")
        self.mag_label.setAlignment(Qt.AlignCenter)
        self.mag_label.setStyleSheet("color: #b388ff; font-weight: bold; font-size: 16px;")
        
        self.pitch_label = QLabel("Pitch: 0.0 deg")
        self.pitch_label.setStyleSheet("color: #ff6b6b; font-weight: bold; font-size: 16px; min-width: 130px;")
        info_layout.addWidget(self.pitch_label)
        
        self.roll_label = QLabel("Roll: 0.0 deg")
        self.roll_label.setStyleSheet("color: #ffd93d; font-weight: bold; font-size: 16px; min-width: 130px;")
        info_layout.addWidget(self.roll_label)
        
        self.ax_label = QLabel("X: 0.00 g")
        self.ax_label.setStyleSheet("color: #ff6b6b; font-size: 14px; min-width: 100px;")
        info_layout.addWidget(self.ax_label)
        
        self.ay_label = QLabel("Y: 0.00 g")
        self.ay_label.setStyleSheet("color: #6bcb77; font-size: 14px; min-width: 100px;")
        info_layout.addWidget(self.ay_label)
        
        self.az_label = QLabel("Z: 0.00 g")
        self.az_label.setStyleSheet("color: #4fc3f7; font-size: 14px; min-width: 100px;")
        info_layout.addWidget(self.az_label)
        
        info_layout.addStretch()
        
        self.status_label = QLabel("Waiting...")
        self.status_label.setStyleSheet("color: #ff4444; font-size: 14px; min-width: 120px;")
        info_layout.addWidget(self.status_label)
        
        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setStyleSheet("color: #88aacc; font-size: 14px; min-width: 70px;")
        info_layout.addWidget(self.fps_label)
        
        layout.addWidget(info_panel)
        layout.addWidget(self.mag_label)
        
        tip_label = QLabel("Mouse drag rotates view | Wheel zoom | MPU6050 attitude viewer")
        tip_label.setStyleSheet("color: #666677; font-size: 12px; padding: 4px;")
        layout.addWidget(tip_label)
        
        self.receiver = UDPReceiver()
        self.receiver.data_received.connect(self.update_data)
        self.receiver.connection_status.connect(self.update_status)
        self.receiver.start()

    def update_status(self, connected):
        if connected:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: #44ff44; font-size: 14px; min-width: 120px;")
        else:
            self.status_label.setText("Waiting...")
            self.status_label.setStyleSheet("color: #ff4444; font-size: 14px; min-width: 120px;")

    def update_camera(self, image):
        self.camera_label.setPixmap(QPixmap.fromImage(image).scaled(
            self.camera_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def update_data(self, data):
        pitch, roll, yaw = data[0], data[1], data[2]
        if len(data) >= 14:
            qw, qx, qy, qz = data[3], data[4], data[5], data[6]
            ax, ay, az = data[7], data[8], data[9]
            distance = data[13]
            self.gl_view.set_cube_quaternion(qw, qx, qy, qz)
            mag_yaw = data[14] if len(data) >= 15 else float("nan")
        else:
            ax, ay, az = data[3], data[4], data[5]
            distance = data[9]
            mag_yaw = float("nan")
        
        # 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偞鐗犻、鏇㈠煕濮橆厽銇濆┑陇鍩栧鍕偓锝庝簷濡叉劙姊绘笟鈧褑澧濋梺鍝勬噺閻╊垶骞?D闂傚倸鍊搁崐宄懊归崶褏鏆﹂柣銏㈩焾缁愭鏌熼幍顔碱暭闁稿绻濋弻鏇熷緞閸繂澹斿┑鐐村灦椤倿寮崼婵堝姦濡炪倖甯掔€氼厾绮?- 濠电姷鏁告慨鐑藉极閹间礁纾绘繛鎴欏灪閸嬨倝鏌曟繛鐐珔闁告艾缍婇獮鏍庨鈧俊鑲╃棯閹呯Ш闁哄备鈧磭鏆ゆい鏂垮悑閸ｇ儤绻涢崼銉х暫婵﹤鎼叅閻犲洩寮撶花浠嬫⒑闂堟稒澶勯柟鍓叉h闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偛顦甸弫宥夊礋椤愩垻浜伴柣搴″帨閸嬫捇鏌涢弴鐐典粵闁哄懌鍨藉铏光偓鍦У椤忕娀鎮介婊呪攳
        self.gl_view.set_cube_angles(yaw, pitch, roll)
        self.gl_view.set_sensor_data(pitch, roll, yaw, ax, ay, az, mag_yaw)
        
        # 闂傚倸鍊搁崐鎼佸磹妞嬪海鐭嗗〒姘ｅ亾妤犵偞鐗犻、鏇㈠煕濮橆厽銇濆┑陇鍩栧鍕偓锝庝簷濡叉劙姊绘笟鈧褑澧濋梺鍝勬噺閻╊垶骞忛幋锔藉亜閻忓繋鐒﹂弬鈧梻浣虹帛閿氱€殿喖鐖奸獮鏍箛閻楀牏鍘遍梺纭呭焽閸斿本绂嶆ィ鍐┾拻闁稿本鐟ч崝宥夋煙椤旇偐鍩ｇ€规洘娲熼、姘跺焵椤掆偓椤曪綁寮婚妷銉у幐闂佸憡渚楅崢楣兯?
        self.yaw_label.setText(f"Yaw: {yaw:6.1f} deg")
        if math.isfinite(mag_yaw):
            # Calibrated absolute magnetic heading uses 0 degrees as North.
            directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
            direction = directions[int((mag_yaw + 22.5) % 360.0 // 45.0)]
            self.mag_label.setText(f"Mag: {mag_yaw:6.1f} deg  {direction}")
        else:
            self.mag_label.setText("Mag: --")
        self.pitch_label.setText(f"Pitch: {pitch:6.1f} deg")
        self.roll_label.setText(f"Roll: {roll:6.1f} deg")
        
        self.ax_label.setText(f"X: {ax/16384.0:6.2f} g")
        self.ay_label.setText(f"Y: {ay/16384.0:6.2f} g")
        self.az_label.setText(f"Z: {az/16384.0:6.2f} g")

    def closeEvent(self, event):
        self.receiver.stop()
        self.receiver.wait()
        self.camera_thread.stop()
        self.camera_thread.wait(1500)
        event.accept()


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
