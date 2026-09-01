# rpc.py
import requests
import json
import time
from server.rpc.core_host import get_core_host

class CarRPC:
    def __init__(self, host=None, port=9030, endpoint="/"):
        """
        初始化JSON-RPC 2.0客户端
        """
        self.host = host
        self.port = port
        self.endpoint = endpoint
        self.request_id = 0
        
        # 方法参数配置
        # "positional": 位置参数列表，如 ["angle"]
        # "args_count": 参数数量（对于可变参数，设为-1）
        self.method_params = {
            # 无参数方法
            "Heartbeat": {"type": "positional", "params": []},
            "UnloadFunc": {"type": "positional", "params": []},
            "StartFunc": {"type": "positional", "params": []},
            "StopFunc": {"type": "positional", "params": []},
            "FinishFunc": {"type": "positional", "params": []},
            "GetRunningFunc": {"type": "positional", "params": []},
            "GetBatteryVoltage": {"type": "positional", "params": []},
            "GetSonarDistance": {"type": "positional", "params": []},
            "GetSystemInfo": {"type": "positional", "params": []},
            "HardwareSelfTest": {"type": "positional", "params": []},
            "ResetPWMServo": {"type": "positional", "params": []},
            "GetSonarDistanceThreshold": {"type": "positional", "params": []},
            "SetSonarRGBStartSymphony": {"type": "positional", "params": []},
            "GetLABValue": {"type": "positional", "params": []},
            "HaveLABAdjust": {"type": "positional", "params": []},
            
            # 单个位置参数方法
            "SetMovementAngle": {"type": "positional", "params": ["angle"]},
            "SetAvoidanceSpeed": {"type": "positional", "params": ["speed"]},
            "SetSonarDistanceThreshold": {"type": "positional", "params": ["threshold"]},
            "SetSonarRGBMode": {"type": "positional", "params": ["mode"]},
            "ColorTrackingWheel": {"type": "positional", "params": ["state"]},
            "SaveLABValue": {"type": "positional", "params": ["color"]},
            "LoadFunc": {"type": "positional", "params": ["new_func"]},
            "SetServoVelocity": {"type": "positional", "params": ["servo_id", "speed"]},
            "GetPWMServoPosition": {"type": "positional", "params": ["servo_id"]},
            
            # 特殊字符串参数方法（参数必须是指定字符串）
            "UnloadBusServo": {"type": "positional", "params": ["args"], "fixed_value": "servoPowerDown"},
            "GetBusServosDeviation": {"type": "positional", "params": ["args"], "fixed_value": "readDeviation"},
            "SaveBusServosDeviation": {"type": "positional", "params": ["args"], "fixed_value": "downloadDeviation"},
            "GetBusServosPulse": {"type": "positional", "params": ["args"], "fixed_value": "angularReadback"},
            "StopBusServo": {"type": "positional", "params": ["args"], "fixed_value": "stopAction"},
            
            # 固定多个位置参数方法
            "SetSonarRGB": {"type": "positional", "params": ["index", "r", "g", "b"]},
            "SetSonarRGBBreathCycle": {"type": "positional", "params": ["index", "color", "cycle"]},
            "SetBusServoDeviation": {"type": "positional", "params": ["servo", "deviation"]},
            
            # 可变位置参数方法 (*args)
            "SetPWMServo": {"type": "variable", "params": "*args"},
            "SetBrushMotor": {"type": "variable", "params": "*args"},
            "SetBusServoPulse": {"type": "variable", "params": "*args"},
            "ColorTracking": {"type": "variable", "params": "*target_color"},
            "VisualPatrol": {"type": "variable", "params": "*target_color"},
            "ColorDetect": {"type": "variable", "params": "*target_color"},
            "SetLABValue": {"type": "variable", "params": "*lab_value"},
        }
    
    def _generate_id(self):
        """生成请求ID"""
        self.request_id += 1
        return self.request_id
    
    def call(self, method, *args, **kwargs):
        """
        调用远程方法
        
        重要：服务器端只接受位置参数，不接受关键字参数！
        """
        # 构建JSON-RPC 2.0请求
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._generate_id()
        }
        
        # 获取方法配置
        config = self.method_params.get(method)
        
        if config:
            param_type = config["type"]
            
            if param_type == "positional":
                params_list = config["params"]
                
                # 处理固定值参数
                if "fixed_value" in config:
                    # 这些方法必须传特定字符串
                    payload["params"] = [config["fixed_value"]]
                
                # 无参数方法
                elif not params_list:
                    if args or kwargs:
                        print(f"警告: 方法 {method} 不需要参数，但传入了参数")
                    # 不添加params字段
                
                # 位置参数方法
                else:
                    if kwargs:
                        # 有关键字参数，尝试按参数名顺序提取
                        extracted_args = []
                        for param_name in params_list:
                            if param_name in kwargs:
                                extracted_args.append(kwargs[param_name])
                        if extracted_args:
                            payload["params"] = extracted_args
                        elif args:
                            # 如果有关键字参数但没匹配上，使用位置参数
                            payload["params"] = list(args)
                    elif args:
                        # 只有位置参数
                        payload["params"] = list(args)
            
            elif param_type == "variable":
                # 可变参数方法
                if args:
                    payload["params"] = list(args)
                elif kwargs:
                    # 对于可变参数，kwargs的所有值作为参数列表
                    payload["params"] = list(kwargs.values())
        
        else:
            # 未知方法，尝试智能处理
            print(f"警告: 方法 {method} 不在配置列表中，尝试智能处理")
            if args:
                payload["params"] = list(args)
            elif kwargs:
                payload["params"] = list(kwargs.values())
        
        # 调试信息
        print(f"调用方法: {method}")
        if "params" in payload:
            print(f"参数: {payload['params']}")
        
        try:
            host = self.host or get_core_host()
            base_url = f"http://{host}:{self.port}{self.endpoint}"
            # HardwareSelfTest intentionally moves both servos sequentially
            # and then exercises four motors. It normally takes around four
            # seconds, so the common two-second RPC timeout reports a false
            # failure immediately after the gimbal finishes moving. Keep a
            # short connect timeout but allow this one operation to complete.
            timeout = (2, 35) if method == "HardwareSelfTest" else 2
            # 发送POST请求
            response = requests.post(
                base_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout
            )
            
            # 检查响应状态
            response.raise_for_status()
            
            # 获取JSON响应
            result = response.json()
            
            # 检查JSON-RPC错误
            if "error" in result:
                error_data = result["error"]
                error_msg = error_data.get("message", "Unknown error")
                error_code = error_data.get("code", -1)
                
                # 如果有详细错误信息
                if "data" in error_data:
                    data = error_data["data"]
                    error_detail = data.get('message', str(data))
                    print(f"错误详情: {error_detail}")
                
                return {"error": error_msg, "code": error_code, "success": False}
            
            # 返回结果
            if "result" in result:
                return {"success": True, "result": result["result"]}
            else:
                return {"success": True, "result": None}
            
        except requests.exceptions.RequestException as e:
            print(f"RPC调用失败: {e}")
            return {"error": str(e), "success": False}
        except json.JSONDecodeError as e:
            print(f"JSON解析失败: {e}")
            return {"error": f"JSON解析失败: {e}", "success": False}
    
    # 便捷方法 - 现在都使用位置参数
    def post_rpc(self, method, *args):
        """
        保持向后兼容，但只使用位置参数
        """
        return self.call(method, *args)
    
    # 常用方法的快捷方式（使用位置参数）
    def heartbeat(self):
        """发送心跳"""
        return self.call("Heartbeat")
    
    def get_battery(self):
        """获取电池电压"""
        return self.call("GetBatteryVoltage")
    
    def get_distance(self):
        """获取超声波距离"""
        return self.call("GetSonarDistance")
    
    def set_movement_angle(self, angle):
        """设置移动角度"""
        return self.call("SetMovementAngle", angle)
    
    def set_avoidance_speed(self, speed):
        """设置避障速度"""
        return self.call("SetAvoidanceSpeed", speed)
    
    def set_rgb_light(self, index, r, g, b):
        """设置RGB灯颜色"""
        return self.call("SetSonarRGB", index, r, g, b)
    
    def load_function(self, func_id):
        """加载功能"""
        return self.call("LoadFunc", func_id)
    
    def unload_function(self):
        """卸载功能"""
        return self.call("UnloadFunc")
    
    def start_function(self):
        """开始功能"""
        return self.call("StartFunc")
    
    def stop_function(self):
        """停止功能"""
        return self.call("StopFunc")
    
    def finish_function(self):
        """完成功能"""
        return self.call("FinishFunc")
    
    def get_running_function(self):
        """获取运行中的功能"""
        return self.call("GetRunningFunc")
    
    def set_sonar_mode(self, mode):
        """设置超声波RGB模式"""
        return self.call("SetSonarRGBMode", mode)
    
    def start_sonar_symphony(self):
        """开始超声波RGB交响"""
        return self.call("SetSonarRGBStartSymphony")
    
    def set_color_tracking(self, *colors):
        """设置颜色跟踪"""
        return self.call("ColorTracking", *colors)
    
    def set_color_detect(self, *colors):
        """设置颜色检测"""
        return self.call("ColorDetect", *colors)
    
    def set_visual_patrol(self, *colors):
        """设置视觉巡逻"""
        return self.call("VisualPatrol", *colors)
    
    def get_lab_value(self):
        """获取LAB颜色值"""
        return self.call("GetLABValue")
    
    def save_lab_value(self, color):
        """保存LAB颜色值"""
        return self.call("SaveLABValue", color)
    
    def have_lab_adjust(self):
        """检查是否有LAB调整"""
        return self.call("HaveLABAdjust")


# 创建全局实例
rpc_client = CarRPC()

# 保持原来的全局函数（使用位置参数）
def post_rpc(method, *args):
    """
    全局函数，使用位置参数
    """
    return rpc_client.call(method, *args)


# 测试函数 - 修正版
def test_common_methods():
    """测试常用方法"""
    print("=" * 50)
    print("测试常用RPC方法")
    print("=" * 50)
    
    tests = [
        ("心跳测试", lambda: rpc_client.heartbeat()),
        ("获取电池电压", lambda: rpc_client.get_battery()),
        ("获取超声波距离", lambda: rpc_client.get_distance()),
        ("卸载功能", lambda: rpc_client.unload_function()),
        ("开始功能", lambda: rpc_client.start_function()),
        ("停止功能", lambda: rpc_client.stop_function()),
        ("完成功能", lambda: rpc_client.finish_function()),
        ("获取运行功能", lambda: rpc_client.get_running_function()),
    ]
    
    for test_name, test_func in tests:
        print(f"\n{test_name}...")
        result = test_func()
        success = result.get("success", False)
        if success:
            result_data = result.get('result')
            if result_data:
                print(f"  ✓ 成功: {result_data}")
            else:
                print(f"  ✓ 成功")
        else:
            print(f"  ✗ 失败: {result.get('error')}")
    
    return True


def test_with_parameters():
    """测试带参数的方法"""
    print("\n" + "=" * 50)
    print("测试带参数的方法")
    print("=" * 50)
    
    tests = [
        ("设置移动角度 90度", lambda: rpc_client.call("SetMovementAngle", 90)),
        ("设置移动角度 -1(停止)", lambda: rpc_client.call("SetMovementAngle", -1)),
        ("设置避障速度 50", lambda: rpc_client.call("SetAvoidanceSpeed", 50)),
        ("设置RGB灯红色", lambda: rpc_client.call("SetSonarRGB", 0, 255, 0, 0)),
        ("加载功能 1", lambda: rpc_client.call("LoadFunc", 1)),
        ("加载功能 2", lambda: rpc_client.call("LoadFunc", 2)),
        ("设置超声波模式 1", lambda: rpc_client.call("SetSonarRGBMode", 1)),
        ("设置避障阈值 30", lambda: rpc_client.call("SetSonarDistanceThreshold", 30)),
        ("设置颜色跟踪轮状态 1", lambda: rpc_client.call("ColorTrackingWheel", 1)),
    ]
    
    for test_name, test_func in tests:
        print(f"\n{test_name}...")
        result = test_func()
        success = result.get("success", False)
        if success:
            result_data = result.get('result')
            if result_data:
                print(f"  ✓ 成功: {result_data}")
            else:
                print(f"  ✓ 成功")
        else:
            print(f"  ✗ 失败: {result.get('error')}")
    
    return True


def test_variable_parameters():
    """测试可变参数方法"""
    print("\n" + "=" * 50)
    print("测试可变参数方法")
    print("=" * 50)
    
    tests = [
        ("设置颜色检测红色", lambda: rpc_client.call("ColorDetect", "red")),
        ("设置颜色跟踪红色", lambda: rpc_client.call("ColorTracking", "red")),
        ("设置视觉巡逻红色", lambda: rpc_client.call("VisualPatrol", "red")),
        ("设置多个颜色", lambda: rpc_client.call("ColorDetect", "red", "green", "blue")),
    ]
    
    for test_name, test_func in tests:
        print(f"\n{test_name}...")
        result = test_func()
        success = result.get("success", False)
        if success:
            result_data = result.get('result')
            if result_data:
                print(f"  ✓ 成功: {result_data}")
            else:
                print(f"  ✓ 成功")
        else:
            print(f"  ✗ 失败: {result.get('error')}")
    
    return True


if __name__ == "__main__":
    # 运行测试
    print("正在连接到 RPC 服务器...")
    
    # 测试基本方法
    test_common_methods()
    
    # 测试带参数的方法
    test_with_parameters()
    
    # 测试可变参数方法
    test_variable_parameters()
    
    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)
    
    # 使用示例
    print("\n使用示例:")
    print("  from rpc import rpc_client")
    print("  # 快捷方法")
    print("  rpc_client.heartbeat()")
    print("  rpc_client.get_battery()")
    print("  rpc_client.load_function(1)")
    print("  # 通用方法（必须用位置参数）")
    print("  rpc_client.call('Heartbeat')")
    print("  rpc_client.call('LoadFunc', 1)")
    print("  rpc_client.call('SetSonarRGB', 0, 255, 0, 0)")
    print("  # 可变参数方法")
    print("  rpc_client.call('ColorDetect', 'red')")
    print("  rpc_client.call('ColorDetect', 'red', 'green')")
