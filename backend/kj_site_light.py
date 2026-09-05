"""Light-theme KJ site template for karaokespot.us subdomains.

Renders a self-contained HTML page with a light blue-gray header,
weekday squares, and an app-like layout. Called when ?theme=light
is passed to the KJ site endpoint.
"""
import html
import json as _json
import os
import sqlite3


def _format_phone(phone: str) -> str:
    """Format a phone number as (XXX) XXX-XXXX."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone


def _format_time(t: str) -> str:
    """Convert 24-hour time (HH:MM) to 12-hour with am/pm."""
    try:
        h, m = t.split(":")
        h = int(h)
        suffix = "pm" if h >= 12 else "am"
        h12 = h % 12
        if h12 == 0:
            h12 = 12
        return f"{h12}:{m}{suffix}"
    except Exception:
        return t


def _kj_site_html_light(kj: sqlite3.Row, venues: list[sqlite3.Row]) -> str:
    """Render a light-theme HTML page for a KJ's business.

    Layout: light header > hero (name, phone, bio, weekday strip on left;
    map + venue capsule on right) > services > footer.
    No separate schedule/venues sections — feels more like an app.
    """
    GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    biz = kj["business_name"] or kj["name"]
    biz_esc = html.escape(biz)
    bio = html.escape(kj["bio"] or "Karaoke host. Live karaoke nights, song suggestions, and premium slot bookings through TheHopper.")
    kj_phone = kj["phone"] or ""
    kj_phone_fmt = _format_phone(kj_phone)

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_short = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
    schedule_by_day: dict[str, list[dict]] = {}
    venue_js_data = []

    for v in venues:
        vid = v["id"]
        v_name = html.escape(v["name"])
        v_addr = html.escape(v["address"])
        v_city = html.escape(v["city"])
        v_lat = v["lat"] or 0
        v_lng = v["lng"] or 0
        v_phone = v["phone"] or ""
        v_phone_fmt = _format_phone(v_phone)
        v_website = v["website"] or ""
        v_vibe = html.escape(v["vibe"] or "")
        nights_raw = v["karaoke_nights"] or ""
        nights_list = [n.strip() for n in nights_raw.split(",") if n.strip()]
        nights_display = ", ".join(nights_list) if nights_list else "schedule varies"
        start = html.escape(_format_time(v["start_time"] or ""))
        end = html.escape(_format_time(v["end_time"] or ""))

        venue_js_data.append({
            "id": vid, "name": v_name, "address": v_addr, "city": v_city,
            "lat": v_lat, "lng": v_lng, "phone": v_phone, "phoneFmt": v_phone_fmt,
            "website": v_website, "vibe": v_vibe, "nights": nights_display,
            "start": start, "end": end,
        })

        for night in nights_list:
            if night not in schedule_by_day:
                schedule_by_day[night] = []
            schedule_by_day[night].append({"name": v_name, "vid": vid, "start": start, "end": end})

    # Weekday squares
    day_squares = []
    for day in day_order:
        gigs = schedule_by_day.get(day, [])
        if gigs:
            g = gigs[0]
            day_squares.append(
                f'<div class="day-square has-gig" data-vid="{g["vid"]}">'
                f'<span class="day-label">{day_short[day]}</span>'
                f'<span class="day-time">{g["start"]}</span></div>'
            )
        else:
            day_squares.append(
                f'<div class="day-square">'
                f'<span class="day-label">{day_short[day]}</span>'
                f'<span class="day-time"></span></div>'
            )
    day_squares_html = "\n      ".join(day_squares)

    venues_json = _json.dumps(venue_js_data)

    # Map
    if venue_js_data:
        center_lat = venue_js_data[0]["lat"]
        center_lng = venue_js_data[0]["lng"]
        has_map = True
    else:
        center_lat = 0
        center_lng = 0
        has_map = False

    # KJ city
    kj_city = kj["city"] if "city" in kj.keys() and kj["city"] else ""
    if not kj_city and venue_js_data:
        city_counts: dict[str, int] = {}
        for v in venue_js_data:
            c = v["city"]
            if c:
                city_counts[c] = city_counts.get(c, 0) + 1
        kj_city = max(city_counts, key=lambda k: city_counts[k]) if city_counts else ""
    centered_in = f"Centered in {html.escape(kj_city)}, FL" if kj_city else ""

    venues_count = len(venues)

    # Private-hire banner. Self-reported via the app; it is the whole reason
    # the hire pages exist, so it gets the top of the services section and a
    # tel: CTA rather than being buried in the bio.
    kj_keys = set(kj.keys())
    available_for_hire = bool(kj["available_for_hire"]) if "available_for_hire" in kj_keys else False
    hire_note = (kj["hire_note"] if "hire_note" in kj_keys else None) or ""
    hire_html = ""
    if available_for_hire:
        note_esc = html.escape(hire_note)
        hire_html = f"""
    <div class="service hire">
      <h3>Available for Private Hire</h3>
      <p>{note_esc or 'Book this host for weddings, parties, and corporate events. Full karaoke setup, thousands of songs, and a host who runs the room.'}</p>
      {f'<p><a class="hire-cta" href="tel:{html.escape(kj_phone)}">Call {html.escape(kj_phone_fmt)}</a></p>' if kj_phone else ''}
    </div>"""

    services_html = f"""{hire_html}
    <div class="service">
      <h3>Live Karaoke Hosting</h3>
      <p>Professional karaoke hosting at {venues_count} venue{'s' if venues_count != 1 else ''}. Full song catalog, sound equipment setup, and crowd engagement.</p>
    </div>
    <div class="service">
      <h3>Song Suggestions</h3>
      <p>Singers get personalized song recommendations matched to their vocal range and style through TheHopper app.</p>
    </div>
    <div class="service">
      <h3>Premium Slots</h3>
      <p>Reserve a preferred singing time slot in the rotation. A community-focused feature that supports the venue and the KJ while keeping the night flowing.</p>
    </div>"""

    map_script = (
        f'<script src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_KEY}&callback=initMap" async defer></script>'
        if has_map else ''
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{biz_esc} &mdash; karaoke</title>
  <style>
    :root {{
      --bg: #f5f7fa;
      --header-bg: #e8eef5;
      --header-text: #1a3a5c;
      --panel: #ffffff;
      --border: #d4dde6;
      --text: #2a2a3e;
      --dim: #6a7080;
      --mute: #9aa0ab;
      --blue: #2a5c8a;
      --blue-light: #3a7ab5;
      --highlight: #4a90d9;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, system-ui, "Segoe UI", roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }}

    /* full-width light header */
    .site-header {{
      background: var(--header-bg);
      border-bottom: 1px solid var(--border);
      padding: 0.5rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: baseline;
    }}
    .brand {{
      font-family: "courier new", courier, monospace;
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--blue);
      letter-spacing: 0.02em;
      text-transform: lowercase;
    }}
    .brand a {{ color: var(--blue); text-decoration: none; }}
    .brand-tag {{
      color: var(--mute);
      font-size: 0.72rem;
      text-transform: lowercase;
    }}

    /* hero section — taller, two-column */
    .hero {{
      background: var(--header-bg);
      padding: 2.5rem 2rem 2rem;
      display: grid;
      grid-template-columns: 1fr 320px;
      gap: 2rem;
      align-items: start;
    }}
    .hero-left {{
      max-width: 560px;
    }}
    .hero h1 {{
      font-size: 2.4rem;
      font-weight: 800;
      color: var(--header-text);
      letter-spacing: -0.03em;
      margin-bottom: 0.3rem;
    }}
    .hero .phone {{
      color: var(--blue);
      font-size: 1.05rem;
      font-weight: 600;
      margin-bottom: 0.8rem;
    }}
    .hero .phone a {{
      color: var(--blue);
      text-decoration: none;
    }}
    .hero .tagline {{
      color: var(--dim);
      font-size: 0.98rem;
      margin-bottom: 0.5rem;
    }}
    .hero .centered-in {{
      color: var(--blue-light);
      font-size: 0.88rem;
      font-weight: 600;
      margin-bottom: 1.2rem;
    }}

    /* weekday squares */
    .weekday-strip {{
      display: flex;
      gap: 6px;
      margin-top: 1rem;
    }}
    .day-square {{
      flex: 1;
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.6rem 0.3rem;
      text-align: center;
      display: flex;
      flex-direction: column;
      gap: 4px;
      cursor: default;
      transition: border-color 0.15s, box-shadow 0.15s;
    }}
    .day-square.has-gig {{
      cursor: pointer;
      border-color: var(--blue-light);
    }}
    .day-square.has-gig:hover {{
      border-color: var(--highlight);
      box-shadow: 0 2px 8px rgba(74, 144, 217, 0.2);
    }}
    .day-square.active {{
      border-color: var(--highlight);
      background: rgba(74, 144, 217, 0.08);
      box-shadow: 0 0 0 2px var(--highlight);
    }}
    .day-label {{
      font-size: 0.72rem;
      font-weight: 700;
      color: var(--header-text);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .day-time {{
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--blue-light);
    }}
    .day-square:not(.has-gig) .day-time {{
      color: transparent;
    }}

    /* map in header right side */
    .hero-right {{
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }}
    .map-container {{
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
      height: 260px;
      background: var(--panel);
    }}
    .map-container #map {{ width: 100%; height: 100%; }}
    .no-map {{
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: var(--mute);
      font-size: 0.85rem;
    }}
    .venue-capsule {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.7rem 1rem;
      font-size: 0.88rem;
    }}
    .venue-capsule .vc-name {{
      font-weight: 700;
      color: var(--header-text);
      font-size: 0.95rem;
    }}
    .venue-capsule .vc-addr {{
      color: var(--dim);
      font-size: 0.82rem;
      margin-top: 0.15rem;
    }}
    .venue-capsule .vc-sched {{
      color: var(--blue-light);
      font-size: 0.82rem;
      margin-top: 0.2rem;
    }}

    /* content area */
    .wrap {{ max-width: 900px; margin: 0 auto; padding: 0 2rem 4rem; }}
    .section {{ margin-top: 2.5rem; }}
    .section-title {{
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--mute);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 0.8rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.4rem;
    }}

    /* services */
    .services-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }}
    .service {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.1rem 1.3rem;
    }}
    .service.hire {{
      border-color: var(--blue);
      border-width: 2px;
    }}
    .hire-cta {{
      display: inline-block;
      margin-top: 0.4rem;
      padding: 0.45rem 1rem;
      background: var(--blue);
      color: #fff;
      border-radius: 999px;
      font-weight: 700;
      font-size: 0.9rem;
      text-decoration: none;
    }}
    .service h3 {{
      font-size: 1rem;
      font-weight: 700;
      color: var(--blue);
      margin-bottom: 0.3rem;
    }}
    .service p {{
      color: var(--dim);
      font-size: 0.88rem;
    }}

    .site-footer {{
      margin-top: 2.5rem;
      padding-top: 1.2rem;
      border-top: 1px solid var(--border);
    }}
    .site-footer p {{
      color: var(--mute);
      font-size: 0.8rem;
      margin-bottom: 0.3rem;
    }}
    .site-footer .powered a {{ color: var(--blue); text-decoration: none; }}

    @media (max-width: 640px) {{
      .hero {{
        grid-template-columns: 1fr;
        padding: 1.5rem 1.5rem 1.5rem;
      }}
      .map-container {{ height: 200px; }}
      .hero h1 {{ font-size: 1.8rem; }}
      .weekday-strip {{ flex-wrap: wrap; }}
      .day-square {{ min-width: calc(50% - 3px); }}
    }}
  </style>
</head>
<body>

  <div class="site-header">
    <div class="brand"><a href="https://karaokespot.us">karaokespot.us</a></div>
    <div class="brand-tag">karaoke worldwide</div>
  </div>

  <div class="hero">
    <div class="hero-left">
      <h1>{biz_esc}</h1>
      {f'<div class="phone"><a href="tel:{html.escape(kj_phone)}">{html.escape(kj_phone_fmt)}</a></div>' if kj_phone else ''}
      <p class="tagline">{bio}</p>
      {f'<p class="centered-in">{centered_in}</p>' if centered_in else ''}
      <div class="weekday-strip">
      {day_squares_html}
      </div>
    </div>
    <div class="hero-right">
      <div class="map-container" id="map-container">
        {'<div id="map"></div>' if has_map else '<div class="no-map">map unavailable</div>'}
      </div>
      <div class="venue-capsule" id="venue-capsule">
        <div class="vc-name">Tap a day to see venue</div>
      </div>
    </div>
  </div>

  <div class="wrap">
    <div class="section">
      <div class="section-title">Services</div>
      <div class="services-grid">
        {services_html}
      </div>
    </div>

    <div class="site-footer">
      <p>{biz_esc} &middot; professional karaoke host</p>
      <p class="powered">Powered by <a href="https://karaokespot.us">karaokespot.us</a> &middot; Book through <a href="https://thehopper.alchemycreativelounge.com">TheHopper</a></p>
    </div>
  </div>

  <script>
    var venues = {venues_json};
    var mapKey = "{GOOGLE_MAPS_KEY}";
    var centerLat = {center_lat};
    var centerLng = {center_lng};
    var map = null;
    var markers = {{}};
    var activeVenueId = null;

    function initMap() {{
      map = new google.maps.Map(document.getElementById('map'), {{
        center: {{ lat: centerLat, lng: centerLng }},
        zoom: 11,
        streetViewControl: false,
        mapTypeControl: false,
        fullscreenControl: false,
        styles: [
          {{ elementType: "geometry", stylers: [{{ color: "#e8eef5" }}] }},
          {{ elementType: "labels.text.fill", stylers: [{{ color: "#6a7080" }}] }},
          {{ featureType: "road", elementType: "geometry", stylers: [{{ color: "#ffffff" }}] }},
          {{ featureType: "water", elementType: "geometry", stylers: [{{ color: "#c5d5e8" }}] }},
          {{ featureType: "poi", elementType: "geometry", stylers: [{{ color: "#e0e8f0" }}] }}
        ]
      }});

      venues.forEach(function(v) {{
        var marker = new google.maps.Marker({{
          position: {{ lat: v.lat, lng: v.lng }},
          map: map,
          title: v.name
        }});
        marker.addListener('click', function() {{ selectVenue(v.id); }});
        markers[v.id] = marker;
      }});
    }}

    function selectVenue(id) {{
      var v = venues.find(function(x) {{ return x.id === id; }});
      if (!v) return;
      activeVenueId = id;

      // Highlight day squares that have this venue
      document.querySelectorAll('.day-square.has-gig').forEach(function(sq) {{
        sq.classList.toggle('active', parseInt(sq.dataset.vid) === id);
      }});

      // Update capsule
      var capsule = document.getElementById('venue-capsule');
      capsule.innerHTML = '<div class="vc-name">' + v.name + '</div>' +
        '<div class="vc-addr">' + v.address + ', ' + v.city + '</div>' +
        '<div class="vc-sched">' + v.nights + ' &middot; ' + v.start + (v.end ? '&ndash;' + v.end : '') + '</div>';

      // Pan map
      if (map) {{
        map.panTo({{ lat: v.lat, lng: v.lng }});
        map.setZoom(15);
      }}

      // Bounce marker
      if (markers[id]) {{
        markers[id].setAnimation(google.maps.Animation.BOUNCE);
        setTimeout(function() {{ markers[id].setAnimation(null); }}, 1400);
      }}
    }}

    // Wire up day square clicks
    document.addEventListener('DOMContentLoaded', function() {{
      document.querySelectorAll('.day-square.has-gig').forEach(function(sq) {{
        sq.addEventListener('click', function() {{
          var vid = parseInt(sq.dataset.vid);
          if (vid) selectVenue(vid);
        }});
      }});
    }});
  </script>
  {map_script}

</body>
</html>"""
