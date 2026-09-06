#!/usr/bin/env python3
"""
Scrape FindKaraoke.net for Florida karaoke venue schedules.
Extract: venue name, address, city, karaoke night(s), start time, end time.
Match against fl_liquor_licenses table and update karaoke fields.
Save unmatched to findkaraoke_unmatched.json.
Also geocode venues in karaokelocations_unmatched.json using Nominatim.
"""
import requests
from bs4 import BeautifulSoup
import json, time, re, sqlite3, urllib.parse
from difflib import SequenceMatcher

DB_PATH = '/home/openclaw/projects/thehopper/backend/thehopper.db'
DATA_DIR = '/home/openclaw/projects/thehopper/data'
BASE_URL = 'https://findkaraoke.net'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}

# ─── Florida cities from FindKaraoke.net ───
FL_CITIES = [
    'boca-raton','boynton-beach','bradenton','cape-coral','coral-gables',
    'coral-springs','daytona-beach','deltona','fort-lauderdale','fort-myers',
    'gainesville','gulfport','hallandale-beach','hialeah','hollywood',
    'jacksonville','jacksonville-beach','key-west','lakeland','melbourne',
    'miami','miami-beach','mount-dora','naples','new-smyrna-beach',
    'north-fort-myers','ocala','orlando','palm-bay','palm-beach-gardens',
    'panama-city-beach','pensacola','saint-petersburg','sanford','sarasota',
    'st-petersburg','tallahassee','tampa','temple-terrace','west-palm-beach'
]

DAYS_MAP = {
    'mon': 'Monday', 'monday': 'Monday',
    'tue': 'Tuesday', 'tues': 'Tuesday', 'tuesday': 'Tuesday',
    'wed': 'Wednesday', 'wednesday': 'Wednesday',
    'thu': 'Thursday', 'thur': 'Thursday', 'thurs': 'Thursday', 'thursday': 'Thursday',
    'fri': 'Friday', 'friday': 'Friday',
    'sat': 'Saturday', 'saturday': 'Saturday',
    'sun': 'Sunday', 'sunday': 'Sunday',
}

DAY_ORDER = ['mon','tue','wed','thu','fri','sat','sun']
DAY_FULL = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

def normalize_time(t):
    """Normalize time strings to HH:MM AM/PM format."""
    if not t:
        return ''
    t = t.strip()
    # Already has AM/PM
    if re.search(r'[AP]M', t, re.I):
        t = re.sub(r'(\d)([AP])', r'\1 \2', t, flags=re.I)
        m = re.match(r'(\d{1,2}):?(\d{0,2})\s*([AP]M)', t, re.I)
        if m:
            hour = int(m.group(1))
            minute = m.group(2) if m.group(2) else '00'
            return f"{hour:02d}:{minute} {m.group(3).upper()}"
        return t.upper()
    if ':' in t:
        hour = int(t.split(':')[0])
        return f"{hour:02d}:{t.split(':')[1].split()[0]} PM"
    if t.isdigit():
        hour = int(t)
        return f"{hour:02d}:00 PM"
    return t


def parse_schedule(main_section_text):
    """Parse schedule from the main section text (between city and 'I'm Going')."""
    time_re = r'\d{1,2}[:\.]?\d{0,2}\s*[APap][Mm]'
    schedule = []
    
    # The main section text looks like:
    # "... 4.4 Updated April 28, 2026 Monday, Tuesday, Thursday, Saturday at 10 PM"
    # or "... 4.5 Updated April 28, 2026 Every day at 12 PM"
    # or "... Thursday at 9:30 PM"
    
    patterns = [
        # Range: "Wednesday–Saturday at 6 PM" (en-dash, em-dash, or hyphen)
        rf'((?:Mon|Tues?|Wed(?:nes)?|Thurs?|Fri|Sat(?:ur)?|Sun)(?:day)?s?)\s*[–\-–—]\s*((?:Mon|Tues?|Wed(?:nes)?|Thurs?|Fri|Sat(?:ur)?|Sun)(?:day)?s?)\s+at\s+({time_re})',
        # "Every day at 6 PM"
        rf'Every\s*day\s+at\s+({time_re})',
        # Comma-separated: "Monday, Tuesday, Thursday, Saturday at 10 PM"
        rf'((?:(?:Mon|Tues?|Wed(?:nes)?|Thurs?|Fri|Sat(?:ur)?|Sun)(?:day)?s?\s*,?\s*(?:and\s+)?)+)\s+at\s+({time_re})',
        # Single day: "Monday at 9 PM"
        rf'((?:Mon|Tues?|Wed(?:nes)?|Thurs?|Fri|Sat(?:ur)?|Sun)(?:day)?s?)\s+at\s+({time_re})',
    ]
    
    for i, pat in enumerate(patterns):
        m = re.search(pat, main_section_text, re.I)
        if not m:
            continue
        
        if i == 0:  # Range
            start_day = m.group(1).lower()[:3]
            end_day = m.group(2).lower()[:3]
            start_time = m.group(3)
            try:
                si = next(idx for idx, d in enumerate(DAY_ORDER) if d.startswith(start_day))
                ei = next(idx for idx, d in enumerate(DAY_ORDER) if d.startswith(end_day))
                if si <= ei:
                    days_in_range = DAY_ORDER[si:ei+1]
                else:
                    days_in_range = DAY_ORDER[si:] + DAY_ORDER[:ei+1]
                for d in days_in_range:
                    schedule.append({'day': DAYS_MAP[d], 'start_time': normalize_time(start_time), 'end_time': ''})
            except StopIteration:
                pass
        elif i == 1:  # Every day
            start_time = m.group(1)
            for day_full in DAY_FULL:
                schedule.append({'day': day_full, 'start_time': normalize_time(start_time), 'end_time': ''})
        elif i == 2:  # Comma-separated
            days_str = m.group(1)
            start_time = m.group(2)
            day_parts = re.split(r',|\sand\s', days_str)
            for dp in day_parts:
                dp = dp.strip().lower()[:3]
                if dp in DAYS_MAP:
                    schedule.append({'day': DAYS_MAP[dp], 'start_time': normalize_time(start_time), 'end_time': ''})
        elif i == 3:  # Single day
            day_str = m.group(1).lower()[:3]
            start_time = m.group(2)
            if day_str in DAYS_MAP:
                schedule.append({'day': DAYS_MAP[day_str], 'start_time': normalize_time(start_time), 'end_time': ''})
        break  # Only use first matching pattern
    
    # Deduplicate by day
    seen = set()
    deduped = []
    for s in schedule:
        if s['day'] not in seen:
            seen.add(s['day'])
            deduped.append(s)
    
    return deduped


def extract_venue_name(soup, city_title):
    """Extract clean venue name from the page."""
    h1 = soup.find('h1')
    if not h1:
        return ''
    h1_text = h1.get_text(strip=True)
    
    # H1 format: "Karaoke at{VenueName}{City}, FL"
    # Remove "Karaoke at" prefix
    name = re.sub(r'^Karaoke at', '', h1_text)
    # Remove city suffix: "{City}, FL" at the end
    # city_title is like "Miami" or "Saint Petersburg" or "Mount Dora"
    name = re.sub(rf'{re.escape(city_title)},\s*FL$', '', name)
    # Also handle city with spaces/hyphens variations
    name = re.sub(r',\s*FL$', '', name)
    
    return name.strip()


def extract_address(soup):
    """Extract address from venue detail page."""
    # Look for Google Maps link
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'maps.google' in href or 'maps.app' in href:
            text = a.get_text(strip=True)
            if re.match(r'^\d+\s+', text):
                return text
            m = re.search(r'[?&]q=([^&]+)', href)
            if m:
                addr = urllib.parse.unquote(m.group(1))
                if ',' in addr:
                    parts = addr.split(',')
                    for p in parts:
                        if re.match(r'^\s*\d+\s+', p):
                            return p.strip()
                return addr
    
    # Look for address label pattern in text
    page_text = soup.get_text(separator='\n', strip=True)
    m = re.search(r'Address\s*\n?\s*(\d+\s+[^\n,]+(?:,[^\n]+)?)', page_text)
    if m:
        return m.group(1).strip()
    
    for line in page_text.split('\n'):
        line = line.strip()
        if re.match(r'^\d+\s+[A-Z]', line) and len(line) < 200 and ('FL' in line or any(kw in line.lower() for kw in ['st','ave','rd','dr','blvd','ln','way','ct','hwy'])):
            return line
    
    return ''


def extract_phone(soup):
    """Extract phone number from venue detail page."""
    page_text = soup.get_text(separator='\n', strip=True)
    m = re.search(r'Phone\s*\n?\s*(\(\d{3}\)\s*\d{3}[-.]?\d{4})', page_text)
    if m:
        return m.group(1)
    m = re.search(r'(\(\d{3}\)\s*\d{3}[-.]?\d{4})', page_text)
    if m:
        return m.group(1)
    return ''


def extract_about(soup):
    """Extract about/description text."""
    page_text = soup.get_text(separator='\n', strip=True)
    m = re.search(r'About\s*\n\s*(.+?)(?:\n\d+\s+[A-Z]|\nGet Directions|\nVisit Website|\nView on Google)', page_text, re.S)
    if m:
        return m.group(1).strip()
    return ''


def extract_main_section(soup):
    """Extract the main content section between the city name and 'I'm Going'."""
    page_text = soup.get_text(separator=' ', strip=True)
    
    # Find the section after "Updated <date>" and before "I'm Going"
    # This is where the schedule line appears
    updated_match = re.search(r'Updated\s+\w+\s+\d+,\s+\d{4}', page_text)
    going_match = re.search(r"I'm Going", page_text)
    
    if updated_match and going_match:
        section = page_text[updated_match.end():going_match.start()].strip()
        return section
    
    # Fallback: between city, FL and I'm Going
    city_match = re.search(r',\s*FL\s+', page_text)
    if city_match and going_match:
        return page_text[city_match.end():going_match.start()].strip()
    
    return ''


def normalize_name(name):
    """Normalize venue name for matching."""
    name = name.lower().strip()
    for suffix in [' bar', ' lounge', ' pub', ' grill', ' restaurant', ' & grill',
                   ' and grill', ' tavern', ' saloon', ' sports bar', ' karaoke',
                   ' bar and grille', ' bar & grille', ' bar and grill',
                   ' inn', ' club', ' inc', ' llc', ' the']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'[^a-z0-9\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def name_similarity(a, b):
    """Calculate similarity between two normalized names."""
    na = normalize_name(a)
    nb = normalize_name(b)
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


def normalize_city(city):
    """Normalize city name for comparison."""
    city = city.lower().strip().replace('-', ' ')
    city = re.sub(r'[^a-z\s]', '', city)
    city = re.sub(r'\s+', ' ', city).strip()
    return city


def scrape_all_venues():
    """Scrape all Florida venues from FindKaraoke.net."""
    all_venues = []
    
    for city in FL_CITIES:
        city_title = city.replace('-', ' ').title()
        # Special cases
        if city == 'saint-petersburg':
            city_title = 'Saint Petersburg'
        
        url = f'{BASE_URL}/{city}'
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            venue_links = []
            seen_names = set()
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/venues/' in href:
                    name = a.get_text(strip=True)
                    if name and name not in seen_names:
                        venue_links.append((href, name))
                        seen_names.add(name)
            
            for href, name in venue_links:
                detail_url = f'{BASE_URL}{href}'
                try:
                    r2 = requests.get(detail_url, headers=HEADERS, timeout=20)
                    soup2 = BeautifulSoup(r2.text, 'html.parser')
                    
                    venue_name = extract_venue_name(soup2, city_title)
                    if not venue_name:
                        venue_name = name
                    
                    address = extract_address(soup2)
                    phone = extract_phone(soup2)
                    about = extract_about(soup2)
                    
                    main_section = extract_main_section(soup2)
                    schedule = parse_schedule(main_section)
                    
                    nights = ', '.join(sorted(set(s['day'] for s in schedule)))
                    start_times = ', '.join(sorted(set(s['start_time'] for s in schedule if s['start_time'])))
                    end_times = ', '.join(sorted(set(s['end_time'] for s in schedule if s['end_time'])))
                    
                    venue_data = {
                        'venue_name': venue_name,
                        'address': address,
                        'city': city_title,
                        'city_raw': city.replace('-', ' '),
                        'phone': phone,
                        'about': about,
                        'schedule': schedule,
                        'karaoke_nights': nights,
                        'karaoke_start_time': start_times,
                        'karaoke_end_time': end_times,
                        'detail_url': href,
                        'source': 'findkaraoke.net'
                    }
                    all_venues.append(venue_data)
                    print(f'    ✓ {venue_name}: {nights or "no schedule"} | {start_times or "no time"}')
                    
                except Exception as e:
                    print(f'    ✗ ERROR {name}: {e}')
                    all_venues.append({
                        'venue_name': name,
                        'address': '',
                        'city': city_title,
                        'city_raw': city.replace('-', ' '),
                        'phone': '',
                        'about': '',
                        'schedule': [],
                        'karaoke_nights': '',
                        'karaoke_start_time': '',
                        'karaoke_end_time': '',
                        'detail_url': href,
                        'source': 'findkaraoke.net',
                        'error': str(e)
                    })
                
                time.sleep(0.3)
            
        except Exception as e:
            print(f'  ERROR fetching city {city}: {e}')
    
    return all_venues


def match_and_update_db(venues):
    """Match scraped venues against fl_liquor_licenses and update DB."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # First, clear any previously set karaoke_nights from our prior run
    # to avoid stale data (only for records we're about to update)
    
    c.execute('SELECT id, dba_name, business_city, business_address FROM fl_liquor_licenses')
    licenses = c.fetchall()
    print(f'\nLoaded {len(licenses)} liquor licenses from DB')
    
    matched = []
    unmatched = []
    
    for venue in venues:
        best_match = None
        best_score = 0
        venue_city_norm = normalize_city(venue['city_raw'])
        
        for lic_id, dba_name, lic_city, lic_address in licenses:
            if not dba_name:
                continue
            lic_city_norm = normalize_city(lic_city or '')
            
            city_match = (venue_city_norm == lic_city_norm or 
                         venue_city_norm in lic_city_norm or 
                         lic_city_norm in venue_city_norm)
            
            if not city_match:
                continue
            
            score = name_similarity(venue['venue_name'], dba_name)
            
            if venue['address'] and lic_address:
                addr_score = SequenceMatcher(None, 
                    venue['address'].lower(), 
                    lic_address.lower()).ratio()
                if addr_score > 0.5:
                    score = min(1.0, score + 0.1)
            
            if score > best_score:
                best_score = score
                best_match = lic_id
        
        if best_match and best_score >= 0.6:
            venue['matched_license_id'] = best_match
            venue['match_score'] = round(best_score, 3)
            matched.append(venue)
            
            c.execute('''UPDATE fl_liquor_licenses 
                        SET karaoke_nights = ?, 
                            karaoke_start_time = ?, 
                            karaoke_end_time = ?,
                            has_karaoke = 1,
                            updated_at = datetime('now')
                        WHERE id = ?''',
                     (venue['karaoke_nights'], 
                      venue['karaoke_start_time'], 
                      venue['karaoke_end_time'],
                      best_match))
            print(f'  ✓ MATCHED: {venue["venue_name"]} -> license #{best_match} (score: {best_score:.3f})')
        else:
            venue['matched_license_id'] = None
            venue['match_score'] = round(best_score, 3) if best_match else 0
            unmatched.append(venue)
            if best_match:
                print(f'  ✗ NO MATCH: {venue["venue_name"]} (best: {best_score:.3f})')
            else:
                print(f'  ✗ NO MATCH: {venue["venue_name"]} (no candidate)')
    
    conn.commit()
    conn.close()
    
    return matched, unmatched


def geocode_nominatim(address, city):
    """Geocode an address using Nominatim API (rate limited to 1 req/sec)."""
    query = f"{address}, {city}, FL" if address and city else (f"{address}, FL" if address else f"{city}, FL")
    params = {
        'q': query,
        'format': 'json',
        'limit': 1,
        'countrycodes': 'us',
        'addressdetails': 1
    }
    headers = {'User-Agent': 'karaokespot-us/1.0'}
    
    try:
        r = requests.get('https://nominatim.openstreetmap.org/search', 
                        params=params, headers=headers, timeout=15)
        if r.status_code == 200 and r.json():
            result = r.json()[0]
            return float(result['lat']), float(result['lon'])
    except Exception as e:
        print(f'    Geocode error for "{query}": {e}')
    
    return None, None


def geocode_unmatched_venues():
    """Geocode the 22 venues in karaokelocations_unmatched.json."""
    input_path = f'{DATA_DIR}/karaokelocations_unmatched.json'
    output_path = f'{DATA_DIR}/karaokelocations_geocoded.json'
    
    with open(input_path) as f:
        venues = json.load(f)
    
    print(f'\nGeocoding {len(venues)} venues with Nominatim...')
    
    results = []
    for i, venue in enumerate(venues):
        address = venue.get('address', '')
        city = venue.get('city', '')
        name = venue.get('name', '')
        
        print(f'  [{i+1}/{len(venues)}] {name} ({city})')
        
        lat, lng = None, None
        
        if address:
            lat, lng = geocode_nominatim(address, city)
        
        if lat is None and name:
            lat, lng = geocode_nominatim(name, city)
        
        if lat is None and city:
            lat, lng = geocode_nominatim('', city)
        
        venue['lat'] = lat
        venue['lng'] = lng
        venue['geocoded'] = lat is not None
        results.append(venue)
        
        if lat:
            print(f'    → {lat}, {lng}')
        else:
            print(f'    → FAILED')
        
        time.sleep(1.1)
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    geocoded_count = sum(1 for v in results if v.get('lat'))
    print(f'\nGeocoded: {geocoded_count}/{len(results)}')
    
    # Update DB for matched venues
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('SELECT id, dba_name, business_city FROM fl_liquor_licenses WHERE business_state = "FL"')
    licenses = c.fetchall()
    
    updated = 0
    for venue in results:
        if venue.get('lat') is None:
            continue
        
        best_match = None
        best_score = 0
        venue_city_norm = normalize_city(venue.get('city', ''))
        
        for lic_id, dba_name, lic_city in licenses:
            if not dba_name:
                continue
            lic_city_norm = normalize_city(lic_city or '')
            if venue_city_norm != lic_city_norm and venue_city_norm not in lic_city_norm and lic_city_norm not in venue_city_norm:
                continue
            score = name_similarity(venue['name'], dba_name)
            if score > best_score:
                best_score = score
                best_match = lic_id
        
        if best_match and best_score >= 0.6:
            c.execute('''UPDATE fl_liquor_licenses 
                        SET lat = ?, lng = ?, geocoded = 1, 
                            has_karaoke = 1,
                            updated_at = datetime('now')
                        WHERE id = ?''',
                     (venue['lat'], venue['lng'], best_match))
            updated += 1
            print(f'  ✓ DB UPDATE: {venue["name"]} -> license #{best_match} (lat/lng)')
    
    conn.commit()
    conn.close()
    print(f'Updated {updated} DB records with coordinates')
    
    return results


def main():
    print('=' * 60)
    print('FindKaraoke.net Florida Scraper')
    print('=' * 60)
    
    # Step 1: Scrape all venues
    print('\n--- Step 1: Scraping FindKaraoke.net ---')
    venues = scrape_all_venues()
    print(f'\nTotal venues scraped: {len(venues)}')
    with_schedule = sum(1 for v in venues if v['karaoke_nights'])
    print(f'Venues with schedule: {with_schedule}')
    
    raw_path = f'{DATA_DIR}/findkaraoke_fl_raw.json'
    with open(raw_path, 'w') as f:
        json.dump(venues, f, indent=2)
    print(f'Raw data saved to {raw_path}')
    
    # Step 2: Match against DB and update
    print('\n--- Step 2: Matching against fl_liquor_licenses ---')
    matched, unmatched = match_and_update_db(venues)
    print(f'\nMatched: {len(matched)} | Unmatched: {len(unmatched)}')
    
    unmatched_path = f'{DATA_DIR}/findkaraoke_unmatched.json'
    with open(unmatched_path, 'w') as f:
        json.dump(unmatched, f, indent=2)
    print(f'Unmatched saved to {unmatched_path}')
    
    # Step 3: Geocode
    print('\n--- Step 3: Geocoding karaokelocations_unmatched.json ---')
    geocoded = geocode_unmatched_venues()
    
    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'Total venues scraped from FindKaraoke.net: {len(venues)}')
    print(f'  - With schedule data: {with_schedule}')
    print(f'  - Without schedule: {len(venues) - with_schedule}')
    print(f'Matched to liquor licenses: {len(matched)}')
    print(f'Unmatched (saved to JSON): {len(unmatched)}')
    print(f'Geocoded venues: {sum(1 for v in geocoded if v.get("lat"))}/{len(geocoded)}')
    print(f'\nFiles created/modified:')
    print(f'  - {raw_path} (raw scraped data)')
    print(f'  - {unmatched_path} (unmatched venues)')
    print(f'  - {DATA_DIR}/karaokelocations_geocoded.json (geocoded venues)')
    print(f'  - {DB_PATH} (updated karaoke fields in fl_liquor_licenses)')


if __name__ == '__main__':
    main()
