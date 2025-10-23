# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

import random
import datetime
from typing import Any, Text, Dict, List
import pandas as pd
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from fuzzywuzzy import process
import re
import json
import os
from datetime import datetime, timedelta

# Load products dataset once (for performance)
PRODUCTS_DF = pd.read_csv("products.csv")

ORDERS_DF = pd.read_csv("orders.csv")

USERS_FILE = "users_data.json"

#print(f"✅ Loaded {len(PRODUCTS_DF)} products from CSV.")
#print(f"Sample categories: {PRODUCTS_DF['category'].unique()[:5]}")

# ✅ Load synonyms from external file
with open("synonyms.json", "r", encoding="utf-8") as f:
    SYNONYMS = json.load(f)

class ActionUserLogin(Action):
    def name(self) -> Text:
        return "action_user_login"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        import json

        user_message = tracker.latest_message.get("text", "").strip()
        parts = user_message.split()

        if len(parts) < 3:
            dispatcher.utter_message(text="Please enter login as: `login <username> <password>`")
            return []

        _, username, password = parts[:3]

        # Load existing users
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users_data = json.load(f)
        else:
            users_data = {"users": {}}

        # If user exists, check password
        if username in users_data["users"]:
            if users_data["users"][username]["password"] == password:
                dispatcher.utter_message(text=f"👋 Welcome back, {username}! Your previous data has been loaded.")
                cart = users_data["users"][username].get("cart", [])
                return [SlotSet("cart", cart)]
            else:
                dispatcher.utter_message(text="❌ Incorrect password. Try again.")
                return []
        else:
            # Register new user
            users_data["users"][username] = {"password": password, "cart": []}
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users_data, f, indent=4)
            dispatcher.utter_message(text=f"✅ New user created! Welcome, {username}.")
            return [SlotSet("cart", [])]

class ActionSearchProduct(Action):
    def name(self) -> str:
        return "action_search_products"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: dict):

        user_message = tracker.latest_message.get('text', '').lower().strip()
        
        is_price_only = any(kw in user_message for kw in ["under", "below", "over", "above", "between"]) and \
                not any(kw in user_message for kw in ["show", "find", "search", "buy", "phone", "book", "coat", "laptop"])

        # 🚨 DEBUG: Check if this action is handling add to cart
        print(f"\n🔍 ActionSearchProduct received: '{user_message}'")
        if "add" in user_message and "cart" in user_message:
            print(" 🚨 WARNING: ActionSearchProduct is handling add to cart! ")
            print(" 🚨 This should go to ActionAddToCart instead! ")
            
        # Extract last remembered category
        last_category = tracker.get_slot("last_category")
        
        # 🔹 Synonym replacement
        for category, synonyms in SYNONYMS.items():
            for synonym in synonyms:
                if synonym in user_message:
                    user_message = user_message.replace(synonym, category)
        if is_price_only and last_category:
            selected_category = last_category
            matched_products = PRODUCTS_DF[
                PRODUCTS_DF['category'].str.lower().str.strip() == last_category
            ]
        else:
            # Extract price filter if present
            price_min, price_max = None, None
            price_pattern = re.findall(r'(\d+)', user_message)
            if "under" in user_message and price_pattern:
                price_max = float(price_pattern[0])
            elif "below" in user_message and price_pattern:
                price_max = float(price_pattern[0])
            elif "above" in user_message and price_pattern:
                price_min = float(price_pattern[0])
            elif "over" in user_message and price_pattern:
                price_min = float(price_pattern[0])

        # Match category using fuzzy logic
        categories = PRODUCTS_DF['category'].str.lower().str.strip().unique().tolist()
        products_name = PRODUCTS_DF['product_name'].str.lower().str.strip().unique().tolist()
        matched_category, score = process.extractOne(user_message, categories)
        matched_prod, prod_score = process.extractOne(user_message, products_name)
        
        if score >= 70:
            selected_category = matched_category
            matched_products = PRODUCTS_DF[
                PRODUCTS_DF['category'].str.lower().str.strip() == matched_category]
            
        elif prod_score >= 60 :
            lowered = PRODUCTS_DF['product_name'].astype(str).str.lower().str.strip()

            q = user_message.lower()
            q_tokens = set(re.findall(r"[a-z0-9]+", q))
        
            contains_mask = lowered.apply(lambda n: any(tok in n for tok in q_tokens if len(tok) >= 4))
            if "coat" in q:
                contains_mask = contains_mask | lowered.str.contains("coat", na=False)
        
            fuzzy_hits = process.extract(user_message, lowered.tolist(), limit=120)
            fuzzy_set = {n for (n, s) in fuzzy_hits if s >= max(55, prod_score - 15)}
        
            mask = contains_mask | lowered.isin(fuzzy_set)
            matched_products = PRODUCTS_DF[mask]
            selected_category = last_category
            
        else:
            selected_category = last_category  # fallback to memory
            matched_products = PRODUCTS_DF[
                PRODUCTS_DF['product_name'].str.lower().str.contains(user_message)
            ]

        # Apply price filtering
        if price_max is not None:
            matched_products = matched_products[matched_products['price'] <= price_max]
        if price_min is not None:
            matched_products = matched_products[matched_products['price'] >= price_min]
            
        # ✅ Synonym fallback (only if nothing matched yet)
        if matched_products.empty:
            for category, synonyms in SYNONYMS.items():
                if any(s in user_message for s in synonyms):
                    matched_products = PRODUCTS_DF[
                        PRODUCTS_DF['category'].str.lower().str.strip() == category
                    ]
                    break

        if matched_products.empty:
            dispatcher.utter_message(text="Sorry, no products match your search or price filter.")
            return []
        
        # 🔀 Shuffle for randomness
        # --- DEDUP by normalized name to avoid repeated same product label with variants
        tmp = matched_products.copy()
        tmp["__name_norm__"] = tmp["product_name"].astype(str).str.lower().str.strip()
        if "rating" in tmp.columns and "price" in tmp.columns:
            tmp = tmp.sort_values(by=["rating", "price"], ascending=[False, True])
        dedup = tmp.drop_duplicates(subset="__name_norm__", keep="first")
        matched_products = dedup.sample(frac=1,random_state=None)
        #matched_products = matched_products.sample(frac=1, random_state=None)

        # 🧾 Send all results (not truncated)
        dispatcher.utter_message(text=f"Here are some products I found ({len(matched_products)} total):")

        product_list = []
        for _, row in matched_products.iterrows():
            product_list.append({
                "product_name": row["product_name"],
                "price": row["price"],
                "category": row["category"],
                "rating": row["rating"],
                "stock_status": row["stock_status"],
                "delivery_time": row["delivery_time"]
            })

        # ✅ Send as JSON so Streamlit can paginate
        dispatcher.utter_message(json_message={"product_results": product_list})

        return [SlotSet("last_category", selected_category)]
'''
class ActionClearCategory(Action):
    def name(self) -> str:
        return "action_clear_category"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: dict):

        dispatcher.utter_message(response="utter_clear_category")
        return [SlotSet("last_category", None)]
'''

class ActionCheckStock(Action):
    def name(self) -> str:
        return "action_check_stock"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: dict):
        
        user_message = tracker.latest_message.get('text', '').lower()

        matched_products = PRODUCTS_DF[PRODUCTS_DF['product_name'].str.lower().str.contains(user_message)]

        if matched_products.empty:
            dispatcher.utter_message(text="I couldn't find that product in our stock.")
            return []

        for _, row in matched_products.iterrows():
            stock_info = f"{row['product_name']} is currently {row['stock_status']}."
            dispatcher.utter_message(text=stock_info)
        
        return []

def _parse_iso_dt(val):
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None

def _parse_int(s, default=None):
    try:
        return int(s)
    except Exception:
        return default

def _business_days_from(start_dt: datetime, n_days: int) -> datetime:
    if n_days is None or n_days <= 0:
        return start_dt
    days_added = 0
    cur = start_dt
    while days_added < n_days:
        cur += timedelta(days=1)
        if cur.weekday() < 5:  # Mon–Fri
            days_added += 1
    return cur

def _extract_delivery_sla(text: str):
    """
    Parse delivery_time strings into (min_days, max_days, is_business).
    Supports:
      - "3-5 days", "2 days"
      - "7–10 business days" (en dash)
      - "5 business days"
      - "next day", "tomorrow", "same day"
    """
    if not text:
        return (None, None, False)
    t = str(text).strip().lower()
    if "same day" in t:
        return (0, 0, False)
    if "next day" in t or "tomorrow" in t:
        return (1, 1, False)
    is_business = "business" in t or "working" in t
    t_norm = t.replace("–", "-").replace("—", "-")
    m = re.search(r"(\d+)\s*-\s*(\d+)\s*day", t_norm)
    if m:
        d1, d2 = _parse_int(m.group(1)), _parse_int(m.group(2))
        if d1 is not None and d2 is not None:
            return (min(d1, d2), max(d1, d2), is_business)
    m = re.search(r"(\d+)\s*day", t_norm)
    if m:
        d = _parse_int(m.group(1))
        if d is not None:
            return (d, d, is_business)
    return (None, None, is_business)

def _compute_expected_from_sla(delivery_time: str, status: str, placed_at: datetime | None, shipped_at: datetime | None, policy: str = "max") -> datetime:
    """
    Convert SLA string to ETA using:
    - policy: 'max' (safe), 'avg', or 'min' when a range exists.
    - anchor: shipped_at for Shipped/In transit, today for Out for delivery, else placed_at.
    """
    now = datetime.now()
    dmin, dmax, is_business = _extract_delivery_sla(delivery_time)
    if dmin is None and dmax is None:
        days = 5
    else:
        dmax = dmax if dmax is not None else dmin
        if policy == "avg":
            days = int(round((dmin + dmax) / 2))
        elif policy == "min":
            days = dmin
        else:
            days = dmax

    s = (status or "").strip().lower()
    if s in {"shipped", "in transit"} and shipped_at:
        anchor = shipped_at
    elif s in {"out for delivery", "out-for-delivery"}:
        return now
    elif s in {"delivered"}:
        return shipped_at or placed_at or now
    else:
        anchor = placed_at or now

    if is_business:
        return _business_days_from(anchor, days)
    return anchor + timedelta(days=days)


class ActionTrackOrder(Action):
    def name(self) -> str:
        return "action_track_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: dict):
        
        # Extract order id from user message
        user_message = tracker.latest_message.get('text', '') or ''
        order_id = None

        # Try robust pattern first, then your simple scan
        m = re.search(r"\bORD\d{3,}\b", user_message.upper())
        if m:
            order_id = m.group(0)
        else:
            for oid in ORDERS_DF['order_id']:
                if oid.lower() in user_message.lower():
                    order_id = oid
                    break

        if not order_id:
            dispatcher.utter_message(text="Please provide a valid order ID (e.g., ORD001).")
            return []

        matched_order = ORDERS_DF[ORDERS_DF['order_id'].str.upper() == order_id.upper()]
        if matched_order.empty:
            dispatcher.utter_message(text=f"Sorry, I couldn't find any order with ID {order_id}.")
            return []

        row = matched_order.iloc[0]

        # Pull fields (keep your existing columns; add fallbacks)
        status = str(row.get('status', 'Processing'))
        product_name = str(row.get('product_name', 'your item'))
        # delivery_time can be on the order or item; here we read from order row
        delivery_time = str(row.get('delivery_time', row.get('expected_delivery', '')))
        placed_at = _parse_iso_dt(row.get('placed_at'))
        shipped_at = _parse_iso_dt(row.get('shipped_at'))

        # Fresh ETA from SLA string (policy='max' is safest)
        eta_dt = _compute_expected_from_sla(
            delivery_time=delivery_time,
            status=status,
            placed_at=placed_at,
            shipped_at=shipped_at,
            policy="max"
        )
        eta_str = eta_dt.strftime("%d %b %Y")

        dispatcher.utter_message(
            text=f"📦 Order {order_id} for {product_name} is currently {status}. Expected delivery: {eta_str}."
        )
        return []

class ActionAddToCart(Action):
    def name(self) -> Text:
        return "action_add_to_cart"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_message = tracker.latest_message.get("text", "").lower().strip()
        
        # 🚨 DEBUG: Confirm this action is triggered
        print(f"\n🛒 ActionAddToCart received: '{user_message}'")

        # 🧠 Clean the text by removing filler words
        cleaned_message = re.sub(r"\b(add|to cart|cart|put|in|into|please)\b", "", user_message)
        cleaned_message = re.sub(r"[^a-zA-Z0-9\s]", "", cleaned_message).strip()  # remove *, (), etc.

        # Avoid empty string
        if not cleaned_message:
            dispatcher.utter_message(text="❌ Please specify a valid product name.")
            return []

        # Try fuzzy matching on product name
        product_names = PRODUCTS_DF['product_name'].str.lower().tolist()
        best_match_tuple = process.extractOne(cleaned_message, product_names)

        if not best_match_tuple:
            dispatcher.utter_message(text="❌ Sorry, I couldn't find that product.")
            return []

        best_match, score = best_match_tuple

        if score < 70:
            dispatcher.utter_message(text="❌ Sorry, I couldn't find that product.")
            return []

        matched_row = PRODUCTS_DF[PRODUCTS_DF['product_name'].str.lower() == best_match].iloc[0]
        product_name = matched_row['product_name']
        price = matched_row['price']

        # 🛒 Update cart
        cart = tracker.get_slot("cart") or []
        cart.append({"product": product_name, "price": price})

        dispatcher.utter_message(text=f"✅ {product_name} added to your cart.")
        
        # 🔹 Recommend top-rated products from the same category
        category = matched_row['category']
        
        category_products = PRODUCTS_DF[
            (PRODUCTS_DF['category'] == category) &
            (PRODUCTS_DF['product_name'] != product_name)
        ]
        
        if not category_products.empty:
            # ✅ Sort by rating (descending) and pick top 3
            if "rating" in category_products.columns:
                recommendations = category_products.sort_values(by="rating", ascending=False).head(3)
            else:
                # fallback if rating column is missing
                recommendations = category_products.head(3)
        
            rec_list = []
            for _, row in recommendations.iterrows():
                rec_list.append({
                    "product_name": row["product_name"],
                    "price": row["price"],
                    "category": row["category"],
                    "rating": row.get("rating", "N/A")
                })
        
            # CHANGED: Use custom instead of json_message for consistency
            dispatcher.utter_message(text="### 🛍️ You might also like these top-rated products:",
                                     custom={"recommendations": rec_list})
        
        print("\n===== DEBUG: Matched product =====")
        print(f"Product: {product_name}, Category: {category}")
        print("===== DEBUG: Recommendations =====")
        print(recommendations[['product_name', 'price']].head(3))
        print("===== DEBUG: Sending recommendations =====")
        print(rec_list)
        return [SlotSet("cart", cart)]



class ActionShowCart(Action):
    def name(self) -> Text:
        return "action_show_cart"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        cart = tracker.get_slot("cart") or []
        if not cart:
            dispatcher.utter_message(text="🛒 Your cart is empty.")
            return []

        total = sum(item["price"] for item in cart)
        message = "🛒 Your cart contains:\n"
        for item in cart:
            message += f"• {item['product']} - ₹{item['price']}\n"
        message += f"\n💰 Total: ₹{total}"

        dispatcher.utter_message(text=message)
        return []


class ActionRemoveFromCart(Action):
    def name(self) -> Text:
        return "action_remove_from_cart"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        user_message = tracker.latest_message.get("text", "").lower()
        cart = tracker.get_slot("cart") or []

        updated_cart = [item for item in cart if item["product"].lower() not in user_message]

        if len(updated_cart) == len(cart):
            dispatcher.utter_message(text="❌ That product was not in your cart.")
        else:
            dispatcher.utter_message(text="🗑️ Item removed from your cart.")

        return [SlotSet("cart", updated_cart)]


class ActionCheckout(Action):
    def name(self) -> Text:
        return "action_checkout"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        cart = tracker.get_slot("cart") or []
        if not cart:
            dispatcher.utter_message(text="🛒 Your cart is empty, nothing to checkout.")
            return []

        total = sum(item["price"] for item in cart)
        order_id = "ORD" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(100, 999))

        dispatcher.utter_message(
            text=f"✅ Checkout successful!\n🧾 Order ID: {order_id}\n💰 Total Paid: ₹{total}\n📦 Your order will be delivered soon."
        )

        # Empty the cart after checkout
        return [SlotSet("cart", [])]

# This is a simple example for a custom action which utters "Hello World!"

# from typing import Any, Text, Dict, List
#
# from rasa_sdk import Action, Tracker
# from rasa_sdk.executor import CollectingDispatcher
#
#
# class ActionHelloWorld(Action):
#
#     def name(self) -> Text:
#         return "action_hello_world"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#
#         dispatcher.utter_message(text="Hello World!")
#
#         return []
