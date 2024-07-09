# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as app_version

app_name = "webshop-01-connector"
app_title = "WooCommerce Connector"
app_publisher = "libracore"
app_description = "WooCommerce Connector for ERPNext"
app_icon = "fa fa-wordpress"
app_color = "#bc3bff"
app_email = "info@libracore.com"
app_license = "AGPL"
app_url = "https://github.com/libracore/webshop-01-connector"

fixtures = ["Custom Field"]
# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/webshop-01-connector/css/webshop-01-connector.css"
# app_include_js = "/assets/webshop-01-connector/js/webshop-01-connector.js"

# include js, css files in header of web template
# web_include_css = "/assets/webshop-01-connector/css/webshop-01-connector.css"
# web_include_js = "/assets/webshop-01-connector/js/webshop-01-connector.js"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "webshop-01-connector.install.before_install"
after_install = "webshop-01-connector.after_install.create_weight_uom"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "webshop-01-connector.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Bin": {
		"on_update": "webshop-01-connector.sync_products.trigger_update_item_stock"
	}
}

# Scheduled Tasks
# ---------------
scheduler_events = {
     "cron": {
         # Will run every 7 minutes
         "*/7 * * * *": [
             "webshop-01-connector.api.sync_woocommerce"
              ]
        }
}


# before_tests = "webshop-01-connector.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "webshop-01-connector.event.get_events"
# }

