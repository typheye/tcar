# ESP32 开发指南

## 固件分层

`src/main.c` 仅负责入口；`route.c` 管理 Wi-Fi、DHCP/NAT、设备发现和 HTTP；`webui.c` 提供嵌入式页面资源。

## APSTA 约束

ESP32 APSTA 共用一套射频。STA 重连会影响 SoftAP 信道，AP 有客户端时禁止主动扫描；任何扫描接口都必须返回明确的拒绝原因。

## 状态接口

`/test` 是轻量发现接口，`/api/state` 是完整管理接口。设备 IP 必须来自 DHCP/ARP 查询并通过 MAC 缓存，不能仅依赖固定回退地址。

## 构建

```powershell
$env:IDF_PATH='C:\Espressif\.espressif\v5.5.5\esp-idf'
idf.py build
idf.py monitor
```
