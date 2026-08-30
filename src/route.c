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
#include "esp_wifi_netif.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/temperature_sensor.h"
#include "esp_private/wifi.h"
#include "lwip/ip4_addr.h"
#include "config.h"
#include "favicon.h"
#include "route.h"
#include "webui.h"
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
    bool open;
} wifi_profile_t;
typedef struct
{
    const char *mac;
    const char *zh;
    const char *en;
    const char *fallback_ip;
} devmap_t;
typedef struct
{
    char mac[18];
    char ip[16];
} ip_cache_t;
static ip_cache_t ip_cache[AP_MAX_CONN + 4];
static const char *cache_ip(const char *mac, const char *ip)
{
    if (!mac || !mac[0])
        return ip && ip[0] ? ip : "0.0.0.0";
    if (ip && ip[0] && strcmp(ip, "0.0.0.0") != 0)
    {
        int empty = -1;
        for (size_t i = 0; i < sizeof(ip_cache) / sizeof(ip_cache[0]); i++)
        {
            if (ip_cache[i].mac[0] == 0 && empty < 0)
                empty = (int)i;
            if (strcmp(ip_cache[i].mac, mac) == 0)
            {
                strlcpy(ip_cache[i].ip, ip, sizeof(ip_cache[i].ip));
                return ip_cache[i].ip;
            }
        }
        if (empty >= 0)
        {
            strlcpy(ip_cache[empty].mac, mac, sizeof(ip_cache[empty].mac));
            strlcpy(ip_cache[empty].ip, ip, sizeof(ip_cache[empty].ip));
            return ip_cache[empty].ip;
        }
        return ip;
    }
    for (size_t i = 0; i < sizeof(ip_cache) / sizeof(ip_cache[0]); i++)
        if (strcmp(ip_cache[i].mac, mac) == 0 && ip_cache[i].ip[0])
            return ip_cache[i].ip;
    return "0.0.0.0";
}
static wifi_profile_t prof[WIFI_PROFILE_MAX];
static int prof_count, active_prof = -1, sta_retry, blink_mode, led_ready;
static bool sta_connected, nat_enabled, sta_manual_disconnect;
static esp_netif_ip_info_t sta_ip;
static float cpu_temp;
static int mem_usage;
static float up_bps, down_bps;
static volatile uint64_t sta_tx_bytes, ap_tx_bytes;
static bool share_wlan;
static bool led_enabled = true;
static char ui_lang[8] = "auto";
static volatile bool scan_running, scan_ready;
static char scan_json[4096] = "{\"networks\":[],\"total\":0}";
static const devmap_t devs[] = {{"88:A2:9E:2F:EB:92", "\u8F66\u8F7D\u8BBE\u5907", "Car device", "192.168.66.2"}, {"D8:3A:DD:8B:32:73", "\u4E2D\u67A2\u4E3B\u673A", "Core host", "192.168.66.3"}};
static bool en_req(httpd_req_t *r) { return strstr(r->uri, "lang=en") != NULL; }
static void finish_scan_result(void);
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
            uint8_t open = prof[i].pass[0] ? 0 : 1;
            snprintf(k, sizeof(k), "o%d", i);
            nvs_get_u8(n, k, &open);
            prof[i].open = open != 0;
            if (prof[i].open)
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
            prof[0].open = prof[0].pass[0] == 0;
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
        snprintf(k, sizeof(k), "o%d", i);
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
            e = nvs_set_str(n, k, prof[i].open ? "" : prof[i].pass);
        }
        if (e == ESP_OK)
        {
            snprintf(k, sizeof(k), "o%d", i);
            e = nvs_set_u8(n, k, prof[i].open ? 1 : 0);
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
        if (!led_enabled)
        {
            led_write(0);
            vTaskDelay(pdMS_TO_TICKS(200));
            continue;
        }
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
static void count_tx_done(uint8_t ifidx, uint8_t *data, uint16_t *data_len, bool txStatus)
{
    if (!txStatus || !data_len)
        return;
    if (ifidx == WIFI_IF_STA)
        sta_tx_bytes += *data_len;
    else if (ifidx == WIFI_IF_AP)
        ap_tx_bytes += *data_len;
}
static void install_wifi_counters(void)
{
    ESP_ERROR_CHECK_WITHOUT_ABORT(esp_wifi_set_tx_done_cb(count_tx_done));
}
static void traffic_task(void *a)
{
    uint64_t last_sta_tx = 0, last_ap_tx = 0;
    while (1)
    {
        uint64_t sta_tx = sta_tx_bytes;
        uint64_t ap_tx = ap_tx_bytes;
        up_bps = (float)((sta_tx - last_sta_tx) * 8);
        down_bps = (float)((ap_tx - last_ap_tx) * 8);
        last_sta_tx = sta_tx;
        last_ap_tx = ap_tx;
        vTaskDelay(pdMS_TO_TICKS(1000));
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
    if (!prof[i].open)
        strlcpy((char *)c.sta.password, prof[i].pass, sizeof(c.sta.password));
    /* Fast scan avoids long full-band retunes during reconnects. */
    c.sta.scan_method = WIFI_FAST_SCAN;
    c.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
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
    if (!share_wlan || sta_manual_disconnect)
        return;
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
        else if (id == WIFI_EVENT_SCAN_DONE)
            finish_scan_result();
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
        if (!sta_manual_disconnect)
            enable_nat();
        else
            disable_nat();
        install_wifi_counters();
    }
}
static void load_settings(void)
{
    nvs_handle_t n;
    share_wlan = false;
    led_enabled = true;
    strlcpy(ui_lang, "auto", sizeof(ui_lang));
    if (nvs_open("app", NVS_READONLY, &n) != ESP_OK)
        return;
    uint8_t v;
    if (nvs_get_u8(n, "share", &v) == ESP_OK)
        share_wlan = v;
    if (nvs_get_u8(n, "led", &v) == ESP_OK)
        led_enabled = v;
    size_t l = sizeof(ui_lang);
    nvs_get_str(n, "lang", ui_lang, &l);
    nvs_close(n);
}
static esp_err_t save_settings(void)
{
    nvs_handle_t n;
    ESP_RETURN_ON_ERROR(nvs_open("app", NVS_READWRITE, &n), TAG, "app nvs");
    esp_err_t e = nvs_set_u8(n, "share", share_wlan ? 1 : 0);
    if (e == ESP_OK)
        e = nvs_set_u8(n, "led", led_enabled ? 1 : 0);
    if (e == ESP_OK)
        e = nvs_set_str(n, "lang", ui_lang);
    if (e == ESP_OK)
        e = nvs_commit(n);
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
    /* Power-save wakeups can look like AP dropouts on a busy SoftAP. */
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    ESP_ERROR_CHECK(esp_wifi_start());
    install_wifi_counters();
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
    esp_netif_pair_mac_ip_t pairs[AP_MAX_CONN] = {0};
    esp_wifi_ap_get_sta_list(&l);
    esp_wifi_ap_get_sta_list_with_ip(&l, &ips);
    int pair_count = l.num > AP_MAX_CONN ? AP_MAX_CONN : l.num;
    for (int i = 0; i < pair_count; i++)
        memcpy(pairs[i].mac, l.sta[i].mac, 6);
    if (pair_count > 0)
        esp_netif_dhcps_get_clients_by_mac(apif, pair_count, pairs);
    char *j = calloc(1, 6144);
    if (!j)
        return httpd_resp_send_500(r);
    size_t o = 0;
    o += snprintf(j + o, 6144 - o, "{\"status\":%d,\"esptemp\":\"%.1f\",\"memory\":%d,\"ap\":{\"ssid\":\"%s\",\"ip\":\"%s\",\"clients\":%u},\"sta\":{\"connected\":%s,\"ssid\":\"%s\",\"ip\":\"" IPSTR "\",\"nat\":%s,\"profiles\":%d},\"devices\":[", all_special() ? 1 : 0, cpu_temp, mem_usage, AP_SSID, AP_IP, l.num, sta_connected ? "true" : "false", (active_prof >= 0 && prof[active_prof].valid) ? prof[active_prof].ssid : "", IP2STR(&sta_ip.ip), nat_enabled ? "true" : "false", prof_count);
    if (o >= 6144)
        o = 6143;
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
                if (!ip || !ip->addr)
                    for (int k = 0; k < pair_count; k++)
                        if (memcmp(pairs[k].mac, l.sta[i].mac, 6) == 0 && pairs[k].ip.addr)
                        {
                            ip = &pairs[k].ip;
                            break;
                        }
                break;
            }
        const char *raw_ip = (ip && ip->addr) ? ip4addr_ntoa((const ip4_addr_t *)ip) : ((c && devs[d].fallback_ip) ? devs[d].fallback_ip : "0.0.0.0");
        const char *ipstr = cache_ip(devs[d].mac, raw_ip);
        o += snprintf(j + o, 6144 - o, "%s{\"name\":\"%s\",\"mac\":\"%s\",\"ip\":\"%s\",\"status\":%s}", first ? "" : ",", devs[d].en, devs[d].mac, ipstr, c ? "true" : "false");
        if (o >= 6144)
            o = 6143;
        first = false;
    }
    for (int i = 0; i < l.num; i++)
    {
        if (special(l.sta[i].mac))
            continue;
        char m[18];
        snprintf(m, sizeof(m), "%02X:%02X:%02X:%02X:%02X:%02X", l.sta[i].mac[0], l.sta[i].mac[1], l.sta[i].mac[2], l.sta[i].mac[3], l.sta[i].mac[4], l.sta[i].mac[5]);
        const esp_ip4_addr_t *ip = ip_for(&ips, l.sta[i].mac);
        o += snprintf(j + o, 6144 - o, "%s{\"name\":\"Other device\",\"mac\":\"%s\",\"ip\":\"%s\",\"status\":true}", first ? "" : ",", m, ip ? ip4addr_ntoa((const ip4_addr_t *)ip) : "0.0.0.0");
        if (o >= 6144)
            o = 6143;
        first = false;
    }
    snprintf(j + o, 6144 - o, "]}");
    httpd_resp_set_type(r, "application/json; charset=utf-8");
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
    bool open = formi(b, "open", pass[0] ? 0 : 1) != 0;
    if (open)
        pass[0] = 0;
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
            slot = prof_count < WIFI_PROFILE_MAX ? prof_count : 0;
        prof[slot].valid = true;
        strlcpy(prof[slot].ssid, ssid, sizeof(prof[slot].ssid));
        strlcpy(prof[slot].pass, pass, sizeof(prof[slot].pass));
        prof[slot].open = open;
    }
    esp_err_t e = save_profiles();
    if (e == ESP_OK)
    {
        if (strcmp(act, "delete") != 0)
        {
            share_wlan = true;
            sta_manual_disconnect = false;
            save_settings();
            esp_wifi_disconnect();
            connect_first();
        }
        if (api)
        {
            httpd_resp_set_type(r, "application/json; charset=utf-8");
            httpd_resp_sendstr(r, "{\"ok\":true}");
        }
        else
            redir(r, en, T(en, "WLAN \u8BBE\u7F6E\u5DF2\u4FDD\u5B58\u3002", "WLAN settings saved."));
    }
    else if (api)
    {
        httpd_resp_send_err(r, HTTPD_500_INTERNAL_SERVER_ERROR, "save failed");
    }
    else
        redir(r, en, T(en, "\u4FDD\u5B58 WLAN \u8BBE\u7F6E\u5931\u8D25\u3002", "Failed to save WLAN settings."));
    return ESP_OK;
}
static const esp_ip4_addr_t *leased_ip_for(esp_netif_pair_mac_ip_t *pairs, int count, const uint8_t mac[6])
{
    for (int i = 0; i < count; i++)
        if (memcmp(pairs[i].mac, mac, 6) == 0 && pairs[i].ip.addr)
            return &pairs[i].ip;
    return NULL;
}
static const char *auth_label(wifi_auth_mode_t auth)
{
    return auth == WIFI_AUTH_OPEN ? "open" : "secure";
}
static esp_err_t api_state(httpd_req_t *r)
{
    wifi_sta_list_t l = {0};
    esp_wifi_ap_get_sta_list(&l);
    esp_netif_pair_mac_ip_t pairs[AP_MAX_CONN] = {0};
    wifi_sta_mac_ip_list_t ip_l = {0};
    int pair_count = l.num > AP_MAX_CONN ? AP_MAX_CONN : l.num;
    for (int i = 0; i < pair_count; i++)
        memcpy(pairs[i].mac, l.sta[i].mac, 6);
    if (pair_count > 0)
    {
        ESP_ERROR_CHECK_WITHOUT_ABORT(esp_netif_dhcps_get_clients_by_mac(apif, pair_count, pairs));
        ESP_ERROR_CHECK_WITHOUT_ABORT(esp_wifi_ap_get_sta_list_with_ip(&l, &ip_l));
    }

    char *j = calloc(1, 8192);
    if (!j)
        return httpd_resp_send_500(r);
    size_t o = 0;
    bool all = all_special();
    o += snprintf(j + o, 8192 - o,
                  "{\"allSpecial\":%s,\"temp\":\"%.1f\",\"mem\":%d,\"up\":%.0f,\"down\":%.0f,\"settings\":{\"share\":%s,\"led\":%s,\"lang\":\"%s\"},\"ap\":{\"ssid\":\"%s\",\"ip\":\"%s\",\"max\":%d},\"sta\":{\"connected\":%s,\"nat\":%s,\"ssid\":\"%s\",\"ip\":\"" IPSTR "\"},\"profiles\":[",
                  all ? "true" : "false", cpu_temp, mem_usage, up_bps, down_bps, share_wlan ? "true" : "false", led_enabled ? "true" : "false", ui_lang, AP_SSID, AP_IP, AP_MAX_CONN, (sta_connected && !sta_manual_disconnect) ? "true" : "false", (nat_enabled && !sta_manual_disconnect) ? "true" : "false", (active_prof >= 0 && prof[active_prof].valid) ? prof[active_prof].ssid : "", IP2STR(&sta_ip.ip));
    bool first = true;
    for (int i = 0; i < WIFI_PROFILE_MAX; i++)
    {
        if (prof[i].valid && prof[i].ssid[0])
        {
            o += snprintf(j + o, 8192 - o, "%s{\"slot\":%d,\"ssid\":\"%s\",\"pass\":\"%s\",\"auth\":\"%s\",\"open\":%s}", first ? "" : ",", i, prof[i].ssid, prof[i].open ? "" : prof[i].pass, prof[i].open ? "open" : "secure", prof[i].open ? "true" : "false");
            first = false;
        }
    }
    o += snprintf(j + o, 8192 - o, "],\"devices\":[");
    first = true;
    for (size_t d = 0; d < sizeof(devs) / sizeof(devs[0]); d++)
    {
        bool c = false;
        const esp_ip4_addr_t *ip = NULL;
        for (int i = 0; i < l.num; i++)
        {
            if (mac_eq(l.sta[i].mac, devs[d].mac))
            {
                c = true;
                ip = leased_ip_for(pairs, pair_count, l.sta[i].mac);
                if (!ip || !ip->addr)
                    ip = leased_ip_for(ip_l.sta, ip_l.num, l.sta[i].mac);
                break;
            }
        }
        const char *raw_ip = (ip && ip->addr) ? ip4addr_ntoa((const ip4_addr_t *)ip) : ((c && devs[d].fallback_ip) ? devs[d].fallback_ip : "0.0.0.0");
        const char *ipstr = cache_ip(devs[d].mac, raw_ip);
        o += snprintf(j + o, 8192 - o, "%s{\"name\":\"%s\",\"mac\":\"%s\",\"ip\":\"%s\",\"online\":%s}", first ? "" : ",", devs[d].zh, devs[d].mac, ipstr, c ? "true" : "false");
        first = false;
    }
    int oi = 1;
    for (int i = 0; i < l.num; i++)
    {
        if (special(l.sta[i].mac))
            continue;
        char m[18];
        snprintf(m, sizeof(m), "%02X:%02X:%02X:%02X:%02X:%02X", l.sta[i].mac[0], l.sta[i].mac[1], l.sta[i].mac[2], l.sta[i].mac[3], l.sta[i].mac[4], l.sta[i].mac[5]);
        const esp_ip4_addr_t *ip = leased_ip_for(pairs, pair_count, l.sta[i].mac);
        if (!ip || !ip->addr)
            ip = leased_ip_for(ip_l.sta, ip_l.num, l.sta[i].mac);
        const char *ipstr = cache_ip(m, (ip && ip->addr) ? ip4addr_ntoa((const ip4_addr_t *)ip) : "0.0.0.0");
        o += snprintf(j + o, 8192 - o, ",{\"name\":\"\u5176\u4ED6\u8BBE\u5907 %d\",\"mac\":\"%s\",\"ip\":\"%s\",\"online\":true}", oi++, m, ipstr);
    }
    snprintf(j + o, 8192 - o, "]}");
    httpd_resp_set_type(r, "application/json; charset=utf-8");
    httpd_resp_sendstr(r, j);
    free(j);
    return ESP_OK;
}
static esp_err_t api_settings(httpd_req_t *r)
{
    char b[160];
    int n = r->content_len;
    if (n >= (int)sizeof(b))
        n = sizeof(b) - 1;
    int g = httpd_req_recv(r, b, n);
    if (g < 0)
        g = 0;
    b[g] = 0;
    share_wlan = formi(b, "share", 0) != 0;
    led_enabled = formi(b, "led", 1) != 0;
    formv(b, "lang", ui_lang, sizeof(ui_lang));
    if (!ui_lang[0])
        strlcpy(ui_lang, "auto", sizeof(ui_lang));
    save_settings();
    if (share_wlan)
    {
        sta_manual_disconnect = false;
        if (sta_connected)
            enable_nat();
        else
            connect_first();
    }
    else
    {
        sta_manual_disconnect = true;
        disable_nat();
    }
    httpd_resp_set_type(r, "application/json; charset=utf-8");
    httpd_resp_sendstr(r, "{\"ok\":true}");
    return ESP_OK;
}
static esp_err_t api_disconnect(httpd_req_t *r)
{
    sta_manual_disconnect = true;
    disable_nat();
    httpd_resp_set_type(r, "application/json; charset=utf-8");
    httpd_resp_set_hdr(r, "Connection", "close");
    httpd_resp_sendstr(r, "{\"ok\":true}");
    return ESP_OK;
}
static void finish_scan_result(void)
{
    uint16_t total = 0;
    esp_err_t e = esp_wifi_scan_get_ap_num(&total);
    ESP_LOGI(TAG, "scan: done event err=%s total=%u", esp_err_to_name(e), total);
    if (e != ESP_OK)
    {
        snprintf(scan_json, sizeof(scan_json), "{\"running\":false,\"networks\":[],\"error\":\"%s\"}", esp_err_to_name(e));
    }
    else
    {
        uint16_t n = total > 50 ? 50 : total;
        wifi_ap_record_t *rec = calloc(n ? n : 1, sizeof(wifi_ap_record_t));
        if (!rec)
        {
            snprintf(scan_json, sizeof(scan_json), "{\"running\":false,\"networks\":[],\"error\":\"NO_MEM\"}");
        }
        else
        {
            esp_wifi_scan_get_ap_records(&n, rec);
            size_t o = 0;
            bool first = true;
            o += snprintf(scan_json + o, sizeof(scan_json) - o, "{\"running\":false,\"networks\":[");
            for (int i = 0; i < n && o < sizeof(scan_json) - 96; i++)
            {
                if (!rec[i].ssid[0])
                    continue;
                bool dup = false;
                for (int k = 0; k < i; k++)
                    if (strcmp((char *)rec[i].ssid, (char *)rec[k].ssid) == 0)
                    {
                        dup = true;
                        break;
                    }
                if (dup)
                    continue;
                o += snprintf(scan_json + o, sizeof(scan_json) - o, "%s{\"ssid\":\"%s\",\"rssi\":%d,\"auth\":\"%s\",\"open\":%s}", first ? "" : ",", (char *)rec[i].ssid, rec[i].rssi, auth_label(rec[i].authmode), rec[i].authmode == WIFI_AUTH_OPEN ? "true" : "false");
                if (o >= sizeof(scan_json))
                {
                    o = sizeof(scan_json) - 1;
                    break;
                }
                first = false;
            }
            snprintf(scan_json + o, sizeof(scan_json) - o, "],\"total\":%u}", total);
            free(rec);
        }
    }
    scan_ready = true;
    scan_running = false;
}
static esp_err_t api_scan(httpd_req_t *r)
{
    ESP_LOGI(TAG, "scan: request sta_connected=%d manual=%d running=%d ready=%d", sta_connected, sta_manual_disconnect, scan_running, scan_ready);
    httpd_resp_set_type(r, "application/json; charset=utf-8");
    httpd_resp_set_hdr(r, "Connection", "close");
    /* A scan temporarily retunes the shared AP/STA radio.  Never start one
       while clients are attached: it can disconnect the car and Core host. */
    wifi_sta_list_t clients = {0};
    esp_wifi_ap_get_sta_list(&clients);
    if (clients.num > 0)
    {
        httpd_resp_sendstr(r, "{\"running\":false,\"networks\":[],\"error\":\"AP_CLIENTS_CONNECTED\"}");
        return ESP_OK;
    }
    if (sta_connected && !sta_manual_disconnect)
    {
        httpd_resp_sendstr(r, "{\"running\":false,\"networks\":[],\"error\":\"DISCONNECT_FIRST\"}");
        return ESP_OK;
    }
    if (scan_running)
    {
        httpd_resp_sendstr(r, "{\"running\":true}");
        return ESP_OK;
    }
    if (scan_ready)
    {
        scan_ready = false;
        httpd_resp_sendstr(r, scan_json);
        return ESP_OK;
    }
    wifi_scan_config_t cfg = {0};
    cfg.show_hidden = true;
    cfg.channel = AP_CHANNEL;
    cfg.scan_type = WIFI_SCAN_TYPE_ACTIVE;
    cfg.scan_time.active.min = 60;
    cfg.scan_time.active.max = 140;
    cfg.home_chan_dwell_time = 30;
    scan_running = true;
    esp_err_t e = esp_wifi_scan_start(&cfg, false);
    if (e != ESP_OK)
    {
        scan_running = false;
        snprintf(scan_json, sizeof(scan_json), "{\"running\":false,\"networks\":[],\"error\":\"%s\"}", esp_err_to_name(e));
        httpd_resp_sendstr(r, scan_json);
        return ESP_OK;
    }
    httpd_resp_sendstr(r, "{\"running\":true}");
    return ESP_OK;
}
static esp_err_t nf(httpd_req_t *r, httpd_err_code_t e)
{
    httpd_resp_set_status(r, "302 Found");
    httpd_resp_set_hdr(r, "Location", "/");
    httpd_resp_sendstr(r, "");
    return ESP_OK;
}
static void start_http(void)
{
    httpd_config_t c = HTTPD_DEFAULT_CONFIG();
    c.uri_match_fn = httpd_uri_match_wildcard;
    c.max_uri_handlers = 14;
    ESP_ERROR_CHECK(httpd_start(&httpd, &c));
    const httpd_uri_t a = {.uri = "/", .method = HTTP_GET, .handler = webui_root_handler};
    const httpd_uri_t css = {.uri = "/static/style.css", .method = HTTP_GET, .handler = webui_style_handler};
    const httpd_uri_t js = {.uri = "/static/app.js", .method = HTTP_GET, .handler = webui_app_handler};
    const httpd_uri_t b = {.uri = "/favicon.ico", .method = HTTP_GET, .handler = favicon_handler};
    const httpd_uri_t t = {.uri = "/test", .method = HTTP_GET, .handler = test_handler};
    const httpd_uri_t w = {.uri = "/wifi", .method = HTTP_POST, .handler = wifi_post};
    const httpd_uri_t aw = {.uri = "/api/wifi", .method = HTTP_POST, .handler = wifi_post};
    const httpd_uri_t st = {.uri = "/api/state", .method = HTTP_GET, .handler = api_state};
    const httpd_uri_t sc = {.uri = "/api/scan", .method = HTTP_GET, .handler = api_scan};
    const httpd_uri_t dc = {.uri = "/api/disconnect", .method = HTTP_POST, .handler = api_disconnect};
    const httpd_uri_t set = {.uri = "/api/settings", .method = HTTP_POST, .handler = api_settings};
    httpd_register_uri_handler(httpd, &a);
    httpd_register_uri_handler(httpd, &css);
    httpd_register_uri_handler(httpd, &js);
    httpd_register_uri_handler(httpd, &b);
    httpd_register_uri_handler(httpd, &t);
    httpd_register_uri_handler(httpd, &w);
    httpd_register_uri_handler(httpd, &aw);
    httpd_register_uri_handler(httpd, &st);
    httpd_register_uri_handler(httpd, &sc);
    httpd_register_uri_handler(httpd, &dc);
    httpd_register_uri_handler(httpd, &set);
    httpd_register_err_handler(httpd, HTTPD_404_NOT_FOUND, nf);
    ESP_LOGI(TAG, "HTTP server started on http://%s/", AP_IP);
}
void tcar_run(void)
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
    xTaskCreate(traffic_task, "traffic", 3072, NULL, 3, NULL);
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







