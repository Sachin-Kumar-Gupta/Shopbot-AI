import streamlit as st
import requests
import json
import os
import re
import uuid

# ========================================================
# CONFIG
# ========================================================
RASA_URL = "http://127.0.0.1:5005/webhooks/rest/webhook"
USER_DB_PATH = "users_data.json"

# ========================================================
# USER DATABASE FUNCTIONS
# ========================================================
def load_user_db():
    if os.path.exists(USER_DB_PATH):
        with open(USER_DB_PATH, "r") as f:
            return json.load(f)
    else:
        # default users
        return {
            "sachin": "1234",
            "admin": "admin123",
            "guest": "guest"
        }

def save_user_db(users_data):
    with open(USER_DB_PATH, "w") as f:
        json.dump(users_data, f, indent=4)

# Load DB into session
if "USER_DB" not in st.session_state:
    st.session_state.USER_DB = load_user_db()

# ========================================================
# SESSION STATE INITIALIZATION
# ========================================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_products" not in st.session_state:
    st.session_state.last_products = []
if "remove_mode" not in st.session_state:
    st.session_state.remove_mode = False
if "show_signup" not in st.session_state:
    st.session_state.show_signup = False
# Add missing session state variables
if "all_products" not in st.session_state:
    st.session_state.all_products = []
if "show_limit" not in st.session_state:
    st.session_state.show_limit = 5
if "selected_addr_id" not in st.session_state:
    st.session_state.selected_addr_id = None
if "checkout_result" not in st.session_state:
    st.session_state.checkout_result = None

st.set_page_config(page_title="🛒 E-commerce Chatbot", page_icon="🤖", layout="centered")


# ========================================================
# AUTH / SIGNUP PAGE
# ========================================================
if not st.session_state.authenticated:
    st.title("🔐 Welcome to ShopBot")
    users = load_user_db()
    mode = st.radio("Select mode:", ["Login", "Sign Up"], horizontal=True)

    # ---------- LOGIN ----------
    if mode == "Login":
        if not st.session_state.show_signup:
            st.subheader("Login to continue")
            username = st.text_input("Username:")
            password = st.text_input("Password:", type="password")
    
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Login"):
                    if username in st.session_state.USER_DB and st.session_state.USER_DB[username]["password"] == password:
                        st.session_state.authenticated = True
                        st.session_state.username = username
                        st.success(f"Welcome back, {username}! 👋")
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password.")
          

    # ---------- SIGNUP ----------
    else:
        st.subheader("🆕 Create Your Account")
        new_user = st.text_input("Choose a username:")
        new_pass = st.text_input("Choose a password:", type="password")
        confirm_pass = st.text_input("Confirm password:", type="password")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Sign Up"):
                if new_user in st.session_state.USER_DB:
                    st.warning("⚠️ Username already exists. Try another.")
                elif new_pass != confirm_pass:
                    st.error("❌ Passwords do not match.")
                elif len(new_user.strip()) == 0 or len(new_pass.strip()) == 0:
                    st.warning("Please enter valid credentials.")
                else:
                    users = load_user_db()
                    users[new_user] = {
                        "password": new_pass,
                        "cart": [],
                        "orders": []
                    }
                    save_user_db(users)
                    st.session_state.USER_DB = users
                    st.success("✅ Account created successfully! You can now log in.")
                    st.session_state.show_signup = False
                    st.rerun()
        #with col2:
         #   if st.button("🔙 Back to Login"):
          #      st.session_state.show_signup = False
          #      st.rerun()

    st.stop()  # Stop here if not authenticated

users_data = load_user_db()
user_data = users_data.get(st.session_state.username, {"cart": [], "orders": [], "last_search": None})
st.session_state.cart_items = user_data.get("cart", [])
st.session_state.orders = user_data.get("orders", [])

# 🧠 Personalized welcome message
last_search = user_data.get("last_search")
if last_search:
    st.info(f"👋 Welcome back, **{st.session_state.username}**! Last time you searched for **{last_search}**. Want to continue shopping?")
else:
    st.info(f"👋 Welcome, **{st.session_state.username}**! What would you like to shop for today?")

#--- Calculation of total price-----
def compute_totals(items, coupon, free_ship_threshold=999, tax_rate=0.18):
    subtotal = round(sum(float(it.get("price", 0.0)) * int(it.get("qty", 1)) for it in items), 2)
    def apply_coupon(subtotal, c):
        if not c: return 0.0
        t, v = c.get("type"), float(c.get("value", 0))
        if t == "percent": return round(subtotal * v / 100.0, 2)
        if t == "flat": return round(min(v, subtotal), 2)
        return 0.0
    discount = apply_coupon(subtotal, coupon)
    tax_base = max(0.0, subtotal - discount)
    shipping = 0.0 if tax_base >= free_ship_threshold else 49.0
    tax = round(tax_base * tax_rate, 2)
    total = round(tax_base + shipping + tax, 2)
    return subtotal, discount, shipping, tax, total

# ========================================================
# MAIN CHATBOT PAGE (only after login)
# ========================================================
st.title(f"🛒 E-commerce Chatbot — {st.session_state.username}")
st.markdown("Ask about products, prices, stock, or track your orders!")

# 🔹 Function to send message to Rasa backend
def send_message_to_rasa(user_message):
    try:
        response = requests.post(
            RASA_URL,
            json={"sender": st.session_state.username, "message": user_message},
            timeout=120
        )
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            return [{"text": "⚠️ Could not connect to the chatbot backend."}]
    except Exception as e:
        return [{"text": f"❌ Connection error: {e}"}]

# ---------------- PENDING BOT RESPONSES ----------------
pending = st.session_state.pop("pending_bot_responses", None)
if pending:
    #print("DEBUG -- pending bot responses:", pending)
    # Convert pending bot responses into unified chat messages
    for resp in pending:
        # 1) Confirmation or other text -> append to history
        if "text" in resp:
            text = resp["text"].strip()
            st.session_state.messages.append({"role": "assistant", "content": text})

        # 2) Recommendations -> append as structured assistant content
        recs = None
        if isinstance(resp.get("custom"), dict) and "recommendations" in resp["custom"]:
            recs = resp["custom"]["recommendations"]
        elif isinstance(resp.get("json_message"), dict) and "recommendations" in resp["json_message"]:
            recs = resp["json_message"]["recommendations"]
        elif "recommendations" in resp:
            recs = resp["recommendations"]

        if recs and not st.session_state.get("added_from_recs", False):
            st.session_state.messages.append({"role": "assistant", "content": {"recommendations": recs}})
            # Optional: mark that this run came from an add-to-cart interaction
            st.session_state["suppress_products_once"] = True
            st.session_state["last_event"] = "add_to_cart"

    # Rerun so the new messages render at the bottom in the chat history
    st.rerun()

# ------------- CHAT HISTORY RENDERER -------------
history_snapshot = list(st.session_state.messages)
for msg in history_snapshot:
    role = msg.get("role")
    content = msg.get("content")

    if role == "user":
        st.chat_message("user").write(content)
        continue

    # Assistant message as plain text
    if role == "assistant" and isinstance(content, str):
        st.chat_message("assistant").write(content)
        continue

    # Assistant message with recommendations payload
    if role == "assistant" and isinstance(content, dict) and "recommendations" in content:
        with st.chat_message("assistant"):
            #st.write("### 🛍️ You might also like:")
            msg_uid = str(id(msg)) #---new code
            seen = set() # new code
            for idx, rec in enumerate(content["recommendations"]):
                col1, col2 = st.columns([3, 1])
                product_name = rec.get('product_name', '')
                price = float(rec.get('price', 0.0) or 0.0)
                sig = (product_name.lower(), price) # new code
                
                if sig in seen: # new code
                    continue 
                seen.add(sig) # new code
                
                with col1:
                    st.markdown(f"**{rec.get('product_name','Unknown')}** — ₹{rec.get('price',0)}")
                with col2:
                    safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", product_name.lower()) or "item"
                    key = f"rec_add__{msg_uid}__{safe_name}__{idx}"
                    #st.caption(f"key={key}")
                    if st.button("Add", key=key):
                        # Capture bot response so next rerun draws any follow-up recs
                        #bot_res = send_message_to_rasa(f"add {rec.get('product_name','')} to cart")
                        #st.session_state["pending_bot_responses"] = bot_res
                    
                        # 2) NEW: Update local DB + session cart (mirror other Add handlers)
                        
                        users = load_user_db()
                        u = users.setdefault(st.session_state.username, {})
                        u.setdefault("cart", [])
                        u["cart"].append({"name": product_name, "price": price})
                        users[st.session_state.username] = u
                        save_user_db(users)
                        st.session_state.cart_items = users[st.session_state.username].get("cart", [])
                        
                        # 3) Trigger backend add (optional sync)
                        #st.session_state["pending_bot_responses"] = send_message_to_rasa(f"add {product_name} to cart")
                    
                        # 3) Keep existing UI flags and rerun
                        st.success(f"✅ Added {product_name} to your cart.")
                        st.session_state["suppress_products_once"] = True
                        st.session_state["last_event"] = "add_to_cart"
                        st.session_state.added_from_recs = True
                        # 4) Persist a visible confirmation into chat history (survives rerun)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"✅ {product_name} added to your cart."
                        })
                        # Optional (consistency): st.session_state["last_event"] = "add_to_cart"
                        st.toast(f"Adding {product_name} from recs...", icon="🛍️")
                        st.rerun()


if st.session_state.get("added_from_recs", False):
    st.chat_message("assistant").write("Would you like to proceed to checkout, or continue shopping? Type 'checkout' or ask for more products.")
    # Clear the flag so the prompt appears only once
    st.session_state.added_from_recs = False
    
# 🔹 Chat input
user_input = st.chat_input("Type your message:")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # 2) INTERCEPT CHECKOUT HERE (add this block)
    normalized = user_input.strip().lower()
    if normalized in {"checkout", "check out", "proceed to checkout", "place order"}:
        users = load_user_db()
        u = users.setdefault(st.session_state.username, {})
        cart = u.setdefault("cart", [])
        orders = u.setdefault("orders", [])
        coupon = u.get("coupon")
        u.setdefault("cart", [])
        u.setdefault("orders", [])
        
        # ADDRESS GUARD (same as sidebar)
        addrs = u.setdefault("addresses", [])
        sel_id = st.session_state.get("selected_addr_id")
    
        if not addrs or not sel_id:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Please select or add a delivery address in the sidebar, then say 'checkout' again."
            })
            st.rerun()
    
        address_snapshot = next((a for a in addrs if a["id"] == sel_id), None)
        if not address_snapshot:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Selected address not found. Please reselect or add a new one."
            })
            st.rerun()

        item_count = len(u["cart"])
        #total = round(sum(float(it.get("price", 0.0) or 0.0) for it in u["cart"]), 2)

        if item_count == 0:
            st.session_state.messages.append({"role": "assistant", "content": "Your cart is empty. Add items before checking out."})
            st.rerun()

        # Recompute totals to ensure consistency
        subtotal, discount, shipping, tax, total = compute_totals(cart, coupon)

        order_id = f"ORD{len(orders)+1:03d}"
        orders.append({
            "order_id": order_id,
            "items": cart,
            "subtotal": subtotal,
            "discount": discount,
            "shipping": shipping,
            "tax": tax,
            "total": total,
            "coupon": coupon,
            "status": "Processing"
        })
        u["cart"] = []
        u.pop("coupon", None)
        users[st.session_state.username] = u
        save_user_db(users)
        st.session_state.cart_items = []

        # Confirmation in chat
        short_addr = f"{address_snapshot.get('label','')}: {address_snapshot.get('line1','')}, {address_snapshot.get('city','')} {address_snapshot.get('postcode','')}"
        st.session_state.messages.append({
            "role": "assistant",
            "content": (
                f"✅ Checkout successful! 🧾 {order_id} • {item_count} items • "
                f"Subtotal ₹{subtotal} • Discount ₹{discount} • Shipping ₹{shipping} • "
                f"Tax ₹{tax} • Total ₹{total} • Delivering to {short_addr}"
            )
        })
        st.rerun()

    # Track last search keyword for personalization
    if any(word in user_input.lower() for word in ["show", "find", "search", "buy", "price", "for"]):
        user_record = users_data.get(st.session_state.username, {})
        user_record.setdefault("last_search", None)
        user_record["last_search"] = user_input
        users_data[st.session_state.username] = user_record
        save_user_db(users_data)

    try:
        bot_responses = send_message_to_rasa(user_input)
        st.session_state.last_products = []

        # Reset products for new search
        st.session_state.all_products = []
        st.session_state.show_limit = 5

        for resp in bot_responses:
            # Store raw response for debugging
            st.session_state["last_raw_rasa_response"] = resp
            #print("DEBUG -- Processing bot message:", resp.keys())
            
            # Handle JSON product results from Rasa action
            if isinstance(resp.get("custom"), dict) and "product_results" in resp["custom"]:
                st.session_state.all_products = resp["custom"]["product_results"]
                st.session_state["last_event"] = "search"
                # Extract product info for later reference
                for product in st.session_state.all_products:
                    product_name = product.get("product_name", "")
                    price = float(product.get("price", 0) or 0)
                    if product_name:
                        st.session_state.last_products.append({"name": product_name, "price": price})
            
            # Handle text responses
            if "text" in resp:
                text = resp["text"].strip()
                st.chat_message("assistant").write(text)
                st.session_state.messages.append({"role": "assistant", "content": text})
                # ✅ Detect and keep track if recommendation message was sent
                #if "You might also like these top-rated {category} products:" in text.lower():
                 #   st.session_state["last_recommendation_text"] = text

            # Handle recommendations
            recs = None
            if isinstance(resp.get("custom"), dict) and "recommendations" in resp["custom"]:
                recs = resp["custom"]["recommendations"]
                #st.write("🔍 Found recommendations in custom!")
            elif isinstance(resp.get("json_message"), dict) and "recommendations" in resp["json_message"]:
                recs = resp["json_message"]["recommendations"]
                #st.write("🔍 Found recommendations in json_message!")
            elif "recommendations" in resp:
                recs = resp["recommendations"]
                #st.write("🔍 Found recommendations at root!")
            
            if recs and not st.session_state.get("added_from_recs", False):
                st.session_state.messages.append({"role": "assistant", "content": {"recommendations": recs}})
                st.session_state["suppress_products_once"] = True
                st.session_state["last_event"] = "add_to_cart"
                #st.write("### 🛍️ You might also like:")
                #st.write("🧠 DEBUG: Recommendations received:", recs)
                #for rec in recs:
                 #   col1, col2 = st.columns([3, 1])
                  #  with col1:
                   #     st.markdown(f"**{rec['product_name']}** — ₹{rec['price']}")
                    #with col2:
                     #   unique_suffix = str(uuid.uuid4())[:8]
                      #  key = f"rec_add_{rec['product_name'].replace(' ', '_')}_{unique_suffix}"
                       # st.write("➡️ Rendering Add button for:", rec.get("product_name"))
                        #if st.button("Add", key=key):
                         #   product_name = rec.get('product_name', '')
                          #  price = rec.get('price', 0.0)
            
                            # 🔹 1. Send to Rasa backend (maintain backend consistency)
                           # bot_res = send_message_to_rasa(f"add {product_name} to cart")
                            #print("===== RAW RASA RESPONSE =====")
                            #print(bot_res)
                            #st.session_state["pending_bot_responses"] = bot_res
            
                            # 🔹 2. Update local DB for instant UI response
                            #users = load_user_db()
                            #u = users.setdefault(st.session_state.username, {})
                            #u.setdefault("cart", [])
                            #u["cart"].append({"name": product_name, "price": price})
                            #users[st.session_state.username] = u
                            #save_user_db(users)
                            #st.session_state.cart_items = u["cart"]
                            
                            # 2️⃣ Trigger backend update (Rasa add_to_cart action)
                            #st.session_state["pending_bot_responses"] = send_message_to_rasa(f"add {product_name} to cart")
            
                            # 🔹 3. Visual feedback + prevent product grid flicker
                            #st.success(f"✅ Added {product_name} to your cart.")
                            #st.session_state["suppress_products_once"] = True
                            #st.session_state["refresh_cart"] = True
                            #st.session_state["last_event"] = "add_to_cart"
                            #st.session_state.cart_items = users[st.session_state.username]["cart"]
                            #st.experimental_rerun()
                            #st.rerun()
            # ✅ If we got recs but Rasa text didn't appear (split messages)
            elif "last_recommendation_text" in st.session_state:
                st.chat_message("assistant").write(st.session_state["last_recommendation_text"])
                st.session_state.pop("last_recommendation_text", None)

        # Remove duplicates
        unique = []
        seen = set()
        for p in st.session_state.last_products:
            name = p.get("name")
            if name and name not in seen:
                seen.add(name)
                unique.append(p)
        st.session_state.last_products = unique

    except requests.exceptions.RequestException as e:
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"❌ Could not connect to Rasa backend.\nError: {e}"
        })

    st.rerun()

# ========================================================
# PRODUCT RENDERING SECTION (ALWAYS RUNS)
# ========================================================
def render_products(products, limit):
    """Render products with Add to Cart buttons"""
    shown = 0
    for product in products[:limit]:
        product_name = product.get("product_name", "")
        price = float(product.get("price", 0) or 0)
        rating = product.get("rating", "—")
        category = product.get("category", "—")
        stock_status = product.get("stock_status", "—")
        delivery_time = product.get("delivery_time", "—")

        # Display product card
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(
                    f"""
                    <div style="border:1px solid #ddd; border-radius:10px; padding:10px; margin:5px 0;">
                        <b>{product_name}</b><br>
                        💰 Price: ₹{price}<br>
                        ⭐ Rating: {rating} | 📂 Category: {category}<br>
                        📦 Stock: {stock_status} | 🚚 Delivery: {delivery_time}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col2:
                add_key = f"add_{product_name.replace(' ', '_').lower()}_{shown}"
                if st.button("🛒 Add", key=add_key):
                    # 1) Send to Rasa and CAPTURE the response for recommendation rendering
                    bot_responses = send_message_to_rasa(f"add {product_name} to cart")
                    st.session_state["pending_bot_responses"] = bot_responses  # <-- critical
                    st.session_state["suppress_products_once"] = True
                    
                    # Update user cart locally
                    users = load_user_db()
                    u = users.setdefault(st.session_state.username, {})
                    u.setdefault("cart", [])
                    u["cart"].append({"name": product_name, "price": price})
                    users[st.session_state.username] = u
                    save_user_db(users)
                    
                    st.session_state.cart_items = users[st.session_state.username].get("cart", [])
                    
                    st.success(f"✅ Added {product_name} to your cart.")
                    st.session_state["refresh_cart"] = True
                    st.rerun()
        shown += 1
    return shown

# --------- PRODUCTS SECTION (guarded) ---------
should_show_products = bool(st.session_state.all_products)

# Skip one rerun after add-to-cart to prevent old grid from popping
if st.session_state.get("suppress_products_once"):
    should_show_products = False
    st.session_state["suppress_products_once"] = False  # consume the flag

# Only show the grid if the last event was a search
if st.session_state.get("last_event") != "search":
    should_show_products = False

if should_show_products:
    st.markdown("### 🛍️ Products Found:")
    total_shown = render_products(st.session_state.all_products, st.session_state.show_limit)
    if len(st.session_state.all_products) > st.session_state.show_limit:
        if st.button("🔽 Show More Products"):
            st.session_state.show_limit += 5
            st.rerun()
            
if st.session_state.get("last_event") == "add_to_cart":
    st.session_state["last_event"] = None
# ========================================================
# SIDEBAR (Cart Management + Logout)
# ========================================================

with st.sidebar:
    st.header(f"🛒 {st.session_state.username}'s Cart")

    users = load_user_db()
    user_rec = users.get(st.session_state.username, {})
    parsed_items = user_rec.get("cart", [])
    st.session_state.cart_items = parsed_items[:] # keep session in sync with persisted store.
    total_items = len(parsed_items)
    total_price = round(sum(float(it.get("price", 0.0) or 0.0) for it in parsed_items), 2)

    st.subheader(f"{total_items} items - ₹{total_price}")

    if not parsed_items:
        st.info("Your cart is empty.")
    else:
        for idx, item in enumerate(parsed_items):
            cols = st.columns([4, 1])
            with cols[0]:
                st.markdown(f"**{item['name']}** — ₹{item['price']}")
            with cols[1]:
                if st.button("🗑️", key=f"remove_{idx}_{item['name']}"):
                    # remove locally and persist
                    users = load_user_db()
                    u = users.setdefault(st.session_state.username, {})
                    u.setdefault("cart", [])
                    # remove first matching entry
                    for j, it in enumerate(u["cart"]):
                        if it["name"].lower() == item["name"].lower():
                            u["cart"].pop(j)
                            break
                    users[st.session_state.username] = u
                    save_user_db(users)
                    st.session_state.cart_items = users[st.session_state.username].get("cart", [])
                    st.success(f"Removed {item['name']}")
                    st.rerun()
    st.divider()                
    #---Coupon Code------
    # Coupon read
    coupon = user_rec.get("coupon") or {}
    
    def apply_coupon(subtotal, c):
        if not c: return 0.0
        t, v = c.get("type"), float(c.get("value", 0))
        if t == "percent": return round(subtotal * v / 100.0, 2)
        if t == "flat": return round(min(v, subtotal), 2)
        return 0.0
    
    # Totals
    subtotal = round(sum(float(it.get("price", 0.0)) * int(it.get("qty", 1)) for it in parsed_items), 2)
    discount = apply_coupon(subtotal, coupon)
    tax_base = max(0.0, subtotal - discount)
    shipping = 0.0 if tax_base >= 999 else 49.0
    tax_rate = 0.18
    tax = round(tax_base * tax_rate, 2)
    grand = round(tax_base + shipping + tax, 2)
    
    st.markdown(f"Subtotal: ₹{subtotal}")
    if discount > 0:
        st.markdown(f"Discount: -₹{discount} ({coupon.get('code','')})")
    st.markdown(f"Shipping: ₹{shipping}")
    st.markdown(f"Tax (18%): ₹{tax}")
    st.subheader(f"Total: ₹{grand}")
    
    # Coupon UI
    with st.expander("Have a coupon?"):
        code = st.text_input("Enter code")
        if st.button("Apply"):
            valid = {"SAVE10": {"type": "percent", "value": 10},
                     "LESS50": {"type": "flat", "value": 50},
                     "FREE": {"type": "flat", "value": 100}}
            if code in valid:
                users = load_user_db()
                u = users.setdefault(st.session_state.username, {})
                u["coupon"] = {"code": code, **valid[code]}
                users[st.session_state.username] = u
                save_user_db(users)
                st.success("Coupon applied!")
                st.rerun()
            else:
                st.warning("Invalid coupon.")
        if coupon and st.button("Remove coupon"):
            users = load_user_db()
            u = users.setdefault(st.session_state.username, {})
            u.pop("coupon", None)
            users[st.session_state.username] = u
            save_user_db(users)
            st.info("Coupon removed.")
            st.rerun()  
            
    # ===== Address Book (button-based selection + delete) =====
    addresses = user_rec.get("addresses", [])
    selected_addr_id = st.session_state.get("selected_addr_id")
    
    # Auto-pick default if nothing selected
    if addresses and not selected_addr_id:
        default = next((a["id"] for a in addresses if a.get("is_default")), addresses[0]["id"])
        st.session_state.selected_addr_id = default
        selected_addr_id = default
    
    st.markdown("### Delivery address")
    
    if not addresses:
        st.info("No delivery address on file. Add one below to proceed.")
    else:
        for a in addresses:
            aid = a["id"]
            is_sel = (aid == st.session_state.get("selected_addr_id"))
            is_def = bool(a.get("is_default"))
        
            # Address summary (keep yours)
            st.markdown(f"**{a.get('label','')}** {'(Default)' if is_def else ''}")
            st.caption(f"{a.get('name','')} · {a.get('line1','')}, {a.get('city','')} {a.get('postcode','')}")
        
            # Buttons stacked vertically (one below another)
            # 1) Select
            if st.button("Select" if not is_sel else "Selected ✅", key=f"addr_sel_{aid}", disabled=is_sel):
                st.session_state.selected_addr_id = aid
                st.rerun()
        
            # small spacer
            st.write("")
        
            # 2) Set Default
            if not is_def and st.button("Set Default", key=f"addr_def_{aid}"):
                users = load_user_db()
                u = users.setdefault(st.session_state.username, {})
                addrs = u.setdefault("addresses", [])
                for ax in addrs:
                    ax["is_default"] = (ax["id"] == aid)
                users[st.session_state.username] = u
                save_user_db(users)
                st.session_state.selected_addr_id = aid
                st.rerun()
        
            st.write("")
        
            # 3) Delete
            can_delete = len(addresses) > 1
            if st.button("Delete", key=f"addr_del_{aid}", disabled=not can_delete):
                users = load_user_db()
                u = users.setdefault(st.session_state.username, {})
                addrs = u.setdefault("addresses", [])
                addrs = [ax for ax in addrs if ax["id"] != aid]
                u["addresses"] = addrs
                users[st.session_state.username] = u
                save_user_db(users)
                # reselection
                if st.session_state.get("selected_addr_id") == aid:
                    st.session_state.selected_addr_id = addrs[0]["id"] if addrs else None
                st.rerun()

    
    # Add / Edit Address form
    with st.expander("Add / Edit Address"):
        with st.form("addr_form_buttons", clear_on_submit=False):
            label = st.text_input("Label (Home/Office)", "Home")
            name = st.text_input("Full name")
            line1 = st.text_input("Address line 1")
            line2 = st.text_input("Address line 2", "")
            city = st.text_input("City")
            state = st.text_input("State/Province")
            postcode = st.text_input("Postcode")
            country = st.text_input("Country", "India")
            phone = st.text_input("Phone")
            make_default = st.checkbox("Set as default", value=True)
            submitted = st.form_submit_button("Save address")
            if submitted:
                users = load_user_db()
                u = users.setdefault(st.session_state.username, {})
                addrs = u.setdefault("addresses", [])
                new_id = f"ADDR{len(addrs)+1:03d}"
    
                if make_default:
                    for ax in addrs: ax["is_default"] = False
    
                addrs.append({
                    "id": new_id, "label": label, "name": name,
                    "line1": line1, "line2": line2, "city": city, "state": state,
                    "postcode": postcode, "country": country, "phone": phone,
                    "is_default": make_default
                })
                u["addresses"] = addrs
                users[st.session_state.username] = u
                save_user_db(users)
    
                # Select the new/updated address
                st.session_state.selected_addr_id = new_id
                st.success("Address saved.")
                st.rerun()
    #----Checkout page----------
    st.divider()

    if total_items > 0:
        if st.button("💳 Checkout"):
            users = load_user_db()
            u = users.setdefault(st.session_state.username, {})
            cart = u.setdefault("cart", [])
            orders = u.setdefault("orders", [])
            coupon = u.get("coupon")
    
            # 1) ADDRESS GUARD — ensure a selected address exists
            addrs = u.setdefault("addresses", [])
            sel_id = st.session_state.get("selected_addr_id")
    
            if not addrs or not sel_id:
                st.warning("Please select or add a delivery address before checkout.")
                st.session_state.messages.append({
                    "role":"assistant",
                    "content":"Please select or add a delivery address in the sidebar, then press Checkout."
                })
                st.rerun()
    
            address_snapshot = next((a for a in addrs if a["id"] == sel_id), None)
            if not address_snapshot:
                st.warning("Selected address not found. Please reselect or add a new one.")
                st.session_state.messages.append({
                    "role":"assistant",
                    "content":"Selected address not found. Please reselect or add a new one in the sidebar."
                })
                st.rerun()
    
            # 2) EMPTY CART GUARD
            if not cart:
                st.info("Your cart is empty.")
                st.session_state.messages.append({
                    "role":"assistant",
                    "content":"Your cart is empty. Add items before checking out."
                })
                st.rerun()
    
            # 3) TOTALS (same logic as sidebar display)
            subtotal = round(sum(float(it["price"]) * int(it.get("qty",1)) for it in cart), 2)
    
            def apply_coupon(subtotal, c):
                if not c: return 0.0
                t, v = c.get("type"), float(c.get("value", 0))
                if t == "percent": return round(subtotal * v / 100.0, 2)
                if t == "flat": return round(min(v, subtotal), 2)
                return 0.0
    
            discount = apply_coupon(subtotal, coupon)
            tax_base = max(0.0, subtotal - discount)
            shipping = 0.0 if tax_base >= 999 else 49.0
            tax = round(tax_base * 0.18, 2)
            total = round(tax_base + shipping + tax, 2)
    
            order_id = f"ORD{len(orders)+1:03d}"
            item_count = sum(int(i.get("qty",1)) for i in cart)
    
            # 4) SAVE ORDER with address snapshot
            orders.append({
                "order_id": order_id,
                "items": cart,
                "subtotal": subtotal,
                "discount": discount,
                "shipping": shipping,
                "tax": tax,
                "total": total,
                "coupon": coupon,
                "status": "Processing",
                "ship_to": address_snapshot
            })
    
            # 5) CLEAR CART & COUPON
            u["cart"] = []
            u.pop("coupon", None)
            users[st.session_state.username] = u
            save_user_db(users)
    
            # 6) CHAT CONFIRMATION + RERUN
            short_addr = f"{address_snapshot.get('label','')}: {address_snapshot.get('line1','')}, {address_snapshot.get('city','')} {address_snapshot.get('postcode','')}"
            msg = (
                f"✅ Checkout successful! 🧾 {order_id} • {item_count} items • "
                f"Subtotal ₹{subtotal} • Discount ₹{discount} • Shipping ₹{shipping} • "
                f"Tax ₹{tax} • Total ₹{total} • Delivering to {short_addr}"
            )
            st.session_state.messages.append({"role": "assistant", "content": msg})
    
            st.session_state.cart_items = []
            st.rerun()

            #st.rerun()
            
     # Order History section       
    st.divider()
    st.subheader("📦 Order History")

    if st.button("🧾 View My Orders"):
        users = load_user_db()
        orders = users.get(st.session_state.username, {}).get("orders", [])
        if not orders:
            st.info("You haven't placed any orders yet.")
        else:
            for order in reversed(orders):
                with st.expander(f"🆔 {order['order_id']} — ₹{order['total']}"):
                    for it in order["items"]:
                        st.markdown(f"- **{it['name']}** — ₹{it['price']}")

    st.divider()
    if st.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.messages = []
        st.session_state.last_products = []
        st.session_state.all_products = []
        st.session_state.show_limit = 5
        st.success("Logged out successfully.")
        st.rerun()

# ========================================================
# 🔍 DEBUG PANEL (Temporary)
# ========================================================
#with st.expander("🪲 Debug: Last Raw Rasa Response"):
#    if "last_raw_rasa_response" in st.session_state:
#        st.json(st.session_state["last_raw_rasa_response"])
#    else:
#        st.info("No response to check yet.")



# ========================================================
# QUICK ACTION BUTTONS (below chat)
# ========================================================
if st.session_state.last_products:
    st.write("👉 **Quick actions:**")
    cols = st.columns(min(len(st.session_state.last_products), 4))  # Limit to 4 columns max
    for i, item in enumerate(st.session_state.last_products[:4]):  # Show only first 4
        product = item["name"]
        price = item.get("price", 0.0)
        with cols[i]:
            key = f"add_quick_{i}_{product}"
            if st.button(f"Add {product} 🛒", key=key):
                st.toast(f"🛒 Adding {product}...", icon="🛍️")

                # 1) Call Rasa to keep backend slot in sync
                bot_responses = send_message_to_rasa(f"add {product} to cart")
                st.session_state["pending_bot_responses"] = bot_responses

                # 2) Update persistent users_data immediately (source-of-truth for UI)
                users = load_user_db()
                u = users.setdefault(st.session_state.username, {})
                u.setdefault("cart", [])
                u["cart"].append({"name": product, "price": price})
                users[st.session_state.username] = u
                save_user_db(users)

                # 3) update local session for instant sidebar display
                st.session_state.cart_items = u["cart"]

                st.success(f"✅ {product} added to cart!")
                st.session_state["refresh_cart"] = True
                st.rerun()
