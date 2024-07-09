from __future__ import unicode_literals
import frappe
from frappe import _
from .exceptions import woocommerceError
from .utils import make_webshop-01-log, get_mention_comment, InsufficientStockAmount
from .sync_customers import (
    create_customer,
    create_customer_address,
    create_customer_contact,
)
from frappe.utils import flt, nowdate, cint, get_datetime, get_date_str, add_days, logger
from .webshop-01-requests import (
    get_webshop-01-orders,
    get_webshop-01-tax,
    get_webshop-01-customer,
    put_request,
)
from erpnext.selling.doctype.sales_order.sales_order import (
    make_delivery_note,
    make_sales_invoice,
)
from erpnext.stock.doctype.serial_no.serial_no import (
    auto_fetch_serial_number
)
import requests.exceptions
import requests

from copy import copy


def sync_orders():
    sync_webshop-01-orders()

def sync_webshop-01-orders():
    frappe.local.form_dict.count_dict["orders"] = 0
    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
    webshop-01-order_status_for_import = get_webshop-01-order_status_for_import() or ["processing"]

    for webshop-01-order_status in webshop-01-order_status_for_import:
        for webshop-01-order in get_webshop-01-orders(webshop-01-order_status):
            process_order(webshop-01-order, webshop-01-settings)


def process_order(webshop-01-order, webshop-01-settings):
    so = frappe.db.get_value(
        "Sales Order",
        {"webshop-01-order_id": webshop-01-order.get("id")},
        "name",
    )

    if so:
        return

    if not valid_customer_and_product(webshop-01-order):
        return

    try:
        create_order(webshop-01-order, webshop-01-settings)
        frappe.local.form_dict.count_dict["orders"] += 1
        close_synced_webshop-01-order(webshop-01-order.get("id"))
    except woocommerceError as e:
        log_webshop-01-error(e, webshop-01-order, "sync_webshop-01-orders")
    except Exception as e:
        log_general_error(e, webshop-01-order, "sync_webshop-01-orders")


def log_webshop-01-error(e, webshop-01-order, method_name):
    make_webshop-01-log(
        status="Error",
        method=method_name,
        message=frappe.get_traceback(),
        request_data=webshop-01-order,
        exception=True,
    )


def log_general_error(e, webshop-01-order, method_name):
    if e.args and e.args[0] and e.args[0].startswith("402"):
        frappe.log_error(frappe.get_traceback(), 'sync orders')
    else:
        make_webshop-01-log(
            title=str(e) if not hasattr(e, 'message') else e.message,
            status="Error",
            method=method_name,
            message=frappe.get_traceback(),
            request_data=webshop-01-order,
            exception=True,
        )

def get_webshop-01-order_status_for_import():
    _status_list = frappe.db.sql(
        """SELECT `status` FROM `tabWooCommerce SO Status`""", as_dict=True
    )
    return [status.status for status in _status_list]


def valid_customer_and_product(webshop-01-order):
    if webshop-01-order.get("status").lower() == "cancelled":
        return False

    if webshop-01-order.get("customer_name") == "s360 Order Test User":
        make_webshop-01-log(
            title="Test Order - Not processed!",
            status="Notice",
            method="valid_customer_and_product",
            message="This order was a test order from one of our vendors. The Order {0} will not be imported! For details of order see below".format(
                webshop-01-order.get("customer_name")  # Assuming you want to print the customer name
            )
        )
        return False

# Iterate over line items
    for item in webshop-01-order.get("line_items"):
        product_id = item.get("product_id")

        if product_id and not frappe.db.get_value("Item", {"webshop-01-product_id": product_id}, "item_code"):
            make_webshop-01-log(
                title="Item missing in ERPNext!",
                status="Error",
                method="valid_customer_and_product",
                message=f"Item with id {product_id} is missing in ERPNext! The Order {webshop-01-order.get('id')} will not be imported! For details of order see below",
                request_data=webshop-01-order,
                exception=True,
            )
            return False
        elif not product_id:
            make_webshop-01-log(
                title="Item id missing in WooCommerce!",
                status="Error",
                method="valid_customer_and_product",
                message=f"Item id is missing in WooCommerce! The Order {webshop-01-order.get('id')} will not be imported! For details of order see below",
                request_data=webshop-01-order,
                exception=True,
            )
            return False

    try:
        customer_id = int(webshop-01-order.get("customer_id"))

    except ValueError:
        customer_id = 0

    if customer_id > 0:
        if not frappe.db.get_value("Customer", {"webshop-01-customer_id": str(customer_id)}, "name", False, True):
            webshop-01-customer = get_webshop-01-customer(customer_id)
            update_customer_addresses(webshop-01-customer, webshop-01-order)
            create_customer(webshop-01-customer, webshop-01-customer_list=[])

    elif customer_id == 0:  # dealing with a guest customer
        guest_id = f"Guest of Order-ID: {webshop-01-order.get('id')}"
        if not frappe.db.get_value("Customer", {"webshop-01-customer_id": guest_id}, "name", False, True):
            make_webshop-01-log(
                title="create new customer based on guest order",
                status="Started",
                method="valid_customer_and_product",
                message="create new customer based on guest order",
                request_data=webshop-01-order,
                exception=False,
            )
            create_new_customer_of_guest(webshop-01-order)

    return True

# ...

def update_customer_addresses(webshop-01-customer, webshop-01-order):
    if webshop-01-customer["billing"].get("address_1") == "":
        webshop-01-customer["billing"] = webshop-01-order["billing"]
        webshop-01-customer["billing"]["country"] = get_country_from_code(webshop-01-customer.get("billing").get("country"))

        if webshop-01-customer["shipping"].get("address_1") == "":
            webshop-01-customer["shipping"] = webshop-01-order["shipping"]
            webshop-01-customer["shipping"]["country"] = get_country_from_code(webshop-01-customer.get("shipping").get("country"))

def get_country_from_code(country_code):
    return frappe.db.get_value("Country", {"code": country_code}, "name")

def create_new_customer_of_guest(webshop-01-order):
    import frappe.utils.nestedset

    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")

    cust_id = "Guest of Order-ID: {0}".format(webshop-01-order.get("id"))
    cust_info = webshop-01-order.get("billing")

    try:
        customer_name = frappe.get_value(
            "Customer",
            {
                "customer_name": "{0} {1}".format(cust_info["first_name"], cust_info["last_name"]),
                "sync_with_woocommerce": 0,
                "customer_group": webshop-01-settings.customer_group,
                "territory": frappe.utils.nestedset.get_root_of("Territory"),
                "customer_type": _("Individual"),
            },
            "name"
        )
        if customer_name:
            return
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "name": cust_id,
                "customer_name": "{0} {1}".format(
                    cust_info["first_name"], cust_info["last_name"]
                ),
                "webshop-01-customer_id": cust_id,
                "sync_with_woocommerce": 0,
                "customer_group": webshop-01-settings.customer_group,
                "territory": frappe.utils.nestedset.get_root_of("Territory"),
                "customer_type": _("Individual"),
            }
        )
        customer.flags.ignore_mandatory = True
        customer.insert()

        if customer:
            create_customer_address(customer, webshop-01-order)
            create_customer_contact(customer, webshop-01-order)

        frappe.db.commit()
        frappe.local.form_dict.count_dict["customers"] += 1
        make_webshop-01-log(
            title="create customer",
            status="Success",
            method="create_new_customer_of_guest",
            message="create customer",
            request_data=webshop-01-order,
            exception=False,
        )

    except Exception as e:
        if e.args[0] and e.args[0].startswith("402"):
            raise e
        else:
            make_webshop-01-log(
                title=e.message,
                status="Error",
                method="create_new_customer_of_guest",
                message=frappe.get_traceback(),
                request_data=webshop-01-order,
                exception=True,
            )

def get_country_name(code):
    country_name = frappe.db.get_value("Country", {"code": code.lower()}, "country_name")
    return country_name or ""


def create_order(webshop-01-order, webshop-01-settings, company=None):
    so = create_sales_order(webshop-01-order, webshop-01-settings, company)
    # check if sales invoice should be created
    if cint(webshop-01-settings.sync_sales_invoice) == 1:
        create_sales_invoice(webshop-01-order, webshop-01-settings, so)

    # Fix this -- add shipping stuff
    if cint(webshop-01-settings.sync_delivery_note):
        create_delivery_note(webshop-01-order, webshop-01-settings, so)


def create_sales_order(webshop-01-order, webshop-01-settings, company=None):
    id = str(webshop-01-order.get("customer_id"))
    customer = frappe.get_all(
        "Customer", filters=[["webshop-01-customer_id", "=", id]], fields=["name"]
    )
    billing_address = webshop-01-order.get('billing')
    backup_customer = frappe.get_all(
        "Customer",
        filters=[
            [
                "customer_name",
                "=",
                "{0} {1}".format(billing_address.get("first_name"), billing_address.get('last_name')),
            ]
        ],
        fields=["name"],
    )
    if customer:
        customer = customer[0]["name"]
    elif backup_customer:
        customer = backup_customer[0]["name"]
    else:
        frappe.log_error("No customer found. This should never happen.")

    so = frappe.db.get_value(
        "Sales Order", {"new_webshop-01-order_id": webshop-01-order.get("id")}, "name"
    )
    if not so:
        # get shipping/billing address
        shipping_address = get_customer_address_from_order(
            "Shipping", webshop-01-order, customer
        )
        billing_address = get_customer_address_from_order(
            "Billing", webshop-01-order, customer
        )

        # get applicable tax rule from configuration
        tax_rules = frappe.get_all(
            "WooCommerce Tax Rule",
            filters={"currency": webshop-01-order.get("currency")},
            fields=["tax_rule"],
        )
        if not tax_rules:
            # fallback: currency has no tax rule, try catch-all
            tax_rules = frappe.get_all(
                "WooCommerce Tax Rule", filters={"currency": "%"}, fields=["tax_rule"]
            )
        if tax_rules:
            tax_rules = tax_rules[0]["tax_rule"]
        else:
            tax_rules = ""

        transactionDate = get_datetime(webshop-01-order.get("date_created"))
#        deliveryDate = add_days(transactionDate, webshop-01-settings.delivery_after_days)
        deliveryDate = add_days(transactionDate, 1)
        so = frappe.get_doc(
            {
                "doctype": "Sales Order",
                "naming_series": webshop-01-settings.sales_order_series
                or "SO-woocommerce-",
                "new_webshop-01-order_id": webshop-01-order.get("id"),
                "webshop-01-payment_method": webshop-01-order.get(
                    "payment_method_title"
                ),
                "_store_id":webshop-01-order.get('_store_id'),
                "customer": customer,
                "customer_group": webshop-01-settings.customer_group,  # hard code group, as this was missing since v12
                "delivery_date": get_date_str(deliveryDate),
                "transaction_date": get_date_str(transactionDate),
                "company": webshop-01-settings.company,
                "selling_price_list": webshop-01-settings.price_list,
                "ignore_pricing_rule": 1,
                "items": get_order_items(
                    webshop-01-order.get("line_items"), webshop-01-settings, get_date_str(deliveryDate)
                ),
                "taxes": get_order_taxes(webshop-01-order, webshop-01-settings),
                # disabled discount as WooCommerce will send this both in the item rate and as discount
                # "apply_discount_on": "Net Total",
                # "discount_amount": flt(webshop-01-order.get("discount_total") or 0),
                "currency": webshop-01-order.get("currency"),
                "taxes_and_charges": tax_rules,
                "customer_address": billing_address,
                "shipping_address_name": shipping_address,
                "customer_provided_note": webshop-01-order.get('customer_note'),
                "goaffpro_vendor_id": webshop-01-order.get('gfp_v_id'),
                "goaffpro_referral_id": webshop-01-order.get('ref'),
            }
        )

        so.flags.ignore_mandatory = True

        # alle orders in ERP = submitted
        so.save(ignore_permissions=True)

        coupons = webshop-01-order.get('coupon_lines')
        for coupon in coupons:
            so.add_tag(coupon.get('code'))

        so.submit()

    else:
        so = frappe.get_doc("Sales Order", so)

    frappe.db.commit()
    make_webshop-01-log(
        title="create sales order",
        status="Success",
        method="create_sales_order",
        message="create sales_order",
        request_data=webshop-01-order,
        exception=False,
    )
    return so


def get_customer_address_from_order(type, webshop-01-order, customer):
    address_record = webshop-01-order[type.lower()]
    country = get_country_name(address_record.get("country"))
    if not frappe.db.exists("Country", country):
        country = "Switzerland"
    address_name = frappe.db.get_value(
        "Address",
        {
            "webshop-01-address_id": type,
            "address_line1": address_record.get("address_1"),
            "webshop-01-company_name": address_record.get("company") or "",
            "address_title": " ".join([address_record.get("first_name"), address_record.get("last_name")]),
            "address_type": type,
            "address_line1": address_record.get("address_1") or "Address 1",
            "address_line2": address_record.get("address_2"),
            "city": address_record.get("city") or "City",
            "state": address_record.get("state"),
            "pincode": address_record.get("postcode"),
            "country": country,
            "phone": address_record.get("phone"),
            "email_id": address_record.get("email") if type=="Billing" else address_record.get("shipping_email"),
        },
        "name",
    )
    if not address_name:
        try:
            address_name = frappe.get_doc(
                {
                    "doctype": "Address",
                    "webshop-01-address_id": type,
                    "webshop-01-company_name": address_record.get("company") or "",
                    "address_title": " ".join([address_record.get("first_name"), address_record.get("last_name")]),
                    "address_type": type,
                    "address_line1": address_record.get("address_1") or "Address 1",
                    "address_line2": address_record.get("address_2"),
                    "city": address_record.get("city") or "City",
                    "state": address_record.get("state"),
                    "pincode": address_record.get("postcode"),
                    "country": country,
                    "phone": address_record.get("phone"),
                    "email_id": address_record.get("email") if type=="Billing" else address_record.get("shipping_email"),
                    "links": [{"link_doctype": "Customer", "link_name": customer}],
                }
            ).insert()
            address_name = address_name.name

        except Exception as e:
            make_webshop-01-log(
                title=e,
                status="Error",
                method="create_customer_address",
                message=frappe.get_traceback(),
                request_data=webshop-01-order,
                exception=True,
            )

    return address_name

def custom_validate_party_accounts(self):
    return

def create_sales_invoice(webshop-01-order, webshop-01-settings, so):
    from erpnext.controllers.accounts_controller import AccountsController
    AccountsController.validate_party_account_currency = custom_validate_party_accounts
    if (
        not frappe.db.get_value(
            "Sales Invoice",
            {"new_webshop-01-order_id": webshop-01-order.get("id")},
            "name",
        )
        and so.docstatus == 1
        and not so.per_billed
    ):
        si = make_sales_invoice(so.name)
        si.new_webshop-01-order_id = webshop-01-order.get("id")
        si.naming_series = (
            webshop-01-settings.sales_invoice_series or "SI-woocommerce-"
        )
        si.flags.ignore_mandatory = True
        set_cost_center(si.items, webshop-01-settings.cost_center)
        si.submit()
        if cint(webshop-01-settings.import_payment) == 1:
            make_payment_entry_against_sales_invoice(si, webshop-01-settings)
        frappe.db.commit()


def set_cost_center(items, cost_center):
    for item in items:
        item.cost_center = cost_center


def make_payment_entry_against_sales_invoice(doc, webshop-01-settings):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    payment_entry = get_payment_entry(
        doc.doctype, doc.name, bank_account=webshop-01-settings.cash_bank_account
    )
    payment_entry.flags.ignore_mandatory = True
    payment_entry.reference_no = doc.name
    payment_entry.reference_date = nowdate()
    payment_entry.submit()


def create_delivery_note(webshop-01-order, webshop-01-settings, so):
    cache_repo = frappe.cache()
    cache_name = 'reserved-woocommerce-sn'
    try:
        dn = make_delivery_note(so.name)
        dn_items = []
        for item in dn.items:
            reserved_sn_b = cache_repo.lrange(cache_name, 0, cache_repo.llen(cache_name))
            reserved_sn_str = list(map(lambda x: x.decode('utf-8'), reserved_sn_b))
            serial_nos_list_str = auto_fetch_serial_number(qty=int(item.qty), item_code=item.item_code, warehouse=item.warehouse, exclude_sr_nos=reserved_sn_str)
            serial_nos_list = list(map(lambda x: frappe.get_doc('Serial No', x), serial_nos_list_str))
            sn_dict = {}

            for sn in serial_nos_list_str:
                cache_repo.rpush(cache_name, sn)

            for serial_no in serial_nos_list:
                if sn_dict.get(serial_no.batch_no) is None:
                    sn_dict[serial_no.batch_no] = {
                        'qty': 1,
                        'serial_nos': [serial_no.name]
                    }
                else:
                    sn_dict[serial_no.batch_no]['qty'] += 1
                    sn_dict[serial_no.batch_no]['serial_nos'].append(serial_no.name)

            for batch_no in sn_dict.keys():
                dn_item = copy(item)
                dn_item.name = None
                dn_item.qty = sn_dict[batch_no]['qty']
                dn_item.batch_no = batch_no
                dn_item.serial_no = "\n".join(sn_dict[batch_no]['serial_nos'])
                dn_items.append(dn_item)

            # serial_no_str = "\n".join(serial_no_list)
            # dn.items[idx].serial_no = serial_no_str
            # if len(serial_no_list) > 0:
            #     sn = frappe.get_doc('Serial No', serial_no_list[0])
            #     dn.items[idx].batch_no = sn.batch_no
        dn.items = dn_items
        # dn.flags.ignore_mandatory = True
        dn.save()
        if dn.total_qty != so.total_qty:
            mention_section = get_mention_comment(webshop-01-settings.contact_person)
            comment = "<div><p>{}<br>{}</p></div>".format(mention_section, "Warning!!! The amount of items in the Delivery Note is less than amount in Sales Order.")
            dn.add_comment("Comment", comment)
        frappe.db.commit()

        make_webshop-01-log(
            title="create Delivery Note",
            status="Success",
            method="create_delivery_note",
            message="create delivery_note",
            request_data=webshop-01-order,
            exception=False,
        )
    except Exception as e:
        mention_section = get_mention_comment(webshop-01-settings.contact_person)
        comment = "<div><p>{} {}</p></div>".format(mention_section, "Cannot create Delivery Note for this Sales Order, please check!")
        so.add_comment("Comment", comment)
        frappe.db.commit()
        make_webshop-01-log(
            title=e,
            status="Error",
            method="create_delivery_note",
            message=frappe.get_traceback(),
            request_data=webshop-01-order,
            exception=True,
        )

def get_fulfillment_items(dn_items, fulfillment_items):
    return [
        dn_item.update({"qty": item.get("quantity")})
        for item in fulfillment_items
        for dn_item in dn_items
        if get_item_code(item) == dn_item.item_code
    ]


def get_order_items(order_items, webshop-01-settings, delivery_date):
    items = []
    for webshop-01-item in order_items:
        item_code = get_item_code(webshop-01-item)
        items.append(
            {
                "item_code": item_code,
                "rate": webshop-01-item.get("price"),
                "delivery_date": delivery_date,
                "qty": webshop-01-item.get("quantity"),
                "warehouse": webshop-01-settings.warehouse,
            }
        )
    return items


def get_item_code(webshop-01-item):
    if cint(webshop-01-item.get("variation_id")) > 0:
        # variation
        item_code = frappe.db.get_value(
            "Item",
            {"webshop-01-product_id": webshop-01-item.get("variation_id")},
            "item_code",
        )
    else:
        # single
        item_code = frappe.db.get_value(
            "Item",
            {"webshop-01-product_id": webshop-01-item.get("product_id")},
            "item_code",
        )

    return item_code


def get_order_taxes(webshop-01-order, webshop-01-settings):
    taxes = []
    for tax in webshop-01-order.get("tax_lines"):

        webshop-01-tax = get_webshop-01-tax(tax.get("rate_id"))
        rate = webshop-01-tax.get("rate")
        name = webshop-01-tax.get("name")

        taxes.append(
            {
                "charge_type": "Actual",
                "account_head": get_tax_account_head(webshop-01-tax),
                "description": "{0} - {1}%".format(name, rate),
                "rate": rate,
                "tax_amount": flt(tax.get("tax_total") or 0)
                + flt(tax.get("shipping_tax_total") or 0),
                "included_in_print_rate": 0,
                "cost_center": webshop-01-settings.cost_center,
            }
        )
    # old code with conditional brutto/netto prices
    # taxes.append({
        #     "charge_type": "On Net Total" if webshop-01-order.get("prices_include_tax") else "Actual",
        #     "account_head": get_tax_account_head(webshop-01-tax),
        #     "description": "{0} - {1}%".format(name, rate),
        #     "rate": rate,
        #     "tax_amount": flt(tax.get("tax_total") or 0) + flt(tax.get("shipping_tax_total") or 0),
        #     "included_in_print_rate": 1 if webshop-01-order.get("prices_include_tax") else 0,
        #     "cost_center": webshop-01-settings.cost_center
        # })
    taxes = update_taxes_with_fee_lines(
        taxes, webshop-01-order.get("fee_lines"), webshop-01-settings
    )
    taxes = update_taxes_with_shipping_lines(
        taxes, webshop-01-order.get("shipping_lines"), webshop-01-settings
    )

    return taxes


def update_taxes_with_fee_lines(taxes, fee_lines, webshop-01-settings):
    for fee_charge in fee_lines:
        taxes.append(
            {
                "charge_type": "Actual",
                "account_head": webshop-01-settings.fee_account,
                "description": fee_charge["name"],
                "tax_amount": fee_charge["amount"],
                "cost_center": webshop-01-settings.cost_center,
            }
        )

    return taxes


def update_taxes_with_shipping_lines(taxes, shipping_lines, webshop-01-settings):
    for shipping_charge in shipping_lines:
        #
        taxes.append(
            {
                "charge_type": "Actual",
                "account_head": get_shipping_account_head(shipping_charge),
                "description": shipping_charge["method_title"],
                "tax_amount": shipping_charge["total"],
                "cost_center": webshop-01-settings.cost_center,
            }
        )

    return taxes


def get_shipping_account_head(shipping):
    shipping_title = shipping.get("method_title") #.encode("utf-8")

    shipping_account = frappe.db.get_value(
        "woocommerce Tax Account",
        {"parent": "WooCommerce Config", "webshop-01-tax": shipping_title},
        "tax_account",
    )

    if not shipping_account:
        frappe.throw(
            "Tax Account not specified for woocommerce shipping method  {0}".format(
                shipping.get("method_title")
            )
        )

    return shipping_account


def get_tax_account_head(tax):
#    tax_title = tax.get("name").encode("utf-8") or tax.get("method_title").encode(
    tax_title = tax.get("name") or tax.get("method_title")

    tax_account = frappe.db.get_value(
        "woocommerce Tax Account",
        {"parent": "WooCommerce Config", "webshop-01-tax": tax_title},
        "tax_account",
    )

    if not tax_account:
        frappe.throw(
            "Tax Account not specified for woocommerce Tax {0}".format(tax.get("name"))
        )

    return tax_account


def close_synced_webshop-01-orders():
    for webshop-01-order in get_webshop-01-orders():
        if webshop-01-order.get("status").lower() != "cancelled":
            order_data = {"status": "completed"}
            try:
                put_request(
                    "orders/{0}".format(webshop-01-order.get("id")), order_data
                )

            except requests.exceptions.HTTPError as e:
                make_webshop-01-log(
                    title=e,
                    status="Error",
                    method="close_synced_webshop-01-orders",
                    message=frappe.get_traceback(),
                    request_data=webshop-01-order,
                    exception=True,
                )


def close_synced_webshop-01-order(wooid):
    order_data = {"status": "completed"}
    try:
        put_request("orders/{0}".format(wooid), order_data)

    except requests.exceptions.HTTPError as e:
        make_webshop-01-log(
            title=e.message,
            status="Error",
            method="close_synced_webshop-01-order",
            message=frappe.get_traceback(),
            request_data=webshop-01-order,
            exception=True,
        )
