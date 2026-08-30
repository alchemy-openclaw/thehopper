"""Static privacy policy and support pages.

Apple and Google both require a reachable privacy policy URL, and Apple checks
the support URL during review. These are served from the API host as plain
server-rendered HTML rather than routes in the React SPA, for two reasons:

  1. The SPA returns its shell (HTTP 200) for unknown paths, so a reviewer
     following /privacy would land on the app itself rather than a policy —
     a 200 that still fails review.
  2. The *.karaokespot.us subdomain middleware treats every non-www host as a
     KJ slug. Apex paths sidestep it entirely.

The content below describes what the app actually does. If data collection
changes, update this file in the same commit.
"""

from __future__ import annotations

# Effective date shown on the policy. Bump when the substance changes.
POLICY_EFFECTIVE_DATE = "August 29, 2026"

# Contact address published to users and to app-store reviewers. This MUST be a
# real, monitored mailbox — Apple has rejected apps for unreachable support
# contacts, and the deletion requests below legally have to land somewhere.
CONTACT_EMAIL = "support@karaokespot.us"

_STYLE = """
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: #0d0221;
    color: #e8e6f0;
    font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 32px 20px 72px;
  }
  main { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 30px; line-height: 1.2; margin: 0 0 6px; color: #fff; }
  h2 { font-size: 19px; margin: 34px 0 8px; color: #fff; }
  .eyebrow { color: #ff2d95; font-weight: 700; letter-spacing: .08em;
             text-transform: uppercase; font-size: 12px; margin: 0 0 20px; }
  .updated { color: #9d97b5; font-size: 14px; margin: 0 0 28px; }
  p, li { color: #cfc9e0; }
  ul { padding-left: 20px; }
  li { margin: 6px 0; }
  a { color: #4fd1e5; }
  table { border-collapse: collapse; width: 100%; margin-top: 10px; display: block;
          overflow-x: auto; }
  th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid #2a2140;
           font-size: 15px; vertical-align: top; }
  th { color: #fff; white-space: nowrap; }
  footer { margin-top: 48px; padding-top: 18px; border-top: 1px solid #2a2140;
           color: #7d769b; font-size: 14px; }
"""


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title} — KaraokeSpot</title>
<style>{_STYLE}</style>
</head>
<body><main>
{body}
<footer>KaraokeSpot · <a href="/privacy">Privacy</a> · <a href="/support">Support</a></footer>
</main></body>
</html>"""


def privacy_html() -> str:
    return _page(
        "Privacy Policy",
        f"""
<p class="eyebrow">KaraokeSpot</p>
<h1>Privacy Policy</h1>
<p class="updated">Effective {POLICY_EFFECTIVE_DATE}</p>

<p>KaraokeSpot helps singers find karaoke nights nearby and lets karaoke hosts
(KJs) run their events. This policy explains what we collect, why, and who we
share it with. We do not sell your personal information.</p>

<h2>What we collect</h2>
<table>
  <tr><th>Data</th><th>Why</th></tr>
  <tr><td>Approximate or precise location</td>
      <td>To sort karaoke venues by distance from you. Requested only while the
          app is open, and only if you grant permission. We use it for the
          search and do not keep a history of where you have been.</td></tr>
  <tr><td>Phone number</td>
      <td>To send a one-time SMS code confirming it is yours, and to contact you
          about your requests. Required for KJs, optional for singers.</td></tr>
  <tr><td>Name or stage name</td>
      <td>To show the KJ who is in the queue to sing.</td></tr>
  <tr><td>Song requests and messages you send the KJ</td>
      <td>To pass your request or message to the host running that night.</td></tr>
  <tr><td>Push notification token</td>
      <td>To tell you when your slot is coming up or a KJ replies.</td></tr>
  <tr><td>Singing preferences (vocal range, favourite genres)</td>
      <td>To suggest songs. These stay on your device and are not sent to
          us.</td></tr>
</table>

<h2>If you are a KJ taking payments</h2>
<p>Payouts run through <strong>Stripe</strong>. To open your payout account
Stripe must verify your identity, so the app asks for your legal name, date of
birth, address, and the last four digits of your SSN. That information is
forwarded to Stripe and <strong>is not stored on our servers</strong> — we keep
only your business name and the Stripe account reference needed to send you
money.</p>

<h2>Payments</h2>
<p>Card payments are handled entirely by Stripe on Stripe's own checkout page.
KaraokeSpot never sees or stores your card number. We record that a payment
happened, its amount, and what it was for.</p>

<h2>Who we share data with</h2>
<ul>
  <li><strong>Stripe</strong> — payment processing and KJ identity verification.</li>
  <li><strong>Twilio</strong> — sending SMS verification codes.</li>
  <li><strong>Apple and Google</strong> — delivering push notifications.</li>
  <li><strong>The KJ at the venue you are interacting with</strong> — your
      display name, song request, and any message you send them.</li>
</ul>
<p>We disclose information otherwise only when the law requires it.</p>

<h2>What is stored on your device</h2>
<p>Your singing preferences, your last selected venue, and a login token proving
you verified your phone number. Signing out or deleting the app removes
them.</p>

<h2>Keeping and deleting your data</h2>
<p>We keep your information while your account is active. Song requests and
messages to a KJ are tied to the event they belong to. Payment records are
retained as long as tax and accounting rules require.</p>
<p>To see or delete your data, email <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
from the phone number on your account and we will action it within 30 days.
Deleting a KJ account does not remove payout records Stripe must keep by
law.</p>

<h2>Children</h2>
<p>KaraokeSpot is not directed at children under 13, and we do not knowingly
collect their information. Venues serving alcohol may have their own age
restrictions.</p>

<h2>Changes</h2>
<p>If this policy changes materially we will update the effective date above and
note the change in the app.</p>

<h2>Contact</h2>
<p><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
""",
    )


def support_html() -> str:
    return _page(
        "Support",
        f"""
<p class="eyebrow">KaraokeSpot</p>
<h1>Support</h1>
<p class="updated">We usually reply within one business day.</p>

<p>Email <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> with your question.
If it concerns a specific event, include the venue name and roughly when you
were there — that makes it much faster to look up.</p>

<h2>Common questions</h2>

<h2>No venues are showing up near me</h2>
<p>KaraokeSpot needs location permission to sort venues by distance. Check that
location access is enabled for the app in your device settings. If your area has
no listings yet, add one from the <strong>Add</strong> tab.</p>

<h2>I never got my SMS code</h2>
<p>Codes expire after 10 minutes. Request a new one, and confirm the number you
entered can receive texts. Requesting a new code cancels the previous one, so
always use the most recent message.</p>

<h2>I paid to move up the queue and nothing happened</h2>
<p>Payment confirmation returns you to the app automatically. If it did not,
reopen the app and check with the KJ — your request is sent to them as soon as
the payment clears. If you were charged and your slot never appeared, email us
with the venue and approximate time and we will sort it out.</p>

<h2>I am a KJ and my payouts have not arrived</h2>
<p>Payouts are handled by Stripe and require identity verification to be
complete. Open the KJ screen in the app to see your current status. If Stripe
still needs something from you it will be listed there.</p>

<h2>I want my data deleted</h2>
<p>Email <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> from the phone
number on your account. See the <a href="/privacy">privacy policy</a> for
details.</p>
""",
    )
