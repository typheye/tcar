#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_wifi_ap_get_sta_list.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/temperature_sensor.h"
#include "lwip/ip4_addr.h"
#include "favicon.h"
#include "web_ui.h"
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
#define CONFIG_TCAR_LED_GPIO 38
#endif
#ifndef CONFIG_TCAR_LED_ACTIVE_LOW
#define CONFIG_TCAR_LED_ACTIVE_LOW 0
#endif
static const char *TAG = "tcar-idf";
static EventGroupHandle_t eg;
static esp_netif_t *apif, *staif;
static httpd_handle_t httpd;
static temperature_sensor_handle_t tsens;
typedef struct
{
    bool valid;
    char ssid[33];
    char pass[65];
} wifi_profile_t;
typedef struct
{
    const char *mac;
    const char *zh;
    const char *en;
} devmap_t;
static wifi_profile_t prof[WIFI_PROFILE_MAX];
static int prof_count, active_prof = -1, sta_retry, blink_mode, led_ready;
static bool sta_connected, nat_enabled, sta_manual_disconnect;
static esp_netif_ip_info_t sta_ip;
static float cpu_temp;
static int mem_usage;
static bool share_wlan;
static bool led_enabled = true;
static char ui_lang[8] = "auto";
static const devmap_t devs[] = {{"88:A2:9E:2F:EB:92", "车载设备", "Car device"}, {"D8:3A:DD:8B:32:73", "中枢主机", "Core host"}};
static bool en_req(httpd_req_t *r) { return strstr(r->uri, "lang=en") != NULL; }
static const char *lc(bool en) { return en ? "en" : "zh"; }
static const char *T(bool en, const char *z, const char *e) { return en ? e : z; }
static int count_prof(void)
{
    int c = 0;
    for (int i = 0; i < WIFI_PROFILE_MAX; i++)
        if (prof[i].valid && prof[i].ssid[0])
            c++;
    return c;
}
static int first_prof(int start)
{
    for (int n = 0; n < WIFI_PROFILE_MAX; n++)
    {
        int i = (start + n + WIFI_PROFILE_MAX) % WIFI_PROFILE_MAX;
        if (prof[i].valid && prof[i].ssid[0])
            return i;
    }
    return -1;
}
static void compact_prof(void)
{
    wifi_profile_t t[WIFI_PROFILE_MAX] = {0};
    int o = 0;
    for (int i = 0; i < WIFI_PROFILE_MAX; i++)
        if (prof[i].valid && prof[i].ssid[0] && o < WIFI_PROFILE_MAX)
            t[o++] = prof[i];
    memcpy(prof, t, sizeof(prof));
    prof_count = o;
}
static void load_profiles(void)
{
    memset(prof, 0, sizeof(prof));
    nvs_handle_t n;
    if (nvs_open("wifi", NVS_READONLY, &n) != ESP_OK)
        return;
    for (int i = 0; i < WIFI_PROFILE_MAX; i++)
    {
        char k[16];
        size_t l = sizeof(prof[i].ssid);
        snprintf(k, sizeof(k), "s%d", i);
        if (nvs_get_str(n, k, prof[i].ssid, &l) == ESP_OK && prof[i].ssid[0])
        {
            l = sizeof(prof[i].pass);
            snprintf(k, sizeof(k), "p%d", i);
            if (nvs_get_str(n, k, prof[i].pass, &l) != ESP_OK)
                prof[i].pass[0] = 0;
            prof[i].valid = true;
        }
    }
    if (count_prof() == 0)
    {
        size_t l = sizeof(prof[0].ssid);
        if (nvs_get_str(n, "ssid", prof[0].ssid, &l) == ESP_OK && prof[0].ssid[0])
        {
            l = sizeof(prof[0].pass);
            if (nvs_get_str(n, "pass", prof[0].pass, &l) != ESP_OK)
                prof[0].pass[0] = 0;
            prof[0].valid = true;
        }
    }
    nvs_close(n);
    compact_prof();
}
static esp_err_t save_profiles(void)
{
    compact_prof();
    nvs_handle_t n;
    ESP_RETURN_ON_ERROR(nvs_open("wifi", NVS_READWRITE, &n), TAG, "nvs");
    esp_err_t e = ESP_OK;
    for (int i = 0; i < WIFI_PROFILE_MAX && e == ESP_OK; i++)
    {
        char k[16];
        snprintf(k, sizeof(k), "s%d", i);
        e = nvs_erase_key(n, k);
        if (e == ESP_ERR_NVS_NOT_FOUND)
            e = ESP_OK;
        snprintf(k, sizeof(k), "p%d", i);
        if (e == ESP_OK)
            e = nvs_erase_key(n, k);
        if (e == ESP_ERR_NVS_NOT_FOUND)
            e = ESP_OK;
    }
    for (int i = 0; i < prof_count && e == ESP_OK; i++)
    {
        char k[16];
        snprintf(k, sizeof(k), "s%d", i);
        e = nvs_set_str(n, k, prof[i].ssid);
        if (e == ESP_OK)
        {
            snprintf(k, sizeof(k), "p%d", i);
            e = nvs_set_str(n, k, prof[i].pass);
        }
    }
    if (e == ESP_OK)
        e = nvs_commit(n);
    nvs_close(n);
    return e;
}
static void set_blink_mode(int m)
{
    if (blink_mode != m)
    {
        ESP_LOGI(TAG, "LED mode %d -> %d", blink_mode, m);
        blink_mode = m;
    }
}
static void led_write(int d)
{
    if (!led_ready)
        return;
    if (d < 0)
        d = 0;
    if (d > LED_DUTY_MAX)
        d = LED_DUTY_MAX;
    if (CONFIG_TCAR_LED_ACTIVE_LOW)
        d = LED_DUTY_MAX - d;
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, d);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}
static void led_task(void *a)
{
    ledc_timer_config_t t = {.speed_mode = LEDC_LOW_SPEED_MODE, .duty_resolution = LEDC_TIMER_13_BIT, .timer_num = LEDC_TIMER_0, .freq_hz = 1000, .clk_cfg = LEDC_AUTO_CLK};
    ledc_channel_config_t c = {.gpio_num = CONFIG_TCAR_LED_GPIO, .speed_mode = LEDC_LOW_SPEED_MODE, .channel = LEDC_CHANNEL_0, .intr_type = LEDC_INTR_DISABLE, .timer_sel = LEDC_TIMER_0, .duty = 0, .hpoint = 0};
    led_ready = (ledc_timer_config(&t) == ESP_OK && ledc_channel_config(&c) == ESP_OK);
    for (int i = 0; i < 3; i++)
    {
        led_write(LED_DUTY_MAX);
        vTaskDelay(pdMS_TO_TICKS(120));
        led_write(0);
        vTaskDelay(pdMS_TO_TICKS(120));
    }
    while (1)
    {
        if (!led_enabled) { led_write(0); vTaskDelay(pdMS_TO_TICKS(200)); continue; }
        int p = 1800, lo = 120, hi = 6500;
        if (blink_mode == 1)
        {
            p = 3200;
            lo = 250;
            hi = 3600;
        }
        else if (blink_mode == 2)
        {
            p = 420;
            lo = 0;
            hi = LED_DUTY_MAX;
        }
        int ph = (int)((esp_timer_get_time() / 1000ULL) % p), h = p / 2, x = ph < h ? ph : p - ph;
        led_write(lo + (hi - lo) * x / h);
        vTaskDelay(pdMS_TO_TICKS(24));
    }
}
static void stats_task(void *a)
{
    temperature_sensor_config_t cfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(10, 80);
    if (temperature_sensor_install(&cfg, &tsens) == ESP_OK)
        temperature_sensor_enable(tsens);
    while (1)
    {
        float t;
        if (tsens && temperature_sensor_get_celsius(tsens, &t) == ESP_OK)
            cpu_temp = t;
        uint32_t f = esp_get_free_heap_size(), m = esp_get_minimum_free_heap_size(), tot = f + m;
        mem_usage = tot ? (int)(100 - f * 100 / tot) : 0;
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}
static void ap_dns_from_sta(void)
{
    esp_netif_dns_info_t dns;
    esp_err_t e = esp_netif_get_dns_info(staif, ESP_NETIF_DNS_MAIN, &dns);
    if (e != ESP_OK || dns.ip.u_addr.ip4.addr == 0)
        dns.ip = (esp_ip_addr_t)ESP_IP4ADDR_INIT(223, 5, 5, 5);
    uint8_t opt = DHCPS_OFFER_DNS;
    ESP_ERROR_CHECK_WITHOUT_ABORT(esp_netif_dhcps_stop(apif));
    ESP_ERROR_CHECK_WITHOUT_ABORT(esp_netif_dhcps_option(apif, ESP_NETIF_OP_SET, ESP_NETIF_DOMAIN_NAME_SERVER, &opt, sizeof(opt)));
    ESP_ERROR_CHECK_WITHOUT_ABORT(esp_netif_set_dns_info(apif, ESP_NETIF_DNS_MAIN, &dns));
    ESP_ERROR_CHECK_WITHOUT_ABORT(esp_netif_dhcps_start(apif));
    ESP_LOGI(TAG, "AP DHCP DNS set to " IPSTR, IP2STR(&dns.ip.u_addr.ip4));
}
static void disable_nat(void)
{
    if (nat_enabled && apif)
        ESP_ERROR_CHECK_WITHOUT_ABORT(esp_netif_napt_disable(apif));
    nat_enabled = false;
}
static void enable_nat(void)
{
    if (!sta_connected || nat_enabled || !apif || !staif)
        return;
    esp_netif_set_default_netif(staif);
    ap_dns_from_sta();
    esp_err_t e = esp_netif_napt_enable(apif);
    if (e == ESP_OK || e == ESP_ERR_INVALID_STATE)
    {
        nat_enabled = true;
        ESP_LOGI(TAG, "NAPT enabled on SoftAP interface");
    }
    else
        ESP_LOGE(TAG, "NAPT enable failed: %s", esp_err_to_name(e));
}
static void connect_profile(int i)
{
    if (i < 0 || i >= WIFI_PROFILE_MAX || !prof[i].valid || !prof[i].ssid[0])
        return;
    wifi_config_t c = {0};
    strlcpy((char *)c.sta.ssid, prof[i].ssid, sizeof(c.sta.ssid));
    strlcpy((char *)c.sta.password, prof[i].pass, sizeof(c.sta.password));
    c.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    c.sta.threshold.authmode = WIFI_AUTH_OPEN;
    c.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    c.sta.failure_retry_cnt = 1;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &c));
    active_prof = i;
    sta_retry = 0;
    sta_connected = false;
    disable_nat();
    ESP_LOGI(TAG, "Connecting STA profile %d/%d to '%s'", i + 1, prof_count, prof[i].ssid);
    esp_wifi_connect();
}
static void connect_first(void)
{
    if (!share_wlan) return;
    int i = first_prof(0);
    if (i >= 0)
        connect_profile(i);
}
static void connect_next(void)
{
    int i = first_prof(active_prof + 1);
    if (i >= 0)
        connect_profile(i);
}
static void wifi_evt(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT)
    {
        if (id == WIFI_EVENT_STA_START)
            connect_first();
        else if (id == WIFI_EVENT_STA_DISCONNECTED)
        {
            sta_connected = false;
            disable_nat();
            if (share_wlan && !sta_manual_disconnect && prof_count)
            {
                if (++sta_retry < WIFI_RETRY_LIMIT)
                {
                    ESP_LOGW(TAG, "STA retry current profile");
                    esp_wifi_connect();
                }
                else
                {
                    ESP_LOGW(TAG, "STA try next profile");
                    connect_next();
                }
            }
        }
    }
    else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP)
    {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;
        sta_connected = true;
        sta_retry = 0;
        sta_ip = e->ip_info;
        ESP_LOGI(TAG, "STA got IP: " IPSTR " gw: " IPSTR, IP2STR(&e->ip_info.ip), IP2STR(&e->ip_info.gw));
        enable_nat();
    }
}
static void load_settings(void)
{
    nvs_handle_t n;
    share_wlan = false;
    led_enabled = true;
    strlcpy(ui_lang, "auto", sizeof(ui_lang));
    if (nvs_open("app", NVS_READONLY, &n) != ESP_OK) return;
    uint8_t v;
    if (nvs_get_u8(n, "share", &v) == ESP_OK) share_wlan = v;
    if (nvs_get_u8(n, "led", &v) == ESP_OK) led_enabled = v;
    size_t l = sizeof(ui_lang);
    nvs_get_str(n, "lang", ui_lang, &l);
    nvs_close(n);
}
static esp_err_t save_settings(void)
{
    nvs_handle_t n;
    ESP_RETURN_ON_ERROR(nvs_open("app", NVS_READWRITE, &n), TAG, "app nvs");
    esp_err_t e = nvs_set_u8(n, "share", share_wlan ? 1 : 0);
    if (e == ESP_OK) e = nvs_set_u8(n, "led", led_enabled ? 1 : 0);
    if (e == ESP_OK) e = nvs_set_str(n, "lang", ui_lang);
    if (e == ESP_OK) e = nvs_commit(n);
    nvs_close(n);
    return e;
}
static void init_wifi(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    eg = xEventGroupCreate();
    apif = esp_netif_create_default_wifi_ap();
    staif = esp_netif_create_default_wifi_sta();
    esp_netif_ip_info_t ip;
    IP4_ADDR(&ip.ip, 192, 168, 66, 1);
    IP4_ADDR(&ip.gw, 192, 168, 66, 1);
    IP4_ADDR(&ip.netmask, 255, 255, 255, 0);
    ESP_ERROR_CHECK(esp_netif_dhcps_stop(apif));
    ESP_ERROR_CHECK(esp_netif_set_ip_info(apif, &ip));
    uint8_t opt = DHCPS_OFFER_DNS;
    esp_netif_dns_info_t dns = {.ip = ESP_IP4ADDR_INIT(223, 5, 5, 5)};
    ESP_ERROR_CHECK(esp_netif_dhcps_option(apif, ESP_NETIF_OP_SET, ESP_NETIF_DOMAIN_NAME_SERVER, &opt, sizeof(opt)));
    ESP_ERROR_CHECK(esp_netif_set_dns_info(apif, ESP_NETIF_DNS_MAIN, &dns));
    ESP_ERROR_CHECK(esp_netif_dhcps_start(apif));
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_evt, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_evt, NULL, NULL));
    load_settings();
    load_profiles();
    wifi_config_t ap = {0};
    strlcpy((char *)ap.ap.ssid, AP_SSID, sizeof(ap.ap.ssid));
    strlcpy((char *)ap.ap.password, AP_PASS, sizeof(ap.ap.password));
    ap.ap.ssid_len = strlen(AP_SSID);
    ap.ap.channel = AP_CHANNEL;
    ap.ap.max_connection = AP_MAX_CONN;
    ap.ap.authmode = WIFI_AUTH_WPA_WPA2_PSK;
    ap.ap.pmf_cfg.required = false;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "AP started: %s ip=%s profiles=%d", AP_SSID, AP_IP, prof_count);
}
static bool mac_eq(const uint8_t m[6], const char *s)
{
    char b[18];
    snprintf(b, sizeof(b), "%02X:%02X:%02X:%02X:%02X:%02X", m[0], m[1], m[2], m[3], m[4], m[5]);
    return strcmp(b, s) == 0;
}
static bool special(const uint8_t m[6])
{
    for (size_t i = 0; i < sizeof(devs) / sizeof(devs[0]); i++)
        if (mac_eq(m, devs[i].mac))
            return true;
    return false;
}
static bool all_special(void)
{
    wifi_sta_list_t l;
    if (esp_wifi_ap_get_sta_list(&l) != ESP_OK || l.num == 0)
        return false;
    for (size_t d = 0; d < sizeof(devs) / sizeof(devs[0]); d++)
    {
        bool f = false;
        for (int i = 0; i < l.num; i++)
            if (mac_eq(l.sta[i].mac, devs[d].mac))
            {
                f = true;
                break;
            }
        if (!f)
            return false;
    }
    return true;
}
static const esp_ip4_addr_t *ip_for(const wifi_sta_mac_ip_list_t *ips, const uint8_t m[6])
{
    for (int i = 0; i < ips->num; i++)
        if (memcmp(ips->sta[i].mac, m, 6) == 0)
            return &ips->sta[i].ip;
    return NULL;
}
static void urldecode(char *s)
{
    char *o = s;
    for (char *p = s; *p; p++)
    {
        if (*p == '+')
            *o++ = ' ';
        else if (*p == '%' && isxdigit((unsigned char)p[1]) && isxdigit((unsigned char)p[2]))
        {
            char h[3] = {p[1], p[2], 0};
            *o++ = (char)strtol(h, NULL, 16);
            p += 2;
        }
        else
            *o++ = *p;
    }
    *o = 0;
}
static void formv(const char *b, const char *k, char *out, size_t n)
{
    out[0] = 0;
    size_t kl = strlen(k);
    const char *p = b;
    while (p && *p)
    {
        if (strncmp(p, k, kl) == 0 && p[kl] == '=')
        {
            p += kl + 1;
            const char *e = strchr(p, '&');
            size_t l = e ? (size_t)(e - p) : strlen(p);
            if (l >= n)
                l = n - 1;
            memcpy(out, p, l);
            out[l] = 0;
            urldecode(out);
            return;
        }
        p = strchr(p, '&');
        if (p)
            p++;
    }
}
static int formi(const char *b, const char *k, int f)
{
    char x[16];
    formv(b, k, x, sizeof(x));
    return x[0] ? atoi(x) : f;
}
static esp_err_t favicon_handler(httpd_req_t *r)
{
    httpd_resp_set_type(r, "image/png");
    httpd_resp_send(r, (const char *)favicon_ico, favicon_ico_size);
    return ESP_OK;
}
static esp_err_t test_handler(httpd_req_t *r)
{
    wifi_sta_list_t l = {0};
    wifi_sta_mac_ip_list_t ips = {0};
    esp_wifi_ap_get_sta_list(&l);
    esp_wifi_ap_get_sta_list_with_ip(&l, &ips);
    char *j = calloc(1, 6144);
    if (!j)
        return httpd_resp_send_500(r);
    size_t o = 0;
    o += snprintf(j + o, 6144 - o, "{\"status\":%d,\"esptemp\":\"%.1f\",\"memory\":%d,\"ap\":{\"ssid\":\"%s\",\"ip\":\"%s\",\"clients\":%u},\"sta\":{\"connected\":%s,\"ssid\":\"%s\",\"ip\":\"" IPSTR "\",\"nat\":%s,\"profiles\":%d},\"devices\":[", all_special() ? 1 : 0, cpu_temp, mem_usage, AP_SSID, AP_IP, l.num, sta_connected ? "true" : "false", (active_prof >= 0 && prof[active_prof].valid) ? prof[active_prof].ssid : "", IP2STR(&sta_ip.ip), nat_enabled ? "true" : "false", prof_count);
    bool first = true;
    for (size_t d = 0; d < sizeof(devs) / sizeof(devs[0]); d++)
    {
        bool c = false;
        const esp_ip4_addr_t *ip = NULL;
        for (int i = 0; i < l.num; i++)
            if (mac_eq(l.sta[i].mac, devs[d].mac))
            {
                c = true;
                ip = ip_for(&ips, l.sta[i].mac);
                break;
            }
        o += snprintf(j + o, 6144 - o, "%s{\"name\":\"%s\",\"mac\":\"%s\",\"ip\":\"%s\",\"status\":%s}", first ? "" : ",", devs[d].en, devs[d].mac, ip ? ip4addr_ntoa((const ip4_addr_t *)ip) : "-", c ? "true" : "false");
        first = false;
    }
    for (int i = 0; i < l.num; i++)
    {
        if (special(l.sta[i].mac))
            continue;
        char m[18];
        snprintf(m, sizeof(m), "%02X:%02X:%02X:%02X:%02X:%02X", l.sta[i].mac[0], l.sta[i].mac[1], l.sta[i].mac[2], l.sta[i].mac[3], l.sta[i].mac[4], l.sta[i].mac[5]);
        const esp_ip4_addr_t *ip = ip_for(&ips, l.sta[i].mac);
        o += snprintf(j + o, 6144 - o, "%s{\"name\":\"Other device\",\"mac\":\"%s\",\"ip\":\"%s\",\"status\":true}", first ? "" : ",", m, ip ? ip4addr_ntoa((const ip4_addr_t *)ip) : "-");
        first = false;
    }
    snprintf(j + o, 6144 - o, "]}");
    httpd_resp_set_type(r, "application/json");
    httpd_resp_sendstr(r, j);
    free(j);
    return ESP_OK;
}
static void redir(httpd_req_t *r, bool en, const char *m)
{
    char h[220];
    snprintf(h, sizeof(h), "<!doctype html><meta charset='utf-8'><meta http-equiv='refresh' content='1;url=/?lang=%s'><body>%s</body>", lc(en), m);
    httpd_resp_set_type(r, "text/html; charset=utf-8");
    httpd_resp_sendstr(r, h);
}
static esp_err_t wifi_post(httpd_req_t *r)
{
    bool api = strstr(r->uri, "/api/") != NULL;
    bool en = en_req(r);
    char b[1024];
    int total = r->content_len;
    if (total >= (int)sizeof(b))
    {
        httpd_resp_send_err(r, HTTPD_400_BAD_REQUEST, "body too large");
        return ESP_OK;
    }
    int got = 0;
    while (got < total)
    {
        int x = httpd_req_recv(r, b + got, total - got);
        if (x <= 0)
        {
            httpd_resp_send_err(r, HTTPD_500_INTERNAL_SERVER_ERROR, "recv failed");
            return ESP_OK;
        }
        got += x;
    }
    b[got] = 0;
    char act[16], ssid[33], pass[65];
    formv(b, "action", act, sizeof(act));
    formv(b, "ssid", ssid, sizeof(ssid));
    formv(b, "password", pass, sizeof(pass));
    int slot = formi(b, "slot", -1);
    if (strcmp(act, "delete") == 0)
    {
        if (slot >= 0 && slot < WIFI_PROFILE_MAX)
            memset(&prof[slot], 0, sizeof(prof[slot]));
    }
    else
    {
        if (!ssid[0])
        {
            httpd_resp_send_err(r, HTTPD_400_BAD_REQUEST, "ssid required");
            return ESP_OK;
        }
        if (slot < 0 || slot >= WIFI_PROFILE_MAX)
        {
            slot = prof_count < WIFI_PROFILE_MAX ? prof_count : 0;
        }
        prof[slot].valid = true;
        strlcpy(prof[slot].ssid, ssid, sizeof(prof[slot].ssid));
        strlcpy(prof[slot].pass, pass, sizeof(prof[slot].pass));
    }
    esp_err_t e = save_profiles();
    if (e == ESP_OK)
    {
        esp_wifi_disconnect();
        connect_first();
        if (api)
        {
            httpd_resp_set_type(r, "application/json");
            httpd_resp_sendstr(r, "{\"ok\":true}");
        }
        else
            redir(r, en, T(en, "WLAN 设置已保存。", "WLAN settings saved."));
    }
    else if (api)
    {
        httpd_resp_send_err(r, HTTPD_500_INTERNAL_SERVER_ERROR, "save failed");
    }
    else
        redir(r, en, T(en, "保存 WLAN 设置失败。", "Failed to save WLAN settings."));
    return ESP_OK;
}
static esp_err_t root(httpd_req_t*r){httpd_resp_set_type(r,"text/html; charset=utf-8");httpd_resp_sendstr(r,INDEX_HTML);return ESP_OK;}
static esp_err_t api_state(httpd_req_t*r){wifi_sta_list_t l={0};wifi_sta_mac_ip_list_t ips={0};esp_wifi_ap_get_sta_list(&l);esp_wifi_ap_get_sta_list_with_ip(&l,&ips);char*j=calloc(1,8192);if(!j)return httpd_resp_send_500(r);size_t o=0;bool all=all_special();o+=snprintf(j+o,8192-o,"{\"allSpecial\":%s,\"temp\":\"%.1f\",\"mem\":%d,\"settings\":{\"share\":%s,\"led\":%s,\"lang\":\"%s\"},\"ap\":{\"ssid\":\"%s\",\"ip\":\"%s\",\"max\":%d},\"sta\":{\"connected\":%s,\"nat\":%s,\"ssid\":\"%s\",\"ip\":\"" IPSTR "\"},\"profiles\":[",all?"true":"false",cpu_temp,mem_usage,share_wlan?"true":"false",led_enabled?"true":"false",ui_lang,AP_SSID,AP_IP,AP_MAX_CONN,sta_connected?"true":"false",nat_enabled?"true":"false",(active_prof>=0&&prof[active_prof].valid)?prof[active_prof].ssid:"",IP2STR(&sta_ip.ip));bool first=true;for(int i=0;i<WIFI_PROFILE_MAX;i++){if(prof[i].valid&&prof[i].ssid[0]){o+=snprintf(j+o,8192-o,"%s{\"slot\":%d,\"ssid\":\"%s\",\"pass\":\"%s\"}",first?"":",",i,prof[i].ssid,prof[i].pass);first=false;}}o+=snprintf(j+o,8192-o,"],\"devices\":[");first=true;for(size_t d=0;d<sizeof(devs)/sizeof(devs[0]);d++){bool c=false;const esp_ip4_addr_t*ip=NULL;for(int i=0;i<l.num;i++)if(mac_eq(l.sta[i].mac,devs[d].mac)){c=true;ip=ip_for(&ips,l.sta[i].mac);break;}const char*ipstr=(ip&&ip->addr)?ip4addr_ntoa((const ip4_addr_t*)ip):"";o+=snprintf(j+o,8192-o,"%s{\"name\":\"%s\",\"mac\":\"%s\",\"ip\":\"%s\",\"online\":%s}",first?"":",",devs[d].zh,devs[d].mac,ipstr,c?"true":"false");first=false;}int oi=1;for(int i=0;i<l.num;i++){if(special(l.sta[i].mac))continue;char m[18];snprintf(m,sizeof(m),"%02X:%02X:%02X:%02X:%02X:%02X",l.sta[i].mac[0],l.sta[i].mac[1],l.sta[i].mac[2],l.sta[i].mac[3],l.sta[i].mac[4],l.sta[i].mac[5]);const esp_ip4_addr_t*ip=ip_for(&ips,l.sta[i].mac);const char*ipstr=(ip&&ip->addr)?ip4addr_ntoa((const ip4_addr_t*)ip):"";o+=snprintf(j+o,8192-o,",{\"name\":\"其他设备 %d\",\"mac\":\"%s\",\"ip\":\"%s\",\"online\":true}",oi++,m,ipstr);}snprintf(j+o,8192-o,"]}");httpd_resp_set_type(r,"application/json");httpd_resp_sendstr(r,j);free(j);return ESP_OK;}
static esp_err_t api_settings(httpd_req_t*r){char b[160];int n=r->content_len;if(n>=(int)sizeof(b))n=sizeof(b)-1;int g=httpd_req_recv(r,b,n);if(g<0)g=0;b[g]=0;share_wlan=formi(b,"share",0)!=0;led_enabled=formi(b,"led",1)!=0;formv(b,"lang",ui_lang,sizeof(ui_lang));if(!ui_lang[0])strlcpy(ui_lang,"auto",sizeof(ui_lang));save_settings();if(share_wlan){sta_manual_disconnect=false;esp_wifi_disconnect();connect_first();}else{sta_manual_disconnect=true;esp_wifi_disconnect();sta_connected=false;disable_nat();}httpd_resp_set_type(r,"application/json");httpd_resp_sendstr(r,"{\"ok\":true}");return ESP_OK;}
static esp_err_t api_disconnect(httpd_req_t*r){sta_manual_disconnect=true;esp_wifi_disconnect();sta_connected=false;disable_nat();httpd_resp_set_type(r,"application/json");httpd_resp_sendstr(r,"{\"ok\":true}");return ESP_OK;}static esp_err_t api_scan(httpd_req_t*r){wifi_scan_config_t cfg={0};cfg.show_hidden=true;cfg.scan_type=WIFI_SCAN_TYPE_ACTIVE;cfg.scan_time.active.min=120;cfg.scan_time.active.max=300;esp_err_t e=esp_wifi_scan_start(&cfg,true);if(e!=ESP_OK){char err[96];snprintf(err,sizeof(err),"{\"networks\":[],\"error\":\"%s\"}",esp_err_to_name(e));httpd_resp_set_type(r,"application/json");httpd_resp_sendstr(r,err);return ESP_OK;}uint16_t total=0;esp_wifi_scan_get_ap_num(&total);uint16_t n=total>50?50:total;wifi_ap_record_t rec[50];memset(rec,0,sizeof(rec));esp_wifi_scan_get_ap_records(&n,rec);char*j=calloc(1,4096);if(!j)return httpd_resp_send_500(r);size_t o=0;bool first=true;o+=snprintf(j+o,4096-o,"{\"networks\":[");for(int i=0;i<n;i++){if(!rec[i].ssid[0])continue;bool dup=false;for(int k=0;k<i;k++){if(strcmp((char*)rec[i].ssid,(char*)rec[k].ssid)==0){dup=true;break;}}if(dup)continue;o+=snprintf(j+o,4096-o,"%s{\"ssid\":\"%s\",\"rssi\":%d,\"open\":%s}",first?"":",",(char*)rec[i].ssid,rec[i].rssi,rec[i].authmode==WIFI_AUTH_OPEN?"true":"false");first=false;}snprintf(j+o,4096-o,"],\"total\":%u}",total);httpd_resp_set_type(r,"application/json");httpd_resp_sendstr(r,j);free(j);return ESP_OK;}
static esp_err_t nf(httpd_req_t *r, httpd_err_code_t e)
{
    httpd_resp_set_status(r, "302 Found");
    httpd_resp_set_hdr(r, "Location", "/");
    httpd_resp_sendstr(r, "");
    return ESP_OK;
}
static void start_http(void){httpd_config_t c=HTTPD_DEFAULT_CONFIG();c.uri_match_fn=httpd_uri_match_wildcard;c.max_uri_handlers=12;ESP_ERROR_CHECK(httpd_start(&httpd,&c));const httpd_uri_t a={.uri="/",.method=HTTP_GET,.handler=root},b={.uri="/favicon.ico",.method=HTTP_GET,.handler=favicon_handler},t={.uri="/test",.method=HTTP_GET,.handler=test_handler},w={.uri="/wifi",.method=HTTP_POST,.handler=wifi_post},aw={.uri="/api/wifi",.method=HTTP_POST,.handler=wifi_post},st={.uri="/api/state",.method=HTTP_GET,.handler=api_state},sc={.uri="/api/scan",.method=HTTP_GET,.handler=api_scan},dc={.uri="/api/disconnect",.method=HTTP_POST,.handler=api_disconnect},set={.uri="/api/settings",.method=HTTP_POST,.handler=api_settings};httpd_register_uri_handler(httpd,&a);httpd_register_uri_handler(httpd,&b);httpd_register_uri_handler(httpd,&t);httpd_register_uri_handler(httpd,&w);httpd_register_uri_handler(httpd,&aw);httpd_register_uri_handler(httpd,&st);httpd_register_uri_handler(httpd,&sc);httpd_register_uri_handler(httpd,&dc);httpd_register_uri_handler(httpd,&set);httpd_register_err_handler(httpd,HTTPD_404_NOT_FOUND,nf);ESP_LOGI(TAG,"HTTP server started on http://%s/",AP_IP);}void app_main(void)
{
    esp_err_t r = nvs_flash_init();
    if (r == ESP_ERR_NVS_NO_FREE_PAGES || r == ESP_ERR_NVS_NEW_VERSION_FOUND)
    {
        ESP_ERROR_CHECK(nvs_flash_erase());
        r = nvs_flash_init();
    }
    ESP_ERROR_CHECK(r);
    xTaskCreate(led_task, "led", 3072, NULL, 4, NULL);
    xTaskCreate(stats_task, "stats", 3072, NULL, 3, NULL);
    init_wifi();
    start_http();
    while (1)
    {
        wifi_sta_list_t l;
        esp_wifi_ap_get_sta_list(&l);
        set_blink_mode((l.num == 0 || !all_special()) ? 0 : 1);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}






