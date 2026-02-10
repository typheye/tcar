#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <ArduinoOTA.h>  // 添加OTA库
#include <esp_wifi.h>  // 添加WiFi相关头文件
#include <esp_netif.h>

// 引入图标数据（二进制）
extern const uint8_t favicon_ico[];
extern const size_t favicon_ico_size;

// 设置热点参数
const char* ssid = "Typheye Car 0000";
const char* password = "hitypheye";
const int max_connections = 5; // 最大连接设备数

WebServer server(80); // 创建Web服务器对象，端口80
IPAddress apIP(192, 168, 66, 1); // 固定IP地址

// LED状态控制变量
unsigned long previousMillis = 0;
int ledState = LOW;
int blinkMode = 0; // 0:长闪, 1:慢闪, 2:快闪

// 系统状态监控变量
float cpuTemperature = 0.0;
int memoryUsage = 0;
unsigned long lastStatsUpdate = 0;

// 设备MAC地址映射
struct DeviceMapping {
  const char* mac;
  const char* name;
};

DeviceMapping deviceMappings[] = {
  {"88:A2:9E:2F:EB:92", "车载设备"},
  {"D8:3A:DD:8B:32:73", "中枢主机"}
};
const int deviceMappingsCount = 2;

void setup() {
  // 初始化LED
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  
  // 开机快闪3下
  for(int i = 0; i < 3; i++) {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(200);
    digitalWrite(LED_BUILTIN, LOW);
    delay(200);
  }
  
  Serial.begin(115200);
  delay(1000);
  
  // 设置WiFi为热点模式
  WiFi.mode(WIFI_AP); // 必须同时启用 AP 和 STA
  
  // 配置固定IP
  WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0));
  // 可选：设置 DNS 为公共 DNS
  // WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0), IPAddress(8, 8, 8, 8));
  // 配置热点参数 - 明确指定使用2.4GHz频段(信道1)
  WiFi.softAP(ssid, password, 1, 0, max_connections); // 信道1，不隐藏SSID
  
  // 等待热点启动
  while (!WiFi.softAPIP()) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("\n");
  Serial.println("热点已启动!");
  Serial.print("热点IP地址: ");
  Serial.println(WiFi.softAPIP());
  Serial.print("热点SSID: ");
  Serial.println(ssid);
  Serial.print("运行频段: 2.4GHz (信道");
  Serial.print(WiFi.channel());
  Serial.println(")");
  
  // 在setup()函数中修改mDNS初始化部分
  // if (!MDNS.begin("tcar")) {
  //   Serial.println("mDNS响应器设置错误");
  // } else {
  //   Serial.println("mDNS响应器已启动，可通过 tcar.local 访问");
  //   // 明确指定在AP接口上添加服务
  //   MDNS.addService("http", "tcp", 80);
  // }
  
  // 初始化OTA
  initOTA();
  
  // 设置Web服务器路由
  server.on("/", handleRoot); // 根路径处理函数
  server.on("/favicon.ico", handleFavicon); // 图标处理
  server.on("/test", handleTest); // 新增测试接口
  server.onNotFound(handleNotFound); // 404处理
  
  // 启动Web服务器
  server.begin();
  Serial.println("HTTP服务器已启动");
  
  // 初始设置为无设备连接状态（长闪）
  setBlinkMode(0);
}

void enableNAT() {
  esp_err_t ret;
  esp_netif_t *ap_netif = esp_netif_get_handle_from_ifkey("WIFI_AP_DEF");
  esp_netif_t *sta_netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");

  if (!ap_netif || !sta_netif) {
    Serial.println("获取 netif 失败");
    return;
  }

  ret = esp_netif_set_ip_info(ap_netif, nullptr); // 可选：重置 AP IP 配置
  if (ret != ESP_OK) Serial.println("重置 AP IP 失败");

  // 启用 NAT：将 AP 流量通过 STA 转发
  ret = esp_netif_napt_enable(sta_netif);
  if (ret == ESP_OK) {
    Serial.println("NAT 已启用");
  } else if (ret == ESP_ERR_INVALID_STATE) {
    Serial.println("NAT 已经启用");
  } else {
    Serial.printf("NAT 启用失败: %d\n", ret);
  }
}

// 新增测试接口处理函数
void handleTest() {
  String jsonResponse = "{";
  
  // 状态字段
  jsonResponse += "\"status\":";
  if (blinkMode == 2) {
    jsonResponse += "-1"; // 系统启动或更新中
  } else {
    // 直接使用areAllSpecialDevicesConnected()的结果，避免重复判断
    if (areAllSpecialDevicesConnected()) {
      jsonResponse += "1"; // 设备正常运行
    } else {
      jsonResponse += "0"; // 系统待机中
    }
  }
  
  // 设备列表 - 先添加所有特殊设备
  jsonResponse += ",\"devices\":[";
  bool firstDevice = true;

  // 先添加所有特殊设备（无论是否连接）
  for (int j = 0; j < deviceMappingsCount; j++) {
      if (!firstDevice) {
          jsonResponse += ",";
      }
      firstDevice = false;
      
      // 检查该特殊设备是否已连接
      bool isConnected = false;
      int connectedDevices = WiFi.softAPgetStationNum();
      if (connectedDevices > 0) {
          wifi_sta_list_t station_list;
          esp_wifi_ap_get_sta_list(&station_list);
          
          for (int i = 0; i < connectedDevices; i++) {
              wifi_sta_info_t station = station_list.sta[i];
              char macStr[18];
              snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
                      station.mac[0], station.mac[1], station.mac[2],
                      station.mac[3], station.mac[4], station.mac[5]);
              
              if (strcmp(macStr, deviceMappings[j].mac) == 0) {
                  isConnected = true;
                  break;
              }
          }
      }
      
      jsonResponse += "{\"name\":\"" + String(deviceMappings[j].name) + "\",";
      jsonResponse += "\"mac\":\"" + String(deviceMappings[j].mac) + "\",";
      jsonResponse += "\"status\":" + String(isConnected ? "true" : "false") + "}";
      
      // 添加调试信息到串口
      Serial.print("设备 ");
      Serial.print(deviceMappings[j].name);
      Serial.print(" (");
      Serial.print(deviceMappings[j].mac);
      Serial.print(") 状态: ");
      Serial.println(isConnected ? "已连接" : "未连接");
  }

  // 再添加其他已连接的非特殊设备
  int connectedDevices = WiFi.softAPgetStationNum();
  if (connectedDevices > 0) {
      wifi_sta_list_t station_list;
      esp_wifi_ap_get_sta_list(&station_list);
      
      for (int i = 0; i < connectedDevices; i++) {
          wifi_sta_info_t station = station_list.sta[i];
          char macStr[18];
          snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
                  station.mac[0], station.mac[1], station.mac[2],
                  station.mac[3], station.mac[4], station.mac[5]);
          
          // 检查是否为特殊设备，如果不是则添加
          bool isSpecialDevice = false;
          for (int j = 0; j < deviceMappingsCount; j++) {
              if (strcmp(macStr, deviceMappings[j].mac) == 0) {
                  isSpecialDevice = true;
                  break;
              }
          }
          
          if (!isSpecialDevice) {
              if (!firstDevice) {
                  jsonResponse += ",";
              }
              firstDevice = false;
              
              jsonResponse += "{\"name\":\"其他设备\",";
              jsonResponse += "\"mac\":\"" + String(macStr) + "\",";
              jsonResponse += "\"status\":true}";
          }
      }
  }
  jsonResponse += "]";
  
  // ESP温度
  jsonResponse += ",\"esptemp\":\"" + String(cpuTemperature, 1) + "\"";
  
  jsonResponse += "}";
  
  server.send(200, "application/json", jsonResponse);
}

// 更新系统状态信息
void updateSystemStats() {
  // 获取温度（ESP32-S3有温度传感器）
  cpuTemperature = temperatureRead();
  
  // 计算内存使用率
  uint32_t freeHeap = esp_get_free_heap_size();
  uint32_t totalHeap = esp_get_minimum_free_heap_size() + freeHeap;
  memoryUsage = 100 - (freeHeap * 100 / totalHeap);
}

// 图标处理函数
void handleFavicon() {
  server.send_P(200, "image/x-icon", (const char*)favicon_ico, favicon_ico_size);
}

// 初始化OTA函数
void initOTA() {
  // 设置OTA主机名（与mDNS一致）
  ArduinoOTA.setHostname("tcar");
  // 确保OTA在所有网络接口上工作
  ArduinoOTA.begin();
  
  // 设置OTA验证密码（可选）
  // ArduinoOTA.setPassword("admin");
  
  // OTA开始时的回调函数
  ArduinoOTA.onStart([]() {
    String type;
    if (ArduinoOTA.getCommand() == U_FLASH) {
      type = "sketch";
    } else { // U_SPIFFS
      type = "filesystem";
    }
    
    // 注意：如果更新SPIFFS，需要先卸载文件系统
    Serial.println("开始OTA更新: " + type);
    setBlinkMode(2); // 进入快闪模式表示正在更新
  });
  
  // OTA结束时的回调函数
  ArduinoOTA.onEnd([]() {
    Serial.println("\nOTA更新完成");
    // 更新完成后重启
    Serial.println("准备重启...");
  });
  
  // OTA进度回调函数
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("更新进度: %u%%\r", (progress / (total / 100)));
  });
  
  // OTA错误回调函数
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("错误[%u]: ", error);
    if (error == OTA_AUTH_ERROR) {
      Serial.println("认证失败");
    } else if (error == OTA_BEGIN_ERROR) {
      Serial.println("开始失败");
    } else if (error == OTA_CONNECT_ERROR) {
      Serial.println("连接失败");
    } else if (error == OTA_RECEIVE_ERROR) {
      Serial.println("接收失败");
    } else if (error == OTA_END_ERROR) {
      Serial.println("结束失败");
    }
    // 发生错误后恢复原来的LED模式
    int connectedDevices = WiFi.softAPgetStationNum();
    setBlinkMode(connectedDevices == 0 ? 0 : 1);
  });
  
  // 开始OTA服务
  ArduinoOTA.begin();
  Serial.println("OTA服务已启动");
  Serial.print("IP地址: ");
  Serial.println(WiFi.softAPIP());
}

void loop() {
  // 监控设备连接状态变化
  static int lastConnectedCount = 0;
  int currentConnectedCount = WiFi.softAPgetStationNum();
  
  if (currentConnectedCount != lastConnectedCount) {
    Serial.print("连接设备数量变化: ");
    Serial.print(lastConnectedCount);
    Serial.print(" -> ");
    Serial.println(currentConnectedCount);
    lastConnectedCount = currentConnectedCount;
    
    // 打印当前连接的设备MAC地址
    if (currentConnectedCount > 0) {
      wifi_sta_list_t station_list;
      esp_wifi_ap_get_sta_list(&station_list);
      Serial.println("当前连接的设备:");
      for (int i = 0; i < currentConnectedCount; i++) {
        wifi_sta_info_t station = station_list.sta[i];
        char macStr[18];
        snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
                station.mac[0], station.mac[1], station.mac[2],
                station.mac[3], station.mac[4], station.mac[5]);
        Serial.println(macStr);
      }
    }
  }

  server.handleClient(); // 处理客户端请求
  ArduinoOTA.handle();   // 处理OTA请求

  // 每2秒更新一次系统状态
  if (millis() - lastStatsUpdate >= 2000) {
    updateSystemStats();
    lastStatsUpdate = millis();
  }
  
  // 根据连接设备数量和特殊设备连接状态更新LED模式
  int connectedDevices = WiFi.softAPgetStationNum();
  if (connectedDevices == 0 || !areAllSpecialDevicesConnected()) {
    setBlinkMode(0); // 无设备连接或特殊设备未全部连接，长闪（待机中）
  } else {
    setBlinkMode(1); // 有设备连接且特殊设备全部连接，慢闪（运行中）
  }
    
  // 更新LED状态
  updateLED();
}

// 设置LED闪烁模式
void setBlinkMode(int mode) {
  if (blinkMode != mode) {
    blinkMode = mode;
    previousMillis = millis();
    
    // 立即应用新模式
    switch(blinkMode) {
      case 0: // 长闪
        digitalWrite(LED_BUILTIN, HIGH);
        ledState = HIGH;
        break;
      case 1: // 慢闪 (500ms)
      case 2: // 快闪 (200ms)
        digitalWrite(LED_BUILTIN, LOW);
        ledState = LOW;
        break;
    }
    
    Serial.print("LED模式改变: ");
    switch(blinkMode) {
      case 0: Serial.println("长闪"); break;
      case 1: Serial.println("慢闪"); break;
      case 2: Serial.println("快闪"); break;
    }
  }
}

// 更新LED状态
void updateLED() {
  unsigned long currentMillis = millis();
  
  switch(blinkMode) {
    case 0: // 等待，300ms间隔
      if (currentMillis - previousMillis >= 300) {
        previousMillis = currentMillis;
        ledState = !ledState;
        digitalWrite(LED_BUILTIN, ledState);
      }
      break;
      
    case 1: // 慢闪，2000ms间隔
      if (currentMillis - previousMillis >= 2000) {
        previousMillis = currentMillis;
        ledState = !ledState;
        digitalWrite(LED_BUILTIN, ledState);
      }
      break;
      
    case 2: // 快闪，100ms间隔
      if (currentMillis - previousMillis >= 50) {
        previousMillis = currentMillis;
        ledState = !ledState;
        digitalWrite(LED_BUILTIN, ledState);
      }
      break;
  }
}

// 根路径处理函数
void handleRoot() {
  String html = "<!DOCTYPE html><html><head>";
  html += "<meta charset='UTF-8'>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1.0'>";
  html += "<link rel='icon' type='image/x-icon' href='/favicon.ico'>";
  html += "<title>Typheye Car</title>";
  html += "<style>";
  html += "body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }";
  html += ".container { background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }";
  html += "h1 { color: #333; }";
  html += "table { width: 100%; border-collapse: collapse; margin-top: 20px; }";
  html += "th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }";
  html += "th { background-color: #f2f2f2; }";
  html += ".status { padding: 8px 15px; border-radius: 5px; font-weight: bold; }";
  html += ".connected { background-color: #d4edda; color: #155724; }";
  html += ".disconnected { background-color: #f8d7da; color: #721c24; }";
  html += ".led-status { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }";
  html += ".led-on { background-color: #28a745; box-shadow: 0 0 8px #28a745; }";
  html += ".led-off { background-color: #6c757d; }";
  html += ".led-blinking { background-color: #ffc107; box-shadow: 0 0 8px #ffc107; animation: blink 1s infinite; }";
  html += ".led-fast-blinking { background-color: #dc3545; box-shadow: 0 0 8px #dc3545; animation: blink 0.4s infinite; }";
  html += ".ota-section { margin-top: 30px; padding: 20px; background-color: #e9ecef; border-radius: 8px; }";
  html += ".wifi-section { margin-top: 30px; padding: 20px; background-color: #e9ecef; border-radius: 8px; }";
  html += ".ota-button, .wifi-button { width: 100%; background-color: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 15px; }";
  html += ".ota-button:hover, .wifi-button:hover { background-color: #0069d9; }";
  html += ".switch { position: relative; display: inline-block; width: 60px; height: 34px; margin-left: 15px; }";
  html += ".switch input { opacity: 0; width: 0; height: 0; }";
  html += ".slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; }";
  html += ".slider:before { position: absolute; content: \"\"; height: 26px; width: 26px; left: 4px; bottom: 4px; background-color: white; transition: .4s; }";
  html += "input:checked + .slider { background-color: #2196F3; }";
  html += "input:checked + .slider:before { transform: translateX(26px); }";
  html += ".slider.round { border-radius: 34px; }";
  html += ".slider.round:before { border-radius: 50%; }";
  html += ".wifi-form { display: none; margin-top: 20px; }";
  html += ".form-group { margin-bottom: 15px; }";
  html += ".form-group label { display: block; margin-bottom: 5px; font-weight: bold; }";
  html += ".form-group input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }";
  html += "</style>";
  html += "</head><body>";
  html += "<div class='container'>";
  html += "<h1>Typheye Car</h1>";
  
  // 显示LED状态
  int connectedDevices = WiFi.softAPgetStationNum();
  html += "<p><strong>状态: </strong>";
  if (connectedDevices == 0 || !areAllSpecialDevicesConnected()) {
    html += "待机中  <span class='led-status led-blinking'></span>";
  } else {
    html += "运行中  <span class='led-status led-on'></span>";
  }
  html += "</p>";
  
  html += "<p><strong>温度:</strong> " + String(cpuTemperature, 1) + " °C</p>";
  html += "<p><strong>内存:</strong> " + String(memoryUsage) + "%</p>";
  html += "<p><strong>名称:</strong> " + String(ssid) + "</p>";
  html += "<p><strong>地址:</strong> " + WiFi.softAPIP().toString() + "</p>";
  html += "<p><strong>频段:</strong> 2.4GHz (信道" + String(WiFi.channel()) + ")</p>";
  html += "<p><strong>设备:</strong> " + String(connectedDevices) + "/" + String(max_connections) + "</p>";
  
  // 显示连接设备信息
  html += "<table>";
  html += "<tr><th>设备名称</th><th>MAC地址</th><th>状态</th></tr>";

  // 先显示所有特殊设备（无论是否连接）
  for (int j = 0; j < deviceMappingsCount; j++) {
    bool isConnected = false;
    char connectedMacStr[18] = "";
    
    // 检查该特殊设备是否已连接
    if (connectedDevices > 0) {
      wifi_sta_list_t station_list;
      esp_wifi_ap_get_sta_list(&station_list);
      
      for (int i = 0; i < connectedDevices; i++) {
        wifi_sta_info_t station = station_list.sta[i];
        char macStr[18];
        snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
                station.mac[0], station.mac[1], station.mac[2],
                station.mac[3], station.mac[4], station.mac[5]);
        
        if (strcmp(macStr, deviceMappings[j].mac) == 0) {
          isConnected = true;
          strcpy(connectedMacStr, macStr);
          break;
        }
      }
    }
    
    // 显示特殊设备
    html += "<tr>";
    html += "<td>" + String(deviceMappings[j].name) + "</td>";
    html += "<td>" + String(deviceMappings[j].mac) + "</td>";
    if (isConnected) {
      html += "<td><span class='status connected'>已连接</span></td>";
    } else {
      html += "<td><span class='status' style='background-color: #f8d7da; color: #721c24;'>未连接</span></td>";
    }
    html += "</tr>";
  }

  // 再显示其他已连接设备
  if (connectedDevices > 0) {
    wifi_sta_list_t station_list;
    esp_wifi_ap_get_sta_list(&station_list);
    
    int otherDeviceCount = 1;
    
    for (int i = 0; i < connectedDevices; i++) {
      wifi_sta_info_t station = station_list.sta[i];
      char macStr[18];
      snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
              station.mac[0], station.mac[1], station.mac[2],
              station.mac[3], station.mac[4], station.mac[5]);
      
      // 检查是否为特殊设备，如果不是则显示
      bool isSpecialDevice = false;
      for (int j = 0; j < deviceMappingsCount; j++) {
        if (strcmp(macStr, deviceMappings[j].mac) == 0) {
          isSpecialDevice = true;
          break;
        }
      }
      
      if (!isSpecialDevice) {
        html += "<tr>";
        html += "<td>其他设备" + String(otherDeviceCount++) + "</td>";
        html += "<td>" + String(macStr) + "</td>";
        html += "<td><span class='status connected'>已连接</span></td>";
        html += "</tr>";
      }
    }
  }

  // 如果没有其他设备连接，显示提示
  if (connectedDevices == 0 || 
      (connectedDevices > 0 && WiFi.softAPgetStationNum() <= deviceMappingsCount)) {
    html += "<tr><td colspan='3' style='text-align: center;'>暂无其他设备连接</td></tr>";
  }

  html += "</table>";
  
  // OTA更新模块
  html += "<div class='ota-section'>";
  html += "<h2>OTA</h2>";
  html += "<p><strong>状态:</strong> 已启用</p>";
  html += "<p><strong>主机:</strong> tcar.local</p>";
  html += "<p><strong>端口:</strong> 3232</p>";
  html += "<p>使用Arduino IDE进行OTA更新:</p>";
  html += "<ol>";
  html += "<li>确保您的计算机已连接到此热点</li>";
  html += "<li>在Arduino IDE中选择工具 → 端口 → tcar.local</li>";
  html += "<li>使用\"上传\"按钮进行OTA更新</li>";
  html += "</ol>";
  html += "<p style='color: #856404; background-color: #fff3cd; padding: 10px; border-radius: 4px;'>";
  html += "注意: OTA更新期间请勿断开电源，更新过程大约需要10-30秒";
  html += "</p>";
  html += "</div>";
  
  // LED状态说明
  html += "<div style='margin-top: 30px; padding: 15px; background-color: #f8f9fa; border-radius: 5px;'>";
  html += "<h3>LED状态指示</h3>";
  html += "<ul style='list-style-type: none; padding: 0;'>";
  html += "<li>慢闪  <span class='led-status led-on'></span> - 已有设备连接，系统运行中</li>";
  html += "<li>长闪  <span class='led-status led-blinking'></span> - 无设备连接，待机中</li>";
  html += "<li>快闪  <span class='led-status led-fast-blinking'></span> - 系统启动中或OTA更新中</li>";
  html += "</ul>";
  html += "</div>";
  
  html += "<style>";
  html += "@keyframes blink { ";
  html += "  0%, 100% { opacity: 1; }";
  html += "  50% { opacity: 0.3; }";
  html += "}";
  html += "</style>";
  
  html += "<p style='margin-top: 20px; font-size: 0.9em; color: #666;'>系统已运行: " + getTimeString() + "</p>";
  html += "</div></body></html>";
  
  server.send(200, "text/html", html);
}

// 404处理函数
void handleNotFound() {
  String message = "404 Not Found\n\n";
  message += "URI: ";
  message += server.uri();
  message += "\nMethod: ";
  message += (server.method() == HTTP_GET) ? "GET" : "POST";
  message += "\nParam: ";
  message += server.args();
  message += "\n";
  
  for (uint8_t i = 0; i < server.args(); i++) {
    message += " " + server.argName(i) + ": " + server.arg(i) + "\n";
  }
  
  server.send(404, "text/plain", message);
}

// 获取时间字符串函数
String getTimeString() {
  unsigned long seconds = millis() / 1000;
  unsigned long minutes = seconds / 60;
  unsigned long hours = minutes / 60;
  seconds %= 60;
  minutes %= 60;
  
  char timeString[20];
  snprintf(timeString, sizeof(timeString), "%02lu:%02lu:%02lu", hours, minutes, seconds);
  return String(timeString);
}

// 检查特殊设备是否全部连接
bool areAllSpecialDevicesConnected() {
  int currentConnectedDevices = WiFi.softAPgetStationNum();
  if (currentConnectedDevices == 0) return false;
  
  wifi_sta_list_t station_list;
  esp_wifi_ap_get_sta_list(&station_list);
  
  int connectedSpecialDevices = 0;
  
  for (int j = 0; j < deviceMappingsCount; j++) {
    for (int i = 0; i < currentConnectedDevices; i++) {
      wifi_sta_info_t station = station_list.sta[i];
      char macStr[18];
      snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
              station.mac[0], station.mac[1], station.mac[2],
              station.mac[3], station.mac[4], station.mac[5]);
      
      if (strcmp(macStr, deviceMappings[j].mac) == 0) {
        connectedSpecialDevices++;
        break;
      }
    }
  }
  
  return (connectedSpecialDevices == deviceMappingsCount);
}