"""Stripe Connect integration for marketplace payments.

Provides reusable logic for:
  - Creating Express connected accounts for payees (KJs, contractors, etc.)
  - Generating onboarding links so payees can complete Stripe verification
  - Generating dashboard links for payees to view their balances/payouts
  - Calculating application fees (platform cut) on charges
  - Creating destination-charge PaymentIntents that split payments

Designed to be reusable across TheHopper (KJs) and DoTeam (evaluators).

Environment variables:
  STRIPE_SECRET_KEY          — platform's secret key
  STRIPE_PUBLISHABLE_KEY     — platform's publishable key
  STRIPE_CONNECT_PLATFORM_FEE_PCT — platform fee percentage (default 15.0)
  STRIPE_WEBHOOK_SECRET      — webhook signing secret
  STRIPE_CONNECT_RETURN_URL  — where to send payees after onboarding/dashboard

Usage:
  from stripe_connect import ConnectManager

  manager = ConnectManager()
  account = manager.create_connected_account(email="kj@example.com")
  link = manager.create_onboarding_link(account.id)
  pi = manager.create_destination_charge(
      amount_cents=5000,
      connected_account_id=account.id,
      description="Premium slot — TheHopper",
  )
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import stripe


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PLATFORM_FEE_PCT = float(os.environ.get("STRIPE_CONNECT_PLATFORM_FEE_PCT", "15.0"))
RETURN_URL = os.environ.get(
    "STRIPE_CONNECT_RETURN_URL",
    "http://localhost:5173",  # Vite dev server default
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConnectAccount:
    """Snapshot of a connected account's status."""

    id: str
    email: str
    details_submitted: bool
    charges_enabled: bool
    payouts_enabled: bool
    requirements: dict[str, Any]
    business_type: str | None = None
    country: str | None = None
    display_name: str | None = None

    @property
    def is_fully_onboarded(self) -> bool:
        """True when the account can receive charges and payouts."""
        return self.charges_enabled and self.payouts_enabled

    @property
    def onboarding_status(self) -> str:
        """Human-readable onboarding status."""
        if self.is_fully_onboarded:
            return "active"
        if self.details_submitted:
            return "pending_verification"
        return "needs_onboarding"

    @property
    def missing_info(self) -> list[str]:
        """Fields Stripe says are still needed."""
        return self.requirements.get("currently_due", []) or []


@dataclass
class FeeBreakdown:
    """Breakdown of a destination-charge payment split."""

    total_cents: int
    platform_fee_cents: int
    connected_amount_cents: int
    stripe_processing_cents: int
    platform_net_cents: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total_cents / 100,
            "platform_fee": self.platform_fee_cents / 100,
            "connected_amount": self.connected_amount_cents / 100,
            "stripe_processing": self.stripe_processing_cents / 100,
            "platform_net": self.platform_net_cents / 100,
            "fee_percentage": PLATFORM_FEE_PCT,
        }


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class ConnectManager:
    """Manages Stripe Connect (Express account) lifecycle.

    All methods talk to the Stripe API directly. The calling app is
    responsible for persisting the returned account IDs in its own database.
    """

    def __init__(self, fee_pct: float | None = None) -> None:
        self.fee_pct = fee_pct if fee_pct is not None else PLATFORM_FEE_PCT
        stripe.api_key = os.environ.get(
            "STRIPE_SECRET_KEY", "sk_tes...T_ME"
        )
        self._test_mode = stripe.api_key.startswith("sk_tes")

    # ------------------------------------------------------------------
    # Account creation
    # ------------------------------------------------------------------

    def create_connected_account(
        self,
        email: str,
        business_type: str = "individual",
        country: str = "US",
        metadata: dict[str, str] | None = None,
    ) -> ConnectAccount:
        """Create an Express connected account for a payee.

        Args:
            email: Payee's email address.
            business_type: "individual" or "company".
            country: 2-letter country code.
            metadata: Optional metadata (e.g. venue_id, user_id) for tracking.

        Returns:
            ConnectAccount with the initial status.
        """
        if self._test_mode:
            return self._mock_account(email)

        acct = stripe.Account.create(
            type="express",
            email=email,
            country=country,
            business_type=business_type,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            metadata=metadata or {},
        )
        return self._account_from_stripe(acct)

    def create_or_update_person(
        self,
        account_id: str,
        first_name: str | None = None,
        last_name: str | None = None,
        dob_day: int | None = None,
        dob_month: int | None = None,
        dob_year: int | None = None,
        address_line1: str | None = None,
        address_city: str | None = None,
        address_state: str | None = None,
        address_postal_code: str | None = None,
        ssn_last_4: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        is_representative: bool = True,
        person_id: str | None = None,
    ) -> str:
        """Create or update a Person on an Express account for KYC prefill.

        IMPORTANT: This must be called BEFORE creating an Account Link.
        Once an Account Link is created for an Express account, Stripe
        locks KYC info and it can no longer be read or updated via API.

        For Express accounts, the account holder still needs to visit
        Stripe's hosted onboarding page to confirm the prefilled data,
        add their payout method, and accept TOS. Prefill just makes
        that page faster -- they confirm instead of typing.

        Args:
            account_id: The connected account ID.
            first_name / last_name: Legal name.
            dob_day / dob_month / dob_year: Date of birth.
            address_*: Physical address.
            ssn_last_4: Last 4 of SSN.
            phone: Phone number.
            email: Email (can differ from account email).
            is_representative: True for the account representative.
            person_id: If updating an existing Person, their ID.
                If None, creates a new Person.

        Returns:
            The Person ID.
        """
        if self._test_mode:
            return f"person_test_{account_id}"

        # Build the person data dict with only provided fields
        person_data: dict[str, Any] = {}
        if first_name:
            person_data["first_name"] = first_name
        if last_name:
            person_data["last_name"] = last_name
        if dob_day is not None and dob_month is not None and dob_year is not None:
            person_data["dob"] = {"day": dob_day, "month": dob_month, "year": dob_year}
        if address_line1:
            person_data["address"] = {
                "line1": address_line1,
                "city": address_city or "",
                "state": address_state or "",
                "postal_code": address_postal_code or "",
                "country": "US",
            }
        if ssn_last_4:
            person_data["ssn_last_4"] = ssn_last_4
        if phone:
            person_data["phone"] = phone
        if email:
            person_data["email"] = email
        if is_representative:
            person_data["relationship"] = {"representative": True}

        if person_id:
            person = stripe.Person.modify(
                person_id,
                account=account_id,
                **person_data,
            )
        else:
            person = stripe.Person.create(
                account=account_id,
                **person_data,
            )
        return person.id

    def set_daily_payouts(self, account_id: str) -> bool:
        """Configure an Express account for daily automatic payouts.

        By default, Stripe Express accounts are on a 2-day rolling
        schedule. This sets it to daily (funds paid out as soon as
        they're available). Call this after the account is active
        (charges_enabled and payouts_enabled).

        Returns True if successful, False otherwise.
        """
        if self._test_mode:
            return True

        try:
            stripe.Account.modify(
                account_id,
                settings={
                    "payouts": {
                        "schedule": {
                            "interval": "daily",
                        },
                    },
                },
            )
            return True
        except Exception:
            return False

    def retrieve_account(self, account_id: str) -> ConnectAccount:
        """Fetch the current status of a connected account."""
        if self._test_mode:
            return self._mock_account("", account_id)
        acct = stripe.Account.retrieve(account_id)
        return self._account_from_stripe(acct)

    # ------------------------------------------------------------------
    # Onboarding links
    # ------------------------------------------------------------------

    def create_onboarding_link(
        self,
        account_id: str,
        return_url: str | None = None,
        refresh_url: str | None = None,
    ) -> str:
        """Generate a Stripe-hosted onboarding link for an Express account.

        The payee follows this URL to complete their Stripe onboarding
        (identity verification, bank account, tax info). Returns the URL
        to redirect them to.
        """
        if self._test_mode:
            return f"/api/connect/test-onboarding?account_id={account_id}"

        link = stripe.AccountLink.create(
            account=account_id,
            type="account_onboarding",
            return_url=return_url or f"{RETURN_URL}?connect=complete",
            refresh_url=refresh_url or f"{RETURN_URL}?connect=refresh",
        )
        return link.url

    def create_dashboard_link(self, account_id: str) -> str:
        """Generate a login link to the Express Dashboard for a payee."""
        if self._test_mode:
            return f"/api/connect/test-dashboard?account_id={account_id}"

        link = stripe.Account.create_login_link(account_id)
        return link.url

    # ------------------------------------------------------------------
    # Payments — destination charges with application fee
    # ------------------------------------------------------------------

    def calculate_fee(self, amount_cents: int) -> FeeBreakdown:
        """Calculate the fee split for a given charge amount.

        The platform fee is a percentage of the total charge.
        Stripe's processing fee (2.9% + $0.30) comes out of the
        total first, then the platform fee goes to the platform,
        and the remainder goes to the connected account.

        If you want the connected account to receive a *clean* percentage
        of the gross, use calculate_fee_from_gross instead.
        """
        total = amount_cents
        # Stripe processing: 2.9% + 30 cents
        stripe_fee = int(round(total * 0.029)) + 30
        # Platform fee: percentage of total
        platform_fee = int(round(total * self.fee_pct / 100))
        # Connected account gets the rest
        connected = total - stripe_fee - platform_fee
        # Platform net = platform fee minus Stripe processing (if platform
        # absorbs the Stripe fee)
        platform_net = platform_fee - stripe_fee

        return FeeBreakdown(
            total_cents=total,
            platform_fee_cents=platform_fee,
            connected_amount_cents=connected,
            stripe_processing_cents=stripe_fee,
            platform_net_cents=platform_net,
        )

    def calculate_fee_from_gross(
        self, amount_cents: int, connected_share_pct: float
    ) -> FeeBreakdown:
        """Calculate fees so the connected account gets a clean % of gross.

        Example: If connected_share_pct=80 and amount=$100:
          - Connected account gets $80.00
          - Stripe fee ($3.20) comes from the platform's share
          - Platform nets $16.80

        This makes the connected amount predictable and easy to communicate.
        """
        total = amount_cents
        connected = int(round(total * connected_share_pct / 100))
        platform_fee = total - connected
        # Stripe processing comes out of the platform's portion
        stripe_fee = int(round(total * 0.029)) + 30
        platform_net = platform_fee - stripe_fee

        return FeeBreakdown(
            total_cents=total,
            platform_fee_cents=platform_fee,
            connected_amount_cents=connected,
            stripe_processing_cents=stripe_fee,
            platform_net_cents=platform_net,
        )

    def create_checkout_session_with_fee(
        self,
        amount_cents: int,
        connected_account_id: str,
        product_name: str,
        product_description: str = "",
        success_url: str = "",
        cancel_url: str = "",
        metadata: dict[str, str] | None = None,
    ) -> stripe.checkout.Session:
        """Create a Stripe Checkout session with a destination charge.

        The customer pays through Stripe Checkout. The charge lands on
        Alchemy's account, the application_fee_amount is taken as the
        platform cut, and the remainder is transferred to the connected
        account automatically.

        If the connected account is not yet charges_enabled, this will
        raise a StripeError — check account status before calling.
        """
        fee = self.calculate_fee(amount_cents)

        if self._test_mode:
            # Return a mock-like object
            class _MockSession:
                id = f"test_session_{amount_cents}"
                url = f"/api/payment-test?account={connected_account_id}"
                payment_intent = f"test_pi_{amount_cents}"
            return _MockSession()  # type: ignore

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": product_name,
                            "description": product_description,
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url or f"{RETURN_URL}?payment=success",
            cancel_url=cancel_url or f"{RETURN_URL}?payment=cancelled",
            # This is the key Connect parameter:
            #   - destination tells Stripe to transfer to the connected account
            #   - application_fee_amount is the platform's cut
            payment_intent_data={
                "application_fee_amount": fee.platform_fee_cents,
                "transfer_data": {
                    "destination": connected_account_id,
                },
            },
            metadata=metadata or {},
        )
        return session

    def create_payment_intent_with_fee(
        self,
        amount_cents: int,
        connected_account_id: str,
        description: str = "",
        metadata: dict[str, str] | None = None,
    ) -> stripe.PaymentIntent:
        """Create a PaymentIntent with a destination charge (no Checkout UI).

        Use this when you have your own payment form (Stripe Elements) and
        want to handle the UI yourself instead of using Stripe Checkout.
        """
        fee = self.calculate_fee(amount_cents)

        if self._test_mode:
            class _MockPI:
                id = f"test_pi_{amount_cents}"
                client_secret = f"test_secret_{amount_cents}"
            return _MockPI()  # type: ignore

        pi = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            description=description,
            application_fee_amount=fee.platform_fee_cents,
            transfer_data={"destination": connected_account_id},
            metadata=metadata or {},
            automatic_payment_methods={"enabled": True},
        )
        return pi

    # ------------------------------------------------------------------
    # Payouts & transfers
    # ------------------------------------------------------------------

    def list_transfers(self, connected_account_id: str, limit: int = 10) -> list[dict]:
        """List recent transfers to a connected account."""
        if self._test_mode:
            return []
        transfers = stripe.Transfer.list(
            destination=connected_account_id, limit=limit
        )
        return [
            {
                "id": t.id,
                "amount": t.amount,
                "currency": t.currency,
                "created": t.created,
                "description": t.description,
            }
            for t in transfers.data
        ]

    def get_account_balance(self, connected_account_id: str) -> dict[str, Any]:
        """Get the current balance for a connected account."""
        if self._test_mode:
            return {"available": 0, "pending": 0, "currency": "usd"}
        balance = stripe.Balance.retrieve(stripe_account=connected_account_id)
        available = sum(b.amount for b in balance.available)
        pending = sum(b.amount for b in balance.pending)
        return {
            "available": available,
            "pending": pending,
            "currency": balance.available[0].currency if balance.available else "usd",
        }

    # ------------------------------------------------------------------
    # Product / price management (KJ-configurable premium slot products)
    # ------------------------------------------------------------------

    def create_product(
        self,
        connected_account_id: str,
        name: str,
        description: str = "",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Create a product on the connected account.

        Products are created on the connected account (not the platform)
        so they belong to the KJ. Prices are created separately and linked.

        Returns the product ID.
        """
        if self._test_mode:
            return f"prod_test_{name[:10]}"

        product = stripe.Product.create(
            name=name,
            description=description,
            metadata=metadata or {},
            stripe_account=connected_account_id,
        )
        return product.id

    def create_price(
        self,
        connected_account_id: str,
        product_id: str,
        amount_cents: int,
        currency: str = "usd",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Create a price for a product on the connected account.

        Returns the price ID.
        """
        if self._test_mode:
            return f"price_test_{amount_cents}"

        price = stripe.Price.create(
            product=product_id,
            unit_amount=amount_cents,
            currency=currency,
            metadata=metadata or {},
            stripe_account=connected_account_id,
        )
        return price.id

    def list_products(
        self, connected_account_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List all products on a connected account."""
        if self._test_mode:
            return []

        products = stripe.Product.list(
            stripe_account=connected_account_id,
            limit=limit,
            active=True,
        )
        result = []
        for p in products.data:
            # Fetch prices for each product
            prices = stripe.Price.list(
                stripe_account=connected_account_id,
                product=p.id,
                active=True,
                limit=5,
            )
            result.append({
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "active": p.active,
                "prices": [
                    {
                        "id": pr.id,
                        "amount_cents": pr.unit_amount,
                        "amount_usd": (pr.unit_amount or 0) / 100,
                        "currency": pr.currency,
                        "active": pr.active,
                    }
                    for pr in prices.data
                ],
                "metadata": dict(p.metadata or {}),
            })
        return result

    def update_product(
        self,
        connected_account_id: str,
        product_id: str,
        active: bool | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        """Update a product on a connected account.

        Setting active=False deactivates the product (it won't show up
        in active listings but remains in the Stripe dashboard).
        """
        if self._test_mode:
            return True

        update_data: dict[str, Any] = {}
        if active is not None:
            update_data["active"] = active
        if name:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if metadata:
            update_data["metadata"] = metadata

        if not update_data:
            return False

        stripe.Product.modify(
            product_id,
            stripe_account=connected_account_id,
            **update_data,
        )
        return True

    def create_checkout_with_product(
        self,
        connected_account_id: str,
        price_id: str,
        platform_fee_cents: int,
        success_url: str = "",
        cancel_url: str = "",
        metadata: dict[str, str] | None = None,
    ) -> stripe.checkout.Session:
        """Create a Checkout session using an existing product/price.

        This is the product-based alternative to create_checkout_session_with_fee
        which uses ad-hoc price_data. Using a real price ID means the
        product shows up properly in the KJ's Stripe dashboard and
        can be enabled/disabled without code changes.
        """
        if self._test_mode:
            class _MockSession:
                id = f"test_session_{price_id}"
                url = f"/api/payment-test?price={price_id}"
                payment_intent = f"test_pi_{price_id}"
            return _MockSession()  # type: ignore

        session = stripe.checkout.Session.create(
            line_items=[{"price": price_id, "quantity": 1}],
            mode="payment",
            success_url=success_url or f"{RETURN_URL}?payment=success",
            cancel_url=cancel_url or f"{RETURN_URL}?payment=cancelled",
            payment_intent_data={
                "application_fee_amount": platform_fee_cents,
                "transfer_data": {"destination": connected_account_id},
            },
            metadata=metadata or {},
        )
        return session

    # ------------------------------------------------------------------
    # Webhook helpers
    # ------------------------------------------------------------------

    @staticmethod
    def verify_webhook_event(payload: bytes, sig_header: str, secret: str) -> stripe.Event:
        """Verify and construct a Stripe Event from a webhook payload."""
        return stripe.Webhook.construct_event(payload, sig_header, secret)

    @staticmethod
    def is_connect_event(event_type: str) -> bool:
        """Check if an event type is Connect-related."""
        connect_events = {
            "account.updated",
            "account.application.authorized",
            "account.application.deauthorized",
            "account.external_account.created",
            "account.external_account.deleted",
            "account.external_account.updated",
            "transfer.created",
            "transfer.reversed",
            "transfer.updated",
        }
        return event_type in connect_events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _account_from_stripe(acct: stripe.Account) -> ConnectAccount:
        return ConnectAccount(
            id=acct.id,
            email=acct.email or "",
            details_submitted=acct.details_submitted,
            charges_enabled=acct.charges_enabled,
            payouts_enabled=acct.payouts_enabled,
            requirements=dict(acct.requirements or {}),
            business_type=getattr(acct, "business_type", None),
            country=getattr(acct, "country", None),
            display_name=getattr(acct, "business_profile", {}).get("name", None)
            if getattr(acct, "business_profile", None)
            else None,
        )

    @staticmethod
    def _mock_account(email: str, account_id: str = "") -> ConnectAccount:
        return ConnectAccount(
            id=account_id or f"acct_test_{email.split('@')[0]}",
            email=email,
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
            requirements={},
            business_type="individual",
            country="US",
            display_name="Test Account",
        )
