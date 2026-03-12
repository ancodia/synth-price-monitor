"""
Streamlit dashboard for the UK Synth Price Monitor.

Run with:
    streamlit run dashboard/app.py
"""
import os
import sys

import plotly.graph_objects as go
import streamlit as st

# Make src/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from database import Database
from models import PriceSnapshot, StockStatus
from pipeline import get_best_deals, init_db
from scraper_sync import scrape_product_sync
from scrapers.registry import get_scraper_for_url

# ------------------------------------------------------------------
# Page config & custom CSS
# ------------------------------------------------------------------

st.set_page_config(
    page_title="Synth Price Monitor",
    page_icon="🎹",
    layout="wide",
)

st.markdown(
    """
<style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .stMetric label, .stMetric [data-testid="stMetricValue"], .stMetric [data-testid="stMetricDelta"] {
        color: #111111 !important;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
    }
    .success-badge {
        background-color: #d4edda;
        color: #155724;
        padding: 5px 10px;
        border-radius: 3px;
        display: inline-block;
    }
    .warning-badge {
        background-color: #fff3cd;
        color: #856404;
        padding: 5px 10px;
        border-radius: 3px;
        display: inline-block;
    }
    .danger-badge {
        background-color: #f8d7da;
        color: #721c24;
        padding: 5px 10px;
        border-radius: 3px;
        display: inline-block;
    }
    .site-badge {
        background-color: #e7f3ff;
        color: #004085;
        padding: 3px 8px;
        border-radius: 3px;
        font-size: 0.85em;
        display: inline-block;
        margin-right: 5px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "price_monitor.db")
db = Database(DB_PATH)
init_db(db)

# ------------------------------------------------------------------
# Sidebar — add product
# ------------------------------------------------------------------

with st.sidebar:
    st.header("Add Product")
    st.caption("Paste a product URL from a supported retailer")

    product_url = st.text_input(
        "Product URL",
        placeholder="https://www.thomann.co.uk/gb/...",
        help="Supported: Thomann, Gear4Music, Juno Records",
    )
    
    # Get unique existing product names for suggestions
    all_products = db.get_all_active_products()
    existing_names = sorted(set(p.name for p in all_products))
    
    # Dropdown with existing names + option to add new
    name_options = ["➕ Add new product name..."] + existing_names
    
    selected_option = st.selectbox(
        "Product Name",
        options=name_options,
        help="Select an existing product to add another retailer, or create a new product group",
    )
    
    # Show text input only if "Add new" is selected
    if selected_option == "➕ Add new product name...":
        product_name = st.text_input(
            "Enter new product name",
            placeholder="e.g., Roland TR-8S",
            help="This name will be used to group variants across retailers",
        )
    else:
        product_name = selected_option
        st.info(f"Adding another retailer for: **{product_name}**")

    if st.button("Add Product", type="primary"):
        if not product_url:
            st.error("Please enter a URL")
        elif not product_name:
            st.error("Please enter a product name")
        else:
            try:
                get_scraper_for_url(product_url)  # validate domain first
                # Extract a short site label from the domain
                domain_part = product_url.split("/")[2]  # e.g. "www.thomann.co.uk"
                site = domain_part.replace("www.", "").split(".")[0]  # "thomann"

                with st.spinner("Fetching product details..."):
                    product_data = scrape_product_sync(product_url)

                    if product_data:
                        # Check if this URL already exists (possibly soft-deleted)
                        existing = db.conn.execute(
                            "SELECT id, is_active FROM products WHERE url = ?",
                            (product_url,)
                        ).fetchone()
                        
                        if existing and existing["is_active"]:
                            # Product already exists and is active
                            st.error("This URL is already being tracked")
                        else:
                            if existing and not existing["is_active"]:
                                # Reactivate soft-deleted product
                                product_id = existing["id"]
                                db.conn.execute(
                                    "UPDATE products SET is_active = 1, name = ? WHERE id = ?",
                                    (product_name.strip(), product_id)
                                )
                                db.conn.commit()
                                st.success(f"Reactivated: {product_name}")
                            else:
                                # New product - insert normally
                                product_id = db.add_product(
                                    name=product_name.strip(),
                                    site=site,
                                    url=product_url,
                                )
                                st.success(f"Added: {product_name}")

                            # Add new snapshot regardless of whether reactivated or new
                            snapshot = PriceSnapshot(
                                product_id=product_id,
                                price=product_data.price,
                                currency=product_data.currency,
                                stock_status=product_data.stock_status,
                            )
                            db.insert_snapshot(snapshot)
                            
                            # Ensure alert config exists
                            existing_config = db.get_alert_config(product_id)
                            if not existing_config:
                                db.add_alert_config(product_id, threshold_percent=5.0)

                            st.cache_data.clear()  # Clear cache to show new product immediately
                            st.rerun()
                    else:
                        st.error("Failed to extract product details")

            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Error: {e}")

# ------------------------------------------------------------------
# Main dashboard header
# ------------------------------------------------------------------

st.title("UK Synth Price Monitor")
st.caption("Automated price tracking across UK music retailers")

# ------------------------------------------------------------------
# Cached data helpers (TTL=60s prevents DB hammering on every rerun)
# ------------------------------------------------------------------

@st.cache_data(ttl=60)
def cached_get_products(_db):
    return _db.get_all_active_products()


@st.cache_data(ttl=60)
def cached_get_best_deals(_db):
    return get_best_deals()


@st.cache_data(ttl=60)
def cached_get_last_snapshot(_db, product_id):
    return _db.get_last_snapshot(product_id)


@st.cache_data(ttl=60)
def cached_get_price_history(_db, product_id, days=30):
    return _db.get_price_history(product_id, days=days)


# ------------------------------------------------------------------
# Summary metrics row
# ------------------------------------------------------------------

products = cached_get_products(db)
best_deals = cached_get_best_deals(db)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Products Tracked", len(products))
with col2:
    st.metric("Active Alerts", db.count_active_alerts())
with col3:
    if best_deals:
        max_saving = max(d["savings"] for d in best_deals)
        st.metric("Best Deal Saving", f"£{max_saving:.2f}")
    else:
        st.metric("Best Deal Saving", "£0.00")
with col4:
    st.metric("Alerts (24h)", db.count_alerts_last_24h())

st.divider()

# ------------------------------------------------------------------
# Product grouping helper
# ------------------------------------------------------------------

def group_products(product_list):
    """
    Group products by exact name match (user-provided names).
    
    Returns:
        List of dicts with 'group_name' and 'products' (list)
    """
    groups = {}
    
    for product in product_list:
        # Use exact name as grouping key
        group_key = product.name.strip()
        
        if group_key not in groups:
            groups[group_key] = {
                'group_name': group_key,
                'products': []
            }
        
        groups[group_key]['products'].append(product)
    
    # Sort groups by name
    return sorted(groups.values(), key=lambda g: g['group_name'])


# ------------------------------------------------------------------
# Filters
# ------------------------------------------------------------------

st.subheader("Filters")
fcol1, fcol2, fcol3 = st.columns(3)

with fcol1:
    show_only_deals = st.checkbox("Recent price drops only", value=False)
with fcol2:
    show_only_in_stock = st.checkbox("In stock only", value=False)
with fcol3:
    sort_by = st.selectbox(
        "Sort by",
        ["Name", "Biggest recent drop", "Lowest price", "Newest"],
    )

# Apply filters
filtered_products = list(products)

if show_only_deals:
    filtered_products = [
        p for p in filtered_products if db.had_price_drop_last_7_days(p.id)
    ]

if show_only_in_stock:
    filtered_products = [
        p
        for p in filtered_products
        if (
            (snap := cached_get_last_snapshot(db, p.id)) is not None
            and snap.stock_status == StockStatus.IN_STOCK
        )
    ]

# Apply sorting
if sort_by == "Biggest recent drop":
    filtered_products.sort(
        key=lambda p: db.get_biggest_drop_last_30_days(p.id) or 0,
        reverse=True,
    )
elif sort_by == "Lowest price":
    filtered_products.sort(
        key=lambda p: (
            snap.price
            if (snap := cached_get_last_snapshot(db, p.id))
            else float("inf")
        )
    )
elif sort_by == "Newest":
    filtered_products.sort(key=lambda p: p.added_date, reverse=True)
else:
    filtered_products.sort(key=lambda p: p.name)

# Group products by normalized name
product_groups = group_products(filtered_products)

st.caption(f"Showing {len(filtered_products)} products in {len(product_groups)} groups")

# ------------------------------------------------------------------
# Product list (grouped by product)
# ------------------------------------------------------------------

for group in product_groups:
    # Determine the best price across all sites in this group
    site_prices = []
    for product in group['products']:
        latest = cached_get_last_snapshot(db, product.id)
        if latest and latest.stock_status == StockStatus.IN_STOCK:
            site_prices.append({
                'site': product.site,
                'price': latest.price,
                'product': product,
                'snapshot': latest
            })
    
    # Build the expander title with price info
    if len(group['products']) == 1:
        # Single site - show simple title
        product = group['products'][0]
        latest = cached_get_last_snapshot(db, product.id)
        if latest:
            title = f"🎹 {product.name} — £{latest.price:.2f} ({product.site.title()})"
        else:
            title = f"🎹 {product.name} — {product.site.title()}"
    else:
        # Multi-site - show best price
        if site_prices:
            best_price = min(p['price'] for p in site_prices)
            title = f"🎹 {group['group_name']} — from £{best_price:.2f} ({len(site_prices)} sites)"
        else:
            title = f"🎹 {group['group_name']} — {len(group['products'])} sites tracked"
    
    with st.expander(title, expanded=False):
        # If multiple sites, show comparison table and combined chart
        if len(group['products']) > 1:
            st.subheader("Price Comparison")
            
            if site_prices:
                # Sort by price (ascending - cheapest first)
                site_prices.sort(key=lambda x: x['price'])
                
                comparison_cols = st.columns([2, 1, 1, 1, 1, 1])
                comparison_cols[0].markdown("**Retailer**")
                comparison_cols[1].markdown("**Price**")
                comparison_cols[2].markdown("**Stock**")
                comparison_cols[3].markdown("**Alert %**")
                comparison_cols[4].markdown("**Stock Alert**")
                comparison_cols[5].markdown("")
                
                # Track if any settings changed
                settings_to_save = []
                
                for site_info in site_prices:
                    ccol1, ccol2, ccol3, ccol4, ccol5, ccol6 = st.columns([2, 1, 1, 1, 1, 1])
                    
                    with ccol1:
                        st.markdown(f'<span class="site-badge">{site_info["site"].title()}</span>', unsafe_allow_html=True)
                    
                    with ccol2:
                        # Highlight best price
                        if site_info['price'] == site_prices[0]['price']:
                            st.markdown(f"**£{site_info['price']:.2f}** 🏆")
                        else:
                            st.write(f"£{site_info['price']:.2f}")
                    
                    with ccol3:
                        if site_info['snapshot'].stock_status == StockStatus.IN_STOCK:
                            st.markdown('<span class="success-badge">In Stock</span>', unsafe_allow_html=True)
                        elif site_info['snapshot'].stock_status == StockStatus.LOW_STOCK:
                            st.markdown('<span class="warning-badge">Low Stock</span>', unsafe_allow_html=True)
                        else:
                            st.markdown('<span class="danger-badge">Out of Stock</span>', unsafe_allow_html=True)
                    
                    # Alert settings inline
                    config = db.get_alert_config(site_info['product'].id)
                    
                    with ccol4:
                        threshold = st.number_input(
                            "Threshold",
                            min_value=1.0,
                            max_value=20.0,
                            value=config.threshold_percent if config else 5.0,
                            step=0.5,
                            key=f"threshold_{site_info['product'].id}",
                            label_visibility="collapsed"
                        )
                    
                    with ccol5:
                        alert_stock = st.checkbox(
                            "Stock alert",
                            value=config.alert_on_stock_change if config else True,
                            key=f"stock_alert_{site_info['product'].id}",
                            label_visibility="collapsed"
                        )
                    
                    with ccol6:
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("💾", key=f"save_{site_info['product'].id}", help="Save alert settings"):
                                db.update_alert_config(site_info['product'].id, threshold, alert_stock)
                                st.success("Saved!")
                        with col_b:
                            st.link_button("🔗", str(site_info['product'].url), help="View product")
                
                # Calculate savings
                if len(site_prices) >= 2:
                    savings = site_prices[-1]['price'] - site_prices[0]['price']
                    if savings > 0:
                        st.success(f"💰 Save £{savings:.2f} by choosing {site_prices[0]['site'].title()} over {site_prices[-1]['site'].title()}")
            else:
                st.info("All variants are currently out of stock")
            
            st.divider()
            
            # Combined chart showing all sites
            st.subheader("Price History (All Sites)")
            
            # Collect history for all products in the group
            fig = go.Figure()
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
            
            for idx, product in enumerate(group['products']):
                history = cached_get_price_history(db, product.id, days=30)
                if history and len(history) > 1:
                    fig.add_trace(
                        go.Scatter(
                            x=[h.scraped_at for h in history],
                            y=[h.price for h in history],
                            mode="lines+markers",
                            name=product.site.title(),
                            line=dict(color=colors[idx % len(colors)], width=2),
                            marker=dict(size=6),
                            hovertemplate=f"{product.site.title()}<br>£%{{y:.2f}}<br>%{{x}}<extra></extra>",
                        )
                    )
            
            if fig.data:
                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Price (£)",
                    height=400,
                    hovermode="x unified",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Not enough data for a chart yet. Check back after the next scrape.")
            
            st.divider()
            
            # Delete buttons for each site variant
            st.subheader("Manage Retailers")
            delete_cols = st.columns(len(group['products']))
            for idx, product in enumerate(group['products']):
                with delete_cols[idx]:
                    st.write(f"**{product.site.title()}**")
                    if st.button("🗑️ Delete", key=f"del_{product.id}", type="secondary"):
                        if st.session_state.get(f"confirm_del_{product.id}", False):
                            db.delete_product(product.id)
                            st.success("Deleted!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.session_state[f"confirm_del_{product.id}"] = True
                            st.warning("Click again to confirm")
        
        # Single-site product - show individual chart and settings
        else:
            product = group['products'][0]
            left_col, right_col = st.columns([3, 1])

            with left_col:
                history = cached_get_price_history(db, product.id, days=30)

                if history and len(history) > 1:
                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=[h.scraped_at for h in history],
                            y=[h.price for h in history],
                            mode="lines+markers",
                            name=product.site.title(),
                            line=dict(width=2),
                            marker=dict(size=8),
                            hovertemplate="£%{y:.2f}<br>%{x}<extra></extra>",
                        )
                    )
                    fig.update_layout(
                        title=f"30-Day Price History — {product.site.title()}",
                        xaxis_title="Date",
                        yaxis_title="Price (£)",
                        height=300,
                        hovermode="x unified",
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    latest = history[-1]

                    if latest.stock_status == StockStatus.IN_STOCK:
                        st.markdown(
                            f'<div class="success-badge">In Stock — £{latest.price:.2f}</div>',
                            unsafe_allow_html=True,
                        )
                    elif latest.stock_status == StockStatus.LOW_STOCK:
                        st.markdown(
                            f'<div class="warning-badge">Low Stock — £{latest.price:.2f}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            '<div class="danger-badge">Out of Stock</div>',
                            unsafe_allow_html=True,
                        )

                    if len(history) >= 2:
                        price_change = history[-1].price - history[-2].price
                        if abs(price_change) > 0.01:
                            change_pct = price_change / history[-2].price * 100
                            if price_change < 0:
                                st.success(
                                    f"Price dropped £{abs(price_change):.2f} "
                                    f"({abs(change_pct):.1f}%) since last check"
                                )
                            else:
                                st.warning(
                                    f"Price increased £{price_change:.2f} "
                                    f"({change_pct:.1f}%) since last check"
                                )
                else:
                    st.info(
                        "Not enough data for a chart yet. Check back after the next scrape."
                    )

            with right_col:
                st.link_button("View Product", str(product.url))

                st.subheader("Alert Settings")
                config = db.get_alert_config(product.id)

                threshold = st.slider(
                    "Drop threshold (%)",
                    min_value=1.0,
                    max_value=20.0,
                    value=config.threshold_percent if config else 5.0,
                    step=0.5,
                    key=f"threshold_{product.id}",
                    help="Send alert when price drops by this percentage",
                )

                alert_stock = st.checkbox(
                    "Alert on back-in-stock",
                    value=config.alert_on_stock_change if config else True,
                    key=f"stock_{product.id}",
                )

                if st.button("Save Settings", key=f"save_{product.id}"):
                    db.update_alert_config(product.id, threshold, alert_stock)
                    st.success("Saved!")

                if st.button("Test Alert", key=f"test_{product.id}"):
                    latest = cached_get_last_snapshot(db, product.id)
                    if latest:
                        from notifications import send_slack_alert

                        send_slack_alert(
                            product.name,
                            latest.price * 1.1,
                            latest.price,
                            10.0,
                            str(product.url),
                            product.site,
                        )
                        st.success("Test alert sent to Slack!")

                st.divider()

                if st.button("Delete", key=f"del_{product.id}", type="secondary"):
                    if st.session_state.get(f"confirm_del_{product.id}", False):
                        db.delete_product(product.id)
                        st.success("Deleted!")
                        st.cache_data.clear()  # Clear cache to update product list immediately
                        st.rerun()
                    else:
                        st.session_state[f"confirm_del_{product.id}"] = True
                        st.warning("Click again to confirm deletion")

                if config and config.last_alert_sent:
                    st.caption(
                        f"Last alert: {config.last_alert_sent.strftime('%Y-%m-%d %H:%M')}"
                    )

# ------------------------------------------------------------------
# Best deals section
# ------------------------------------------------------------------

st.divider()
st.subheader("Best Deals Across Sites")

if best_deals:
    for deal in best_deals[:5]:
        dcol1, dcol2, dcol3 = st.columns([3, 1, 1])

        with dcol1:
            st.markdown(f"**{deal['product_name'].title()}**")
        with dcol2:
            st.metric(
                "Best Price",
                f"£{deal['best_price']:.2f}",
                delta=f"-£{deal['savings']:.2f}",
                delta_color="inverse",
            )
        with dcol3:
            st.markdown(f"[{deal['best_site'].title()}]({deal['best_url']})")

        with st.expander("See all prices"):
            for price_info in deal["all_prices"]:
                pc1, pc2, pc3 = st.columns([2, 1, 1])
                pc1.write(price_info["site"].title())
                pc2.write(f"£{price_info['price']:.2f}")
                pc3.link_button("View", price_info["url"])
else:
    st.info(
        "No multi-site products tracked yet. "
        "Add the same product from different retailers to compare prices."
    )

st.divider()