# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
from .exceptions import woocommerceSetupError

def disable_webshop-01-sync_for_item(item, rollback=False):
	"""Disable Item if not exist on woocommerce"""
	if rollback:
		frappe.db.rollback()
		
	item.sync_with_woocommerce = 0
	item.sync_qty_with_woocommerce = 0
	item.save(ignore_permissions=True)
	frappe.db.commit()

def disable_webshop-01-sync_on_exception():
	frappe.db.rollback()
	frappe.db.set_value("WooCommerce Config", None, "enable_woocommerce", 0)
	frappe.db.commit()

def is_webshop-01-enabled():
	webshop-01-settings = frappe.get_doc("WooCommerce Config")
	if not webshop-01-settings.enable_woocommerce:
		return False
	try:
		webshop-01-settings.validate()
	except woocommerceSetupError:
		return False
	
	return True
	
def make_webshop-01-log(title="Sync Log", status="Queued", method="sync_woocommerce", message=None, exception=False, 
name=None, request_data={}):
	if not name:
		name = frappe.db.get_value("woocommerce Log", {"status": "Queued"})
		
		if name:
			""" if name not provided by log calling method then fetch existing queued state log"""
			log = frappe.get_doc("woocommerce Log", name)
		
		else:
			""" if queued job is not found create a new one."""
			log = frappe.get_doc({"doctype":"woocommerce Log"}).insert(ignore_permissions=True)
		
		if exception:
			frappe.db.rollback()
			log = frappe.get_doc({"doctype":"woocommerce Log"}).insert(ignore_permissions=True)
			
		log.message = message if message else frappe.get_traceback()
		log.title = title[0:140]
		log.method = method
		log.status = status
		log.request_data= json.dumps(request_data)
		
		log.save(ignore_permissions=True)
		frappe.db.commit()

def get_mention_comment(mention_to_name, ) -> str:
	user = frappe.get_doc('User', mention_to_name)
	mention_comment = """
	<span class="mention" data-id="{}" data-value="" data-denotation-char="@">
		<span><span class="ql-mention-denotation-char">@</span>{}</span>
	</span>""".format(user.name, user.get_fullname())
	return mention_comment

class InsufficientStockAmount(frappe.ValidationError):
	pass
