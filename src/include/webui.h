#pragma once
#include "esp_http_server.h"

esp_err_t webui_root_handler(httpd_req_t *r);
esp_err_t webui_style_handler(httpd_req_t *r);
esp_err_t webui_app_handler(httpd_req_t *r);
