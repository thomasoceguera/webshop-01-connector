from __future__ import unicode_literals
import frappe
from frappe import _
import requests.exceptions
from .webshop-01-requests import get_webshop-01-customers, post_request, put_request
from .utils import make_webshop-01-log

def sync_customers():
    webshop-01-customer_list = []
    sync_webshop-01-customers(webshop-01-customer_list)
    frappe.local.form_dict.count_dict["customers"] = len(webshop-01-customer_list)

def sync_webshop-01-customers(webshop-01-customer_list):
    for webshop-01-customer in get_webshop-01-customers():
        # import new customer or update existing customer
        if not frappe.db.get_value("Customer", {"webshop-01-customer_id": webshop-01-customer.get('id')}, "name"):
            #only synch customers with address
            if webshop-01-customer.get("billing").get("address_1") != "" and webshop-01-customer.get("shipping").get("address_1") != "":
                create_customer(webshop-01-customer, webshop-01-customer_list)
            # else:
            #    make_webshop-01-log(title="customer without address", status="Error", method="create_customer",
            #        message= "customer without address found",request_data=webshop-01-customer, exception=False)
        else:
            update_customer(webshop-01-customer)

def update_customer(webshop-01-customer):
    return

def create_customer(webshop-01-customer, webshop-01-customer_list):
    import frappe.utils.nestedset

    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
    
    cust_name = (webshop-01-customer.get("first_name") + " " + (webshop-01-customer.get("last_name") \
        and  webshop-01-customer.get("last_name") or "")) if webshop-01-customer.get("first_name")\
        else webshop-01-customer.get("email")
        
    try:
        # try to match territory
        country_name = get_country_name(webshop-01-customer["billing"]["country"])
        if frappe.db.exists("Territory", country_name):
            territory = country_name
        else:
            territory = frappe.utils.nestedset.get_root_of("Territory")
        customer_to_check = frappe.get_value(
            "Customer",
            {
                "customer_name": cust_name,
                "sync_with_woocommerce": 0,
                "customer_group": webshop-01-settings.customer_group,
                "territory": territory,
                "customer_type": _("Individual"),
            },
            "name"
        )
        customer = frappe.get_doc({
            "doctype": "Customer",
            "name": webshop-01-customer.get("id"),
            "customer_name" : cust_name,
            "webshop-01-customer_id": webshop-01-customer.get("id"),
            "sync_with_woocommerce": 0,
            "customer_group": webshop-01-settings.customer_group,
            "territory": territory,
            "customer_type": _("Individual")
        })
        customer.flags.ignore_mandatory = True
        customer.insert()
        
        if customer:
            create_customer_address(customer, webshop-01-customer)
            create_customer_contact(customer, webshop-01-customer)
    
        webshop-01-customer_list.append(webshop-01-customer.get("id"))
        frappe.db.commit()
        make_webshop-01-log(title="create customer", status="Success", method="create_customer",
            message= "create customer",request_data=webshop-01-customer, exception=False)
            
    except Exception as e:
        if e.args[0] and e.args[0].startswith("402"):
            raise e
        else:
            make_webshop-01-log(title=e, status="Error", method="create_customer", message=frappe.get_traceback(),
                request_data=webshop-01-customer, exception=True)
        
def create_customer_address(customer, webshop-01-customer):
    billing_address = webshop-01-customer.get("billing")
    shipping_address = webshop-01-customer.get("shipping")
    
    if billing_address:
        country = get_country_name(billing_address.get("country"))
        if not frappe.db.exists("Country", country):
            country = "Switzerland"
        try :
            frappe.get_doc({
                "doctype": "Address",
                "webshop-01-address_id": "Billing",
                "webshop-01-company_name": billing_address.get("company") or "",
                "address_title": " ".join([billing_address.get("first_name"), billing_address.get("last_name")]),
                "address_type": "Billing",
                "address_line1": billing_address.get("address_1") or "Address 1",
                "address_line2": billing_address.get("address_2"),
                "city": billing_address.get("city") or "City",
                "state": billing_address.get("state"),
                "pincode": billing_address.get("postcode"),
                "country": country,
                "phone": billing_address.get("phone"),
                "email_id": billing_address.get("email"),
                "links": [{
                    "link_doctype": "Customer",
                    "link_name": customer.name
                }]
            }).insert()

        except Exception as e:
            make_webshop-01-log(title=e, status="Error", method="create_customer_address", message=frappe.get_traceback(),
                    request_data=webshop-01-customer, exception=True)

    if shipping_address:
        country = get_country_name(billing_address.get("country"))
        if not frappe.db.exists("Country", country):
            country = "Switzerland"
        try :
            frappe.get_doc({
                "doctype": "Address",
                "webshop-01-address_id": "Shipping",
                "webshop-01-company_name": shipping_address.get("company") or "",
                "address_title": " ".join([shipping_address.get("first_name"), shipping_address.get("last_name")]),
                "address_type": "Shipping",
                "address_line1": shipping_address.get("address_1") or "Address 1",
                "address_line2": shipping_address.get("address_2"),
                "city": shipping_address.get("city") or "City",
                "state": shipping_address.get("state"),
                "pincode": shipping_address.get("postcode"),
                "country": country,
                "phone": shipping_address.get("phone"),
                "email_id": shipping_address.get("shipping_email"),
                "links": [{
                    "link_doctype": "Customer",
                    "link_name": customer.name
                }]
            }).insert()
            
        except Exception as e:
            make_webshop-01-log(title=e, status="Error", method="create_customer_address", message=frappe.get_traceback(),
                request_data=webshop-01-customer, exception=True)

# TODO: email and phone into child table
def create_customer_contact(customer, webshop-01-customer):
    try :
        frappe.get_doc({
            "doctype": "Contact",
            "first_name": webshop-01-customer["billing"]["first_name"],
            "last_name": webshop-01-customer["billing"]["last_name"],
            "email_ids": [{
                "email_id": webshop-01-customer["billing"]["email"],
                "is_primary": 1
            }],
            "phone_nos": [{
                "phone": webshop-01-customer["billing"]["phone"],
                "is_primary_phone": 1
            }],
            "links": [{
                "link_doctype": "Customer",
                "link_name": customer.name
            }]
        }).insert()

    except Exception as e:
        make_webshop-01-log(title=e, status="Error", method="create_customer_contact", message=frappe.get_traceback(),
                request_data=webshop-01-customer, exception=True)

def get_country_name(code):
    coutry_name = ''
    coutry_names = """SELECT `country_name` FROM `tabCountry` WHERE `code` = '{0}'""".format(code.lower())
    for _coutry_name in frappe.db.sql(coutry_names, as_dict=1):
        coutry_name = _coutry_name.country_name
    return coutry_name
