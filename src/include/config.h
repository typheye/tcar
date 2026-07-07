#pragma once

#define AP_SSID "Typheye Car 0000"
#define AP_PASS "hitypheye"
#define AP_IP "192.168.66.1"
#define AP_CHANNEL 1
#define AP_MAX_CONN 5
#define WIFI_PROFILE_MAX 5
#define WIFI_RETRY_LIMIT 2
#define DHCPS_OFFER_DNS 0x02
#define LED_DUTY_MAX 8191

#ifndef CONFIG_TCAR_LED_GPIO
#define CONFIG_TCAR_LED_GPIO 21
#endif
#ifndef CONFIG_TCAR_LED_ACTIVE_LOW
#define CONFIG_TCAR_LED_ACTIVE_LOW 1
#endif

