#include "webui.h"
#include "web_ui.h"

esp_err_t webui_root_handler(httpd_req_t *r)
{
    httpd_resp_set_type(r, "text/html; charset=utf-8");
    httpd_resp_sendstr(r, INDEX_HTML);
    return ESP_OK;
}

esp_err_t webui_style_handler(httpd_req_t *r)
{
    httpd_resp_set_type(r, "text/css; charset=utf-8");
    httpd_resp_sendstr(r, STYLE_CSS);
    return ESP_OK;
}

esp_err_t webui_app_handler(httpd_req_t *r)
{
    httpd_resp_set_type(r, "application/javascript; charset=utf-8");
    httpd_resp_sendstr(r, APP_JS);
    return ESP_OK;
}
