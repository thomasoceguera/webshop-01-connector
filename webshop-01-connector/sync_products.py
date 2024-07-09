from __future__ import unicode_literals
import frappe
from frappe.utils import cstr
from frappe import _
import requests.exceptions
from .exceptions import woocommerceError
from .utils import make_webshop-01-log, disable_webshop-01-sync_for_item
from erpnext.stock.utils import get_bin
from frappe.utils import cstr, flt, cint, get_files_path
from .webshop-01-requests import post_request, get_webshop-01-items,get_webshop-01-item_variants,  put_request, get_webshop-01-item_image
import base64, requests, datetime, os
from frappe.utils import get_datetime
import json

webshop-01-variants_attr_list = ["option1", "option2", "option3"]

def sync_products(price_list, warehouse, sync_from_woocommerce=False):
    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
    webshop-01-item_list = []
    if sync_from_woocommerce:
        sync_webshop-01-items(warehouse, webshop-01-item_list)
    frappe.local.form_dict.count_dict["products"] = len(webshop-01-item_list)
    if webshop-01-settings.if_not_exists_create_item_to_woocommerce == 1:
        sync_erpnext_items(price_list, warehouse, webshop-01-item_list)
    if webshop-01-settings.rewrite_stock_uom_from_wc_unit == 1:
        rewrite_stock_uom_from_wc_unit()

def sync_webshop-01-items(warehouse, webshop-01-item_list):
    for webshop-01-item in get_webshop-01-items():
        try:
            make_item(warehouse, webshop-01-item, webshop-01-item_list)

        except woocommerceError as e:
            make_webshop-01-log(title="{0}".format(e), status="Error", method="sync_webshop-01-items", message=frappe.get_traceback(),
                request_data=webshop-01-item, exception=True)

        except Exception as e:
            if e.args[0] and e.args[0] == 402:
                raise e
            else:
                make_webshop-01-log(title="{0}".format(e), status="Error", method="sync_webshop-01-items", message=frappe.get_traceback(),
                    request_data=webshop-01-item, exception=True)

def make_item(warehouse, webshop-01-item, webshop-01-item_list):
    
    if has_variants(webshop-01-item):
        #replace woocommerce variants id array with actual variant info
        webshop-01-item['variants'] = get_webshop-01-item_variants(webshop-01-item.get("id"))
        
        attributes = create_attribute(webshop-01-item)
        create_item(webshop-01-item, warehouse, 1, attributes=attributes, webshop-01-item_list=webshop-01-item_list)
        create_item_variants(webshop-01-item, warehouse, attributes, webshop-01-variants_attr_list, webshop-01-item_list)

    else:
        """webshop-01-item["variant_id"] = webshop-01-item['variants'][0]["id"]"""
        attributes = create_attribute(webshop-01-item)
        create_item(webshop-01-item, warehouse, attributes=attributes, webshop-01-item_list=webshop-01-item_list)

def create_item(webshop-01-item, warehouse, has_variant=0, attributes=None, variant_of=None, webshop-01-item_list=[], template_item=None):
    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
    valuation_method = webshop-01-settings.get("valuation_method")
    weight_unit =  webshop-01-settings.get("weight_unit")
    
    item_code = get_item_code(webshop-01-item, webshop-01-settings)

    item_dict = {
        "doctype": "Item",
        "webshop-01-product_id": webshop-01-item.get("id"),
        "webshop-01-variant_id": webshop-01-item.get("id"),
        "variant_of": variant_of,
        "sync_with_woocommerce": 1,
        "is_stock_item": 1,
        "item_name": webshop-01-item.get("name"),
        "valuation_method": valuation_method,
        "description": webshop-01-item.get("description") or webshop-01-item.get("name"),
        "webshop-01-description": webshop-01-item.get("description") or webshop-01-item.get("name"),
        "webshop-01-short_description": webshop-01-item.get("short_description") or webshop-01-item.get("name"),
        "item_group": get_item_group(webshop-01-item.get("categories")),
        "has_variants": has_variant,
        "attributes": attributes or [],
        "stock_uom": get_erpnext_uom(webshop-01-item, webshop-01-settings, attributes),
        "stock_keeping_unit": webshop-01-item.get("sku"), #or get_sku(webshop-01-item),
        "default_warehouse": warehouse,
        "image": get_item_image(webshop-01-item),
        "weight_uom": weight_unit, #webshop-01-item.get("weight_unit"),
        "weight_per_unit": webshop-01-item.get("weight"),
        "web_long_description": webshop-01-item.get("description") or webshop-01-item.get("name")
        #"uoms": get_conversion_table(attributes, webshop-01-settings) if not has_variant else []
    }
    
    # in case of naming series (item_code = None), set naming series
    if not item_code:
        item_dict['naming_series'] = webshop-01-settings.item_code_naming_series
        # for variants, apply WooCommerce ID (because naming series is not applicable)
        item_dict['item_code'] = str(webshop-01-item.get("id"))
    else:
        item_dict['item_code'] = item_code
        
    if template_item:
        #variants
        item_dict["product_category"] = get_categories(template_item, is_variant=True)
    else:
        #single & templates
        item_dict["product_category"] = get_categories(webshop-01-item, is_variant=False)
            
    
    #item_dict["web_long_description"] = item_dict["webshop-01-description"]
    
    if not is_item_exists(item_dict, attributes, variant_of=variant_of, webshop-01-item_list=webshop-01-item_list):
        item_details = get_item_details(webshop-01-item)

        if not item_details:
            
            new_item = frappe.get_doc(item_dict)
            new_item.insert()
            name = new_item.name

        else:
            update_item(item_details, item_dict)
            name = item_details.name

        if not has_variant:
            add_to_price_list(webshop-01-item, name)
    
        frappe.db.commit()
        
def get_item_code(webshop-01-item, webshop-01-settings):
    item_code = ''
    if webshop-01-settings.item_code_based_on == 'WooCommerce ID':
        item_code = str(webshop-01-item.get("id"))
    elif webshop-01-settings.item_code_based_on == 'WooCommerce ID + Name':
        item_code = str(webshop-01-item.get("id")) + str(webshop-01-item.get("name"))
    elif webshop-01-settings.item_code_based_on == 'WooCommerce Name':
        item_code = str(webshop-01-item.get("name"))
    elif webshop-01-settings.item_code_based_on == 'Random Hash':
        item_code = frappe.generate_hash(length=10)
    elif webshop-01-settings.item_code_based_on == 'Naming Series':
        item_code = None
        
    return item_code
    
def get_erpnext_uom(webshop-01-item, webshop-01-settings, attributes=[]):
    if len(attributes) > 0:
        for attr in attributes:
            if attr["attribute"] == webshop-01-settings.attribute_for_uom:
                uom_match = frappe.get_all("UOM", filters={'uom_name': "{0}".format(attr["attribute_value"])}, fields=['name'])
                if len(uom_match) > 0:
                    return attr["attribute_value"]
                else:
                    frappe.log_error("{0} {1}".format(attr, webshop-01-item))
                    new_uom = frappe.get_doc({
                        'doctype': 'UOM',
                        'uom_name': attr["attribute_value"]
                    }).insert()
                    return attr["attribute_value"]
    else:
        return 'Nos'
        
#def get_conversion_table(attributes, webshop-01-settings):
#    table = []
#    conversion_value = False
#    attribute_for_uom_conversion = webshop-01-settings.attribute_for_uom_conversion or 'Nos'
#    try:
#        for attr in attributes:
#            if attr["attribute"] == attribute_for_uom_conversion:
#                conversion_value = attr["attribute_value"]
#        if conversion_value:
#            table.append({
#                "uom": webshop-01-settings.dimension_units or 'Nos',
#                "conversion_factor": int(conversion_value)
#            })
#    except Exception as e:
#        make_webshop-01-log(title="{0}".format(e), status="Error", method="get_conversion_table", message=frappe.get_traceback(),
#                    request_data=attributes, exception=True)
#    
#    return table

def create_item_variants(webshop-01-item, warehouse, attributes, webshop-01-variants_attr_list, webshop-01-item_list):
    template_item = frappe.db.get_value("Item", filters={"webshop-01-product_id": webshop-01-item.get("id")},
        fieldname=["name", "stock_uom"], as_dict=True)
    

    if template_item:
        for variant in webshop-01-item.get("variants"):
            webshop-01-item_variant = {
                "id" : variant.get("id"),
                "webshop-01-variant_id" : variant.get("id"),
                "name": webshop-01-item.get("name"),
                "item_code":  str(variant.get("id")), # + " " + webshop-01-item.get("name"),
                "title": variant.get("name"),
                "item_group": get_item_group(webshop-01-item.get("")),
                "sku": variant.get("sku"),
                "uom": template_item.stock_uom or _("Nos"),
                "item_price": variant.get("price"),
                "variant_id": variant.get("id"),
                "weight_unit": variant.get("weight_unit"),
                "net_weight": variant.get("weight")
            }

            webshop-01-variants_attr_list = variant.get("attributes")
            # create attribute list based on attribute name as key
            for variant in webshop-01-variants_attr_list:
                for attr in attributes:
                    if attr['attribute'] == variant['name']:
                        attr['attribute_value'] = get_attribute_value(variant.get("option"), variant)
                        break
            create_item(webshop-01-item_variant, warehouse, 0, attributes, 
                        variant_of=template_item.name, webshop-01-item_list=webshop-01-item_list, template_item=template_item)
                        
#add childtable with categories into items
def get_categories(webshop-01-item, is_variant=False):
    categories = []
    if not is_variant:
        try:
            for category in webshop-01-item.get("categories"):
                categories.append({'category': category.get("name")})
        except:
            pass
    else:
        try:
            erpnext_categories = frappe.db.sql("""SELECT `category` FROM `tabItem Product Category` WHERE `parent` = '{item_code}'""".format(item_code=webshop-01-item.name), as_list=True)
            for category in erpnext_categories:
                categories.append({'category': category[0]})
        except:
            pass
    return categories

#fix this
def is_item_exists(item_dict, attributes=None, variant_of=None, webshop-01-item_list=[]):
    webshop-01-item_list.append(cstr(item_dict.get("webshop-01-product_id")))

    erp_item_match = frappe.get_all("Item", 
                filters={'webshop-01-product_id': item_dict.get("webshop-01-product_id")},
                fields=['name', 'stock_uom'])
    if len(erp_item_match) > 0:
        # item does exist in ERP --> Update
        update_item(item_details=erp_item_match[0], item_dict=item_dict)
        return True

    else:
        return False

def update_item(item_details, item_dict):
    item = frappe.get_doc("Item", item_details['name'])
        
    item_dict["stock_uom"] = item_details['stock_uom']

    if not item_dict["web_long_description"]:
        del item_dict["web_long_description"]

    if item_dict.get("warehouse"):
        del item_dict["warehouse"]

    del item_dict["description"]
    del item_dict["item_code"]
    del item_dict["variant_of"]
    del item_dict["item_name"]
    if "attributes" in item_dict:
        del item_dict["attributes"]

    item.update(item_dict)
    item.flags.ignore_mandatory = True
    item.save()
                        
def has_variants(webshop-01-item):
    if len(webshop-01-item.get("variations")) >= 1:
        return True
    return False

# this function makes sure that all attributes exist in ERPNext as "Item Attribute"
def create_attribute(webshop-01-item):
    attribute = []
    # woocommerce item dict
    for attr in webshop-01-item.get('attributes'):
        if not frappe.db.get_value("Item Attribute", attr.get("name"), "name"):
            new_item_attribute_entry = frappe.get_doc({
                "doctype": "Item Attribute",
                "attribute_name": attr.get("name"),
                "webshop-01-attribute_id": attr.get("id"),
                "item_attribute_values": []
            })
            
            for attr_value in attr.get("options"):
                row = new_item_attribute_entry.append('item_attribute_values', {})
                row.attribute_value = attr_value[:140]
                row.abbr = attr_value[:140]
            
            new_item_attribute_entry.insert()
            
            if len(attr.get("options")[0]) > 140:
                attribute_value = attr.get("options")[0][:140]
            else:
                attribute_value = attr.get("options")[0]
            attribute.append({"attribute": attr.get("name"), "attribute_value": attribute_value})
        else:
            # check for attribute values
            item_attr = frappe.get_doc("Item Attribute", attr.get("name"))
            if not item_attr.numeric_values:
            # line below hinders insert of new attribute values for existing attributes
            #    if not item_attr.get("webshop-01-attribute_id"):
                    item_attr.webshop-01-attribute_id = attr.get("id")
                    old_len = len(item_attr.item_attribute_values)
                    item_attr = set_new_attribute_values(item_attr, attr.get("options"))
                    if len(item_attr.item_attribute_values) > old_len:    # only save item attributes if they have changed
                        item_attr.save()
            if len(attr.get("options")[0]) > 140:
                attribute_value = attr.get("options")[0][:140]
            else:
                attribute_value = attr.get("options")[0]
            attribute.append({"attribute": attr.get("name"), "attribute_value": attribute_value})
                #frappe.log_error(attribute.append.format(attribute.append), "append attributes")
            #else:
                #attribute.append({
                    #"attribute": attr.get("name"),
                    #"from_range": item_attr.get("from_range"),
                    #"to_range": item_attr.get("to_range"),
                    #"increment": item_attr.get("increment"),
                    #"numeric_values": item_attr.get("numeric_values")
                #})

    return attribute

def set_new_attribute_values(item_attr, values):
    for attr_value in values:
        if not any((d.abbr.lower() == attr_value[:140].lower() or d.attribute_value.lower() == attr_value[:140].lower())\
        for d in item_attr.item_attribute_values):
            item_attr.append("item_attribute_values", {
                "attribute_value": attr_value[:140],
                "abbr": attr_value[:140]
            })
    return item_attr

def get_attribute_value(variant_attr_val, attribute):
    attribute_value = frappe.db.sql("""select attribute_value from `tabItem Attribute Value`
        where parent = %s and (abbr = %s or attribute_value = %s)""", (attribute["name"], variant_attr_val,
        variant_attr_val), as_list=1)
    # check if this is really not available due to numeric value or if it is from changing attributes after creation
    if len(attribute_value) == 0 and ("{0}".format(cint(variant_attr_val)) != "{0}".format(variant_attr_val)):
        frappe.log_error("Attribute value mismatch: {attr}: {value} (potential change in attribute?".format(attr=attribute, 
            value=variant_attr_val), "WooCommerce Attribute Mismatch")
        return "{0}".format(variant_attr_val)
    return attribute_value[0][0] if len(attribute_value)>0 else cint(variant_attr_val)

def get_item_group(product_type=None):
    #woocommerce supports multiple categories per item, so we just pick a default in ERPNext
    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
    return webshop-01-settings.get("default_item_group")

def add_to_price_list(item, name):
    price_list = frappe.db.get_value("WooCommerce Config", None, "price_list")
    item_price_name = frappe.db.get_value("Item Price",
        {"item_code": name, "price_list": price_list}, "name")
    rate = item.get("sale_price") or item.get("price") or item.get("item_price") or 0
    if float(rate) > 0 and frappe.db.exists("Item", name):
        # only apply price if it is bigger than 0
        if not item_price_name:
            frappe.get_doc({
                "doctype": "Item Price",
                "price_list": price_list,
                "item_code": name,
                "price_list_rate": rate
            }).insert()
        else:
            item_rate = frappe.get_doc("Item Price", item_price_name)
            item_rate.price_list_rate = rate
            item_rate.save()


def get_item_image(webshop-01-item):
    if webshop-01-item.get("images"):
        for image in webshop-01-item.get("images"):
            if image.get("position") == 0: # the featured image
                return image
            return None
    else:
        return None

def get_item_details(webshop-01-item):
    item_details = {}

    item_details = frappe.db.get_value("Item", {"webshop-01-product_id": webshop-01-item.get("id")},
        ["name", "stock_uom", "item_name"], as_dict=1)

    if item_details:
        return item_details

    else:
        item_details = frappe.db.get_value("Item", {"webshop-01-variant_id": webshop-01-item.get("id")},
            ["name", "stock_uom", "item_name"], as_dict=1)
        return item_details

def sync_erpnext_items(price_list, warehouse, webshop-01-item_list):
    webshop-01-item_list = {}
    for item in get_webshop-01-items():
        webshop-01-item_list[int(item['id'])] = item

    for item in get_erpnext_items(price_list):
        try:
            sync_item_with_woocommerce(item, price_list, warehouse, webshop-01-item_list.get(item.get('webshop-01-product_id')))
            frappe.local.form_dict.count_dict["products"] += 1

        except woocommerceError as e:
            make_webshop-01-log(title="{0}".format(e), status="Error", method="sync_webshop-01-items", message=frappe.get_traceback(),
                request_data=item, exception=True)
        except Exception as e:
            make_webshop-01-log(title="{0}".format(e), status="Error", method="sync_webshop-01-items", message=frappe.get_traceback(),
                request_data=item, exception=True)

def get_erpnext_items(price_list):
    erpnext_items = []
    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")

    last_sync_condition, item_price_condition = "", ""
    if webshop-01-settings.last_sync_datetime:
        last_sync_condition = "and modified >= '{0}' ".format(webshop-01-settings.last_sync_datetime)
        item_price_condition = "AND `tabItem Price`.`modified` >= '{0}' ".format(webshop-01-settings.last_sync_datetime)

    item_from_master = """select name, item_code, item_name, item_group,
        description, webshop-01-description, has_variants, variant_of, stock_uom, image, webshop-01-product_id,
        webshop-01-variant_id, sync_qty_with_woocommerce, weight_per_unit, weight_uom from tabItem
        where sync_with_woocommerce=1 and (variant_of is null or variant_of = '')
        and (disabled is null or disabled = 0)  %s """ % last_sync_condition

    erpnext_items.extend(frappe.db.sql(item_from_master, as_dict=1))

    template_items = [item.name for item in erpnext_items if item.has_variants]

    if len(template_items) > 0:
    #    item_price_condition += ' and i.variant_of not in (%s)'%(' ,'.join(["'%s'"]*len(template_items)))%tuple(template_items)
        # escape raw item name
        for i in range(len(template_items)):
            template_items[i] = template_items[i].replace("'", r"\'")
        # combine condition
        item_price_condition += ' AND `tabItem`.`variant_of` NOT IN (\'{0}\')'.format(
            ("' ,'".join(template_items)))
    
    item_from_item_price = """SELECT `tabItem`.`name`, 
                                     `tabItem`.`item_code`, 
                                     `tabItem`.`item_name`, 
                                     `tabItem`.`item_group`, 
                                     `tabItem`.`description`,
                                     `tabItem`.`webshop-01-description`, 
                                     `tabItem`.`has_variants`, 
                                     `tabItem`.`variant_of`, 
                                     `tabItem`.`stock_uom`, 
                                     `tabItem`.`image`, 
                                     `tabItem`.`webshop-01-product_id`,
                                     `tabItem`.`webshop-01-variant_id`, 
                                     `tabItem`.`sync_qty_with_woocommerce`, 
                                     `tabItem`.`weight_per_unit`, 
                                     `tabItem`.`weight_uom`
        FROM `tabItem`, `tabItem Price`
        WHERE `tabItem Price`.`price_list` = '%s' 
          AND `tabItem`.`name` = `tabItem Price`.`item_code`
          AND `tabItem`.`sync_with_woocommerce` = 1 
          AND (`tabItem`.`disabled` IS NULL OR `tabItem`.`disabled` = 0) %s""" %(price_list, item_price_condition)
    frappe.log_error("{0}".format(item_from_item_price))



    updated_price_item_list = frappe.db.sql(item_from_item_price, as_dict=1)

    # to avoid item duplication
    return [frappe._dict(tupleized) for tupleized in set(tuple(item.items())
        for item in erpnext_items + updated_price_item_list)]

def sync_item_with_woocommerce(item, price_list, warehouse, webshop-01-item=None):
    variant_item_name_list = []
    variant_list = []
    item_data = {
            "name": item.get("item_name"),
            "description": item.get("webshop-01-description") or item.get("web_long_description") or item.get("description"),
            "short_description": item.get("description") or item.get("web_long_description") or item.get("webshop-01-description"),
    }
    item_data.update( get_price_and_stock_details(item, warehouse, price_list) )

    if item.get("has_variants"):  # we are dealing a variable product
        item_data["type"] = "variable"

        if item.get("variant_of"):
            item = frappe.get_doc("Item", item.get("variant_of"))

        variant_list, options, variant_item_name = get_variant_attributes(item, price_list, warehouse)
        item_data["attributes"] = options

    else:   # we are dealing with a simple product
        item_data["type"] = "simple"


    erp_item = frappe.get_doc("Item", item.get("name"))
    erp_item.flags.ignore_mandatory = True

    if not item.get("webshop-01-product_id"):
        item_data["status"] = "draft"

        create_new_item_to_woocommerce(item, item_data, erp_item, variant_item_name_list)

    else:
        item_data["id"] = item.get("webshop-01-product_id")
        try:
            put_request("products/{0}".format(item.get("webshop-01-product_id")), item_data)

        except requests.exceptions.HTTPError as e:
            if e.args[0] and (e.args[0].startswith("404") or e.args[0].startswith("400")):
                if frappe.db.get_value("WooCommerce Config", "WooCommerce Config", "if_not_exists_create_item_to_woocommerce"):
                    item_data["id"] = ''
                    create_new_item_to_woocommerce(item, item_data, erp_item, variant_item_name_list)
                else:
                    disable_webshop-01-sync_for_item(erp_item)
            else:
                raise e

    if variant_list:
        for variant in variant_list:
            erp_varient_item = frappe.get_doc("Item", variant["item_name"])
            if erp_varient_item.webshop-01-product_id: #varient exist in woocommerce let's update only
                r = put_request("products/{0}/variations/{1}".format(erp_item.webshop-01-product_id, erp_varient_item.webshop-01-product_id),variant)
            else:
                webshop-01-variant = post_request("products/{0}/variations".format(erp_item.webshop-01-product_id), variant)

                erp_varient_item.webshop-01-product_id = webshop-01-variant.get("id")
                erp_varient_item.webshop-01-variant_id = webshop-01-variant.get("id")
                erp_varient_item.save()

    if erp_item.image:
        try:
            item_image = get_item_image(webshop-01-item)
        except:
            item_image = None
        img_details = frappe.db.get_value("File", {"file_url": erp_item.image}, ["modified"])

        if not item_image or datetime.datetime(item_image.date_modified, '%Y-%m-%dT%H:%M:%S') < datetime.datetime(img_details[0], '%Y-%m-%d %H:%M:%S.%f'):
            sync_item_image(erp_item)

    frappe.db.commit()


def create_new_item_to_woocommerce(item, item_data, erp_item, variant_item_name_list):
    new_item = post_request("products", item_data)

    erp_item.webshop-01-product_id = new_item.get("id")

    #if not item.get("has_variants"):
        #erp_item.webshop-01-variant_id = new_item['product']["variants"][0].get("id")

    erp_item.save()
    #update_variant_item(new_item, variant_item_name_list)

def sync_item_image(item):
    image_info = {
        "images": [{}]
    }

    if item.image:
        img_details = frappe.db.get_value("File", {"file_url": item.image}, ["file_name", "file_url", "is_private", "content_hash"])

        image_info["images"][0]["src"] = 'https://' + cstr(frappe.local.site) + img_details[1]
        image_info["images"][0]["position"] = 0

        post_request("products/{0}".format(item.webshop-01-product_id), image_info)


def validate_image_url(url):
    """ check on given url image exists or not"""
    res = requests.get(url)
    if res.headers.get("content-type") in ('image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/tiff'):
        return True
    return False

def item_image_exists(webshop-01-product_id, image_info):
    """check same image exist or not"""
    for image in get_webshop-01-item_image(webshop-01-product_id):
        if image_info.get("image").get("filename"):
            if os.path.splitext(image.get("src"))[0].split("/")[-1] == os.path.splitext(image_info.get("image").get("filename"))[0]:
                return True
        elif image_info.get("image").get("src"):
            if os.path.splitext(image.get("src"))[0].split("/")[-1] == os.path.splitext(image_info.get("image").get("src"))[0].split("/")[-1]:
                return True
        else:
            return False

def update_variant_item(new_item, item_code_list):
    for i, name in enumerate(item_code_list):
        erp_item = frappe.get_doc("Item", name)
        erp_item.flags.ignore_mandatory = True
        erp_item.webshop-01-product_id = new_item['product']["variants"][i].get("id")
        erp_item.webshop-01-variant_id = new_item['product']["variants"][i].get("id")
        erp_item.save()

def get_variant_attributes(item, price_list, warehouse):
    options, variant_list, variant_item_name, attr_sequence = [], [], [], []
    attr_dict = {}

    for i, variant in enumerate(frappe.get_all("Item", filters={"variant_of": item.get("name")},
        fields=['name'])):

        item_variant = frappe.get_doc("Item", variant.get("name"))

        data = (get_price_and_stock_details(item_variant, warehouse, price_list))
        data["item_name"] = item_variant.name
        data["attributes"] = []
        for attr in item_variant.get('attributes'):
            attribute_option = {}
            attribute_option["name"] = attr.attribute
            attribute_option["option"] = attr.attribute_value
            data["attributes"].append(attribute_option)

            if attr.attribute not in attr_sequence:
                attr_sequence.append(attr.attribute)
            if not attr_dict.get(attr.attribute):
                attr_dict.setdefault(attr.attribute, [])

            attr_dict[attr.attribute].append(attr.attribute_value)

        variant_list.append(data)


    for i, attr in enumerate(attr_sequence):
        options.append({
            "name": attr,
            "visible": "True",
            "variation": "True",
            "position": i+1,
            "options": list(set(attr_dict[attr]))
        })
    return variant_list, options, variant_item_name

def get_price_and_stock_details(item, warehouse, price_list):
    actual_qty = frappe.db.get_value("Bin", {"item_code":item.get("item_code"), "warehouse": warehouse}, "actual_qty")
    reserved_qty = frappe.db.get_value("Bin", {"item_code":item.get("item_code"), "warehouse": warehouse}, "reserved_qty")
    qty = (actual_qty or 0) - (reserved_qty or 0)
    price = frappe.db.get_value("Item Price", 
            {"price_list": price_list, "item_code": item.get("item_code")}, "price_list_rate")

    item_price_and_quantity = {
        "regular_price": "{0}".format(flt(price)) #only update regular price
    }

    if item.weight_per_unit:
        if item.weight_uom and item.weight_uom.lower() in ["kg", "g", "oz", "lb", "lbs"]:
            item_price_and_quantity.update({
                "weight": "{0}".format(get_weight_in_webshop-01-unit(item.weight_per_unit, item.weight_uom))
            })

    if item.stock_keeping_unit:
        item_price_and_quantity = {
        "sku": "{0}".format(item.stock_keeping_unit)
    }

    if item.get("sync_qty_with_woocommerce"):
        item_price_and_quantity.update({
            "stock_quantity": "{0}".format(cint(qty) if qty else 0),
            "manage_stock": "True"
        })

    #rlavaud Do I need this???
    if item.webshop-01-variant_id:
        item_price_and_quantity["id"] = item.webshop-01-variant_id


    return item_price_and_quantity

def get_weight_in_grams(weight, weight_uom):
    convert_to_gram = {
        "kg": 1000,
        "lb": 453.592,
        "oz": 28.3495,
        "g": 1
    }

    return weight * convert_to_gram[weight_uom.lower()]

def get_weight_in_webshop-01-unit(weight, weight_uom):
    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
    weight_unit = webshop-01-settings.weight_unit
    convert_to_gram = {
        "kg": 1000,
        "lb": 453.592,
        "lbs": 453.592,
        "oz": 28.3495,
        "g": 1
    }
    convert_to_oz = {
        "kg": 0.028,
        "lb": 0.062,
        "lbs": 0.062,
        "oz": 1,
        "g": 28.349
    }
    convert_to_lb = {
        "kg": 1000,
        "lb": 1,
        "lbs": 1,
        "oz": 16,
        "g": 0.453
    }
    convert_to_kg = {
        "kg": 1,
        "lb": 2.205,
        "lbs": 2.205,
        "oz": 35.274,
        "g": 1000
    }
    if weight_unit.lower() == "g":
        return weight * convert_to_gram[weight_uom.lower()]

    if weight_unit.lower() == "oz":
        return weight * convert_to_oz[weight_uom.lower()]

    if weight_unit.lower() == "lb"  or weight_unit.lower() == "lbs":
        return weight * convert_to_lb[weight_uom.lower()]

    if weight_unit.lower() == "kg":
        return weight * convert_to_kg[weight_uom.lower()]



def trigger_update_item_stock(doc, method):
    if doc.flags.via_stock_ledger_entry:
        webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
        if webshop-01-settings.webshop-01-url and webshop-01-settings.enable_woocommerce and webshop-01-settings.trigger_update_item_stock:
            update_item_stock(doc.item_code, webshop-01-settings, doc)

def update_item_stock_qty(force=False):
    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
    for item in frappe.get_all("Item", fields=["item_code"], filters={"sync_qty_with_woocommerce": '1', "disabled": ("!=", 1)}):
        try:
            update_item_stock(item.item_code, webshop-01-settings, force=force)
        except woocommerceError as e:
            make_webshop-01-log(title="{0}".format(e), status="Error", method="sync_webshop-01-items", message=frappe.get_traceback(),
                request_data=item, exception=True)

        except Exception as e:
            if e.args[0] and e.args[0].startswith("402"):
                raise e
            else:
                make_webshop-01-log(title="{0}".format(e), status="Error", method="sync_webshop-01-items", message=frappe.get_traceback(),
                    request_data=item, exception=True)

def update_item_stock(item_code, webshop-01-settings, bin=None, force=False):
    item = frappe.get_doc("Item", item_code)
    if item.sync_qty_with_woocommerce:
        if not item.webshop-01-product_id:
            make_webshop-01-log(title="WooCommerce ID missing", status="Error", method="sync_webshop-01-items",
                message="Please sync WooCommerce IDs to ERP (missing for item {0})".format(item_code), request_data=item_code, exception=True)
        else:
            # removed bin date check
            # check bin creation date
            last_sync_datetime = get_datetime(webshop-01-settings.last_sync_datetime)
            bin_since_last_sync = frappe.db.sql("""SELECT COUNT(`name`) FROM `tabBin` WHERE `item_code` = '{item_code}' AND `modified` > '{last_sync_datetime}'""".format(item_code=item_code, last_sync_datetime=last_sync_datetime), as_list=True)[0][0]
            if bin_since_last_sync > 0 or force != False:
                bin = get_bin(item_code, webshop-01-settings.warehouse)

                actual_qty = bin.actual_qty
                reserved_qty = bin.reserved_qty
                qty = actual_qty - reserved_qty

                for warehouse in webshop-01-settings.warehouses:
                    _bin = get_bin(item_code, warehouse.warehouse)
                    qty += (_bin.actual_qty - _bin.reserved_qty)

				# bugfix #1582: variant control from WooCommerce, not ERPNext
				#if item.webshop-01-variant_id and int(item.webshop-01-variant_id) > 0:
					#item_data, resource = get_product_update_dict_and_resource(item.webshop-01-product_id, item.webshop-01-variant_id, is_variant=True, actual_qty=qty)
				#else:
					#item_data, resource = get_product_update_dict_and_resource(item.webshop-01-product_id, item.webshop-01-variant_id, actual_qty=qty)
                if item.webshop-01-product_id and item.variant_of:
					# item = variant
                    template_item = frappe.get_doc("Item", item.variant_of).webshop-01-product_id
                    item_data, resource = get_product_update_dict_and_resource(template_item, webshop-01-variant_id=item.webshop-01-product_id, is_variant=True, actual_qty=qty)
                else:
					# item = single
                    item_data, resource = get_product_update_dict_and_resource(item.webshop-01-product_id, actual_qty=qty)
                try:
					#make_webshop-01-log(title="Update stock of {0}".format(item.barcode), status="Started", method="update_item_stock", message="Resource: {0}, data: {1}".format(resource, item_data))
                    put_request(resource, item_data)
                except requests.exceptions.HTTPError as e:
                    if e.args[0] and e.args[0].startswith("404"):
                        make_webshop-01-log(title=e.message, status="Error", method="update_item_stock", message=frappe.get_traceback(),
                            request_data=item_data, exception=True)
                        disable_webshop-01-sync_for_item(item)
                    else:
                        raise e


def get_product_update_dict_and_resource(webshop-01-product_id, webshop-01-variant_id=None, is_variant=False, actual_qty=0):
    item_data = {}
    item_data["stock_quantity"] = "{0}".format(cint(actual_qty))
    item_data["manage_stock"] = "1"

    if is_variant:
        resource = "products/{0}/variations/{1}".format(webshop-01-product_id,webshop-01-variant_id)
    else: #simple item
        resource = "products/{0}".format(webshop-01-product_id)

    return item_data, resource

def add_w_id_to_erp():
    # purge WooCommerce IDs so that there cannot be any conflict
    purge_ids = """UPDATE `tabItem`
            SET `webshop-01-product_id` = NULL, `webshop-01-variant_id` = NULL;"""
    frappe.db.sql(purge_ids)
    frappe.db.commit()

    # loop through all items on WooCommerce and get their IDs (matched by barcode)
    woo_items = get_webshop-01-items()
    make_webshop-01-log(title="Syncing IDs", status="Started", method="add_w_id_to_erp", message='Item: {0}'.format(woo_items),
        request_data={}, exception=True)
    for webshop-01-item in woo_items:
        update_item = """UPDATE `tabItem`
            SET `webshop-01-product_id` = '{0}'
            WHERE `barcode` = '{1}';""".format(webshop-01-item.get("id"), webshop-01-item.get("sku"))
        frappe.db.sql(update_item)
        frappe.db.commit()
        for webshop-01-variant in get_webshop-01-item_variants(webshop-01-item.get("id")):
            update_variant = """UPDATE `tabItem`
                SET `webshop-01-variant_id` = '{0}', `webshop-01-product_id` = '{1}'
                WHERE `barcode` = '{2}';""".format(webshop-01-variant.get("id"), webshop-01-item.get("id"), webshop-01-variant.get("sku"))
            frappe.db.sql(update_variant)
            frappe.db.commit()
    make_webshop-01-log(title="IDs synced", status="Success", method="add_w_id_to_erp", message={},
        request_data={}, exception=True)

def rewrite_stock_uom_from_wc_unit():
    webshop-01-settings = frappe.get_doc("WooCommerce Config", "WooCommerce Config")
    sql_query = """SELECT *
        FROM (SELECT 
          `tabItem`.`item_code`, 
          `tabItem`.`stock_uom` ,
          (SELECT `tabItem Variant Attribute`.`attribute_value` 
           FROM `tabItem Variant Attribute` 
           WHERE `tabItem Variant Attribute`.`parent` = `tabItem`.`name` 
             AND `tabItem Variant Attribute`.`attribute` = "{unit}") AS `unit` 
        FROM `tabItem`
        ) AS `raw`
        WHERE 
          `raw`.`unit` IS NOT NULL
          AND `raw`.`stock_uom` != `raw`.`unit`;""".format(unit=webshop-01-settings.attribute_for_uom)
    # get all items that have different WC unit from stock_uom      
    different_unit_items = frappe.db.sql(sql_query, as_dict=True)
    # if there are items, rewrite them
    if len(different_unit_items) > 0:
        # loop through items
        for i in different_unit_items:
            item = frappe.get_doc("Item", i.item_code)
            try:
                item.stock_uom = i.unit
                item.save()
            except Exception as err:
                make_webshop-01-log(title="WC rewrite stock uom", status="Error", method="rewrite_stock_uom_from_wc_unit", 
                        message="Unabe to rewrite stock of item {0} from {1} to {2}: {3}".format(i.item_code, i.stock_uom, i.unit, err),
                        request_data=None, exception=True)
        frappe.db.commit()
    return

# this function will force load all prices
def force_load_prices(debug=False):
    # prepare all items
    if debug:
        print("Loading items (no filter conditions)...")
    items = get_webshop-01-items(ignore_filter_conditions=True)
    for item in items:
        # load prices
        load_price(item, debug)
        # check variations and also load prices
        if len(item.get('variations')) > 0:
            variants = get_webshop-01-item_variants(item.get('id'))
            for v in variants:
                load_price(v, debug)
    return

def load_price(item, debug=False):
    # find item in ERP
    erp_item_code = frappe.get_value("Item", 
        {'webshop-01-product_id': item.get('id'), 'disabled': 0}, 'name')
    if erp_item_code:
        # create or update price
        add_to_price_list(item, erp_item_code)
        if debug:
            print("Updated {0} with {1}".format(erp_item_code, item.get('price')))
    return
