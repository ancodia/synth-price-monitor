"""
Playwright e2e tests for the Streamlit dashboard UI.

Validates:
  - Roland TR-8S appears in the product list with all 3 retailers
  - Price comparison table shows correct data
  - Combined price history chart renders
  - Alert settings are accessible and functional
  - Best deals section works for multi-site products

Prerequisites:
  - seeded_db fixture provides 14 days of price history + a Thomann price drop
  - streamlit_app fixture starts the dashboard on a test port
"""
import re

import pytest
from playwright.sync_api import Page, expect


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def expand_product_group(page: Page, product_name: str):
    """Find and click the expander for a given product name."""
    expander = page.locator(f"text=/{re.escape(product_name)}/i").first
    expander.click()
    page.wait_for_timeout(1000)


# ------------------------------------------------------------------
# Product display tests
# ------------------------------------------------------------------

class TestProductDisplay:
    """Verify that seeded products appear correctly in the dashboard."""

    @pytest.fixture(autouse=True)
    def navigate(self, page: Page, streamlit_app: str):
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

    def test_dashboard_title_visible(self, page: Page):
        """The main title should be visible."""
        expect(page.locator("text=UK Synth Price Monitor")).to_be_visible()

    def test_product_count_metric(self, page: Page, attach_screenshot):
        """The 'Products Tracked' metric should show 3 (one per retailer)."""
        metric = page.locator("[data-testid='stMetric']").filter(has_text="Products Tracked")
        expect(metric).to_contain_text("3")
        attach_screenshot(metric.screenshot())

    def test_roland_tr8s_appears_in_list(self, page: Page, attach_screenshot):
        """Roland TR-8S should appear as a grouped product entry."""
        entry = page.locator("text=/Roland TR-8S/").first
        expect(entry).to_be_visible()
        attach_screenshot(entry.locator("..").screenshot())

    def test_group_shows_site_count(self, page: Page):
        """The expander title should mention '3 sites' for the grouped product."""
        expander_title = page.locator("text=/Roland TR-8S/").first
        expect(expander_title).to_contain_text(re.compile(r"3 sites|from £"))

    def test_filters_section_visible(self, page: Page):
        """Filter controls should be present."""
        expect(page.locator("text=Filters")).to_be_visible()
        expect(page.locator("text=Recent price drops only")).to_be_visible()
        expect(page.locator("text=In stock only")).to_be_visible()


# ------------------------------------------------------------------
# Price comparison table tests
# ------------------------------------------------------------------

class TestPriceComparison:
    """Verify the multi-site comparison table inside the product expander."""

    @pytest.fixture(autouse=True)
    def navigate_and_expand(self, page: Page, streamlit_app: str, seeded_db):
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        expand_product_group(page, "Roland TR-8S")
        self.scenario = seeded_db

    def test_comparison_heading_visible(self, page: Page):
        """'Price Comparison' subheader should appear inside the expander."""
        expect(page.locator("text=Price Comparison")).to_be_visible()

    def test_all_retailers_listed(self, page: Page, attach_screenshot):
        """All three retailer badges should be visible."""
        for site in ["Thomann", "Gear4music", "Juno"]:
            expect(page.locator(f"text=/{site}/i").first).to_be_visible()
        attach_screenshot(page.locator("text=Price Comparison").locator("..").screenshot())

    def test_best_price_has_trophy(self, page: Page, attach_screenshot):
        """The lowest price should be marked with the trophy emoji."""
        trophy = page.locator("text=🏆").first
        expect(trophy).to_be_visible()
        attach_screenshot(trophy.locator("..").locator("..").screenshot())

    def test_prices_are_numeric(self, page: Page):
        """At least one GBP price should be visible in the comparison."""
        price_pattern = page.locator("text=/£\\d+\\.\\d{2}/")
        expect(price_pattern.first).to_be_visible()

    def test_stock_badges_visible(self, page: Page):
        """Stock status badges should appear (all seeded as in_stock)."""
        expect(page.locator("text=/In Stock/i").first).to_be_visible()

    def test_savings_message_visible(self, page: Page, attach_screenshot):
        """If there's a price difference, a savings message should appear."""
        # Thomann dropped to 499, others are ~559/569 — savings should show
        savings = page.locator("text=/Save £/").first
        expect(savings).to_be_visible()
        attach_screenshot(savings.locator("..").screenshot())

    def test_alert_threshold_inputs_exist(self, page: Page):
        """Each retailer row should have a threshold number input."""
        threshold_inputs = page.locator("input[type='number']")
        assert threshold_inputs.count() >= 3

    def test_product_links_present(self, page: Page):
        """Each retailer should have a link button to the product page."""
        link_buttons = page.locator("text=🔗")
        assert link_buttons.count() >= 3


# ------------------------------------------------------------------
# Chart tests
# ------------------------------------------------------------------

class TestChartDisplay:
    """Verify that price history charts render correctly."""

    @pytest.fixture(autouse=True)
    def navigate_and_expand(self, page: Page, streamlit_app: str, seeded_db):
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        expand_product_group(page, "Roland TR-8S")

    def test_combined_chart_heading(self, page: Page):
        """The combined chart section heading should be visible."""
        expect(page.locator("text=/Price History.*All Sites/i").first).to_be_visible()

    def test_plotly_chart_renders(self, page: Page, attach_screenshot):
        """A Plotly chart container should be present in the DOM."""
        chart = page.locator(".stPlotlyChart, .js-plotly-plot").first
        expect(chart).to_be_visible(timeout=10_000)
        attach_screenshot(chart.screenshot())

    def test_chart_has_multiple_traces(self, page: Page):
        """The combined chart should show traces for each retailer."""
        chart_area = page.locator(".stPlotlyChart, .js-plotly-plot").first
        for site in ["Thomann", "Gear4music", "Juno"]:
            expect(chart_area.locator(f"text=/{site}/i").first).to_be_visible(
                timeout=5000
            )

    def test_chart_axes_labelled(self, page: Page):
        """Chart should have Price label on y-axis."""
        chart_area = page.locator(".stPlotlyChart, .js-plotly-plot").first
        expect(chart_area.locator("text=/Price/i").first).to_be_visible(timeout=5000)


# ------------------------------------------------------------------
# Manage retailers tests
# ------------------------------------------------------------------

class TestManageRetailers:
    """Verify the delete/manage UI for multi-site products."""

    @pytest.fixture(autouse=True)
    def navigate_and_expand(self, page: Page, streamlit_app: str, seeded_db):
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        expand_product_group(page, "Roland TR-8S")

    def test_manage_retailers_heading(self, page: Page):
        """'Manage Retailers' section should appear for multi-site products."""
        expect(page.locator("text=Manage Retailers")).to_be_visible()

    def test_delete_buttons_per_retailer(self, page: Page):
        """Each retailer should have its own delete button."""
        delete_buttons = page.locator("text=🗑️ Delete")
        assert delete_buttons.count() >= 3


# ------------------------------------------------------------------
# Best deals section tests
# ------------------------------------------------------------------

class TestBestDeals:
    """Verify the cross-site best deals section at the bottom."""

    @pytest.fixture(autouse=True)
    def navigate(self, page: Page, streamlit_app: str, seeded_db):
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

    def test_best_deals_heading(self, page: Page, attach_screenshot):
        """The 'Best Deals Across Sites' section should be visible."""
        heading = page.locator("text=Best Deals Across Sites")
        expect(heading).to_be_visible()
        attach_screenshot(heading.locator("..").screenshot())

    def test_best_deal_shows_roland(self, page: Page):
        """Roland TR-8S should appear in best deals (multi-site tracking)."""
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)
        expect(page.locator("text=/Roland TR-8S/i").first).to_be_visible()
