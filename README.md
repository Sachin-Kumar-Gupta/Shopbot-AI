# 🛒 Shopbot-AI Assistant
An intelligent shopping copilot built with Streamlit and Rasa that transforms traditional e‑commerce browsing into conversational shopping. Search by natural language, refine with contextual filters, manage cart and addresses, and checkout in one message—all while tracking orders with dynamic ETAs.

# ✨ Features
Natural Language Search: Ask for "phones under 40k with 120Hz" or "coats" and get instant results.
Contextual Price Refinement: Follow‑up with "under 2000" or "between 1k and 2k" to filter the same category without repeating the query.
Smart Recommendations: Get relevant complementary product suggestions after adding items to cart.
Live Totals Breakdown: Transparent subtotal, discount, shipping, and tax with coupon support (e.g., SAVE10, LESS50).
Address Book: Save multiple delivery addresses with default selection; checkout gates on a selected address.
One‑Message Checkout: Type "checkout" in chat or click the sidebar button—both paths confirm the order with ID, totals, and shipping details.
Dynamic Order Tracking: Track orders with "track ORD001" and get status + expected delivery computed from SLA strings like "3–5 business days."
Session Persistence: User carts, orders, and addresses persist across sessions (demo uses JSON; production can swap to Postgres/Firebase).
# 🛠️ Tech Stack
Frontend: Streamlit (Python web app)
Backend NLU: Rasa (intent classification, entity extraction, custom actions)
Data: CSV for products; JSON for users/carts/orders (demo persistence)
Libraries: pandas, rapidfuzz (fuzzy matching), requests
# 📂 Project Structure
├── README.md

├── requirements.txt

├── app/

│ ├── app.py # Streamlit frontend

│ ├── users_data.json # Demo user accounts (sign-up/login)

│ └── products.csv # Product catalog

│ └── order.csv # Orders catalog

└── rasa/

├── domain.yml

├── config.yml

├── credentials.yml

├── endpoints.yml

├── data/

│ ├── nlu.yml

│ ├── stories.yml

│ └── rules.yml

└── actions/

└── actions.py # Custom actions (search, add to cart, track order)
