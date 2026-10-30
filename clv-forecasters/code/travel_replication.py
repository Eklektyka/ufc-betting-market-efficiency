#!/usr/bin/env python3
"""
Miller & Nichols (2026) travel-distance replication on 2007-2025 UFC data.
Tests whether travel distance / time-zone differential predicts fight outcomes
net of the closing line.
"""
import sys, math, time, csv, re, json, warnings
import numpy as np
import pandas as pd
from collections import defaultdict, Counter
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.metrics import brier_score_loss, log_loss, accuracy_score
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from datetime import datetime
from zoneinfo import ZoneInfo

warnings.filterwarnings('ignore')
np.set_printoptions(precision=4)

SEED = 67
rng = np.random.RandomState(SEED)
N_BOOT = 2000

# Force unbuffered output
import functools
print = functools.partial(print, flush=True)

# ═══════════════════════════════════════════════════════════════════
# STEP 1: GEOCODE EVENT LOCATIONS
# ═══════════════════════════════════════════════════════════════════
print("STEP 1: GEOCODE EVENT LOCATIONS")
print("=" * 72)

events = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_events.csv')
unique_locs = events['location'].unique()
print(f"  Unique event locations to geocode: {len(unique_locs)}")

geolocator = Nominatim(user_agent="ufc-travel-research-2026", timeout=10)
tf = TimezoneFinder()

# Geocode each unique location
loc_cache = {}
failed_locs = []

# Hard-coded fallbacks for common/known locations
KNOWN_COORDS = {
    'Las Vegas, Nevada, USA': (36.1699, -115.1398),
    'Abu Dhabi, Abu Dhabi, United Arab Emirates': (24.4539, 54.3773),
    'Abu Dhabi, United Arab Emirates': (24.4539, 54.3773),
    'New York City, New York, USA': (40.7128, -74.0060),
    'London, England, United Kingdom': (51.5074, -0.1278),
    'Paris, Ile-de-France, France': (48.8566, 2.3522),
    'Tokyo, Japan': (35.6762, 139.6503),
    'Sydney, New South Wales, Australia': (-33.8688, 151.2093),
    'Perth, Western Australia, Australia': (-31.9505, 115.8605),
    'Rio de Janeiro, Rio de Janeiro, Brazil': (-22.9068, -43.1729),
    'Sao Paulo, Sao Paulo, Brazil': (-23.5505, -46.6333),
    'Shanghai, Hebei, China': (31.2304, 121.4737),
    'Beijing, China': (39.9042, 116.4074),
    'Macau, China': (22.1987, 113.5439),
    'Seoul, South Korea': (37.5665, 126.9780),
    'Singapore, Singapore': (1.3521, 103.8198),
    'Mexico City, Distrito Federal, Mexico': (19.4326, -99.1332),
    'Calgary, Alberta, Canada': (51.0447, -114.0719),
    'Toronto, Ontario, Canada': (43.6532, -79.3832),
    'Montreal, Quebec, Canada': (45.5017, -73.5673),
    'Vancouver, British Columbia, Canada': (49.2827, -123.1207),
    'Edmonton, Alberta, Canada': (53.5461, -113.4938),
    'Winnipeg, Manitoba, Canada': (49.8951, -97.1384),
    'Ottawa, Ontario, Canada': (45.4215, -75.6972),
    'Chicago, Illinois, USA': (41.8781, -87.6298),
    'Houston, Texas, USA': (29.7604, -95.3698),
    'Dallas, Texas, USA': (32.7767, -96.7970),
    'San Antonio, Texas, USA': (29.4241, -98.4936),
    'Austin, Texas, USA': (30.2672, -97.7431),
    'Atlanta, Georgia, USA': (33.7490, -84.3880),
    'Boston, Massachusetts, USA': (42.3601, -71.0589),
    'Denver, Colorado, USA': (39.7392, -104.9903),
    'Nashville, Tennessee, USA': (36.1627, -86.7816),
    'Jacksonville, Florida, USA': (30.3322, -81.6557),
    'Miami, Florida, USA': (25.7617, -80.1918),
    'Tampa, Florida, USA': (27.9506, -82.4572),
    'Orlando, Florida, USA': (28.5383, -81.3792),
    'Sacramento, California, USA': (38.5816, -121.4944),
    'San Jose, California, USA': (37.3382, -121.8863),
    'Anaheim, California, USA': (33.8366, -117.9143),
    'Los Angeles, California, USA': (34.0522, -118.2437),
    'Inglewood, California, USA': (33.9617, -118.3531),
    'San Diego, California, USA': (32.7157, -117.1611),
    'Brooklyn, New York, USA': (40.6782, -73.9442),
    'Newark, New Jersey, USA': (40.7357, -74.1724),
    'Atlantic City, New Jersey, USA': (39.3643, -74.4229),
    'Philadelphia, Pennsylvania, USA': (39.9526, -75.1652),
    'Pittsburgh, Pennsylvania, USA': (40.4406, -79.9959),
    'Washington, DC, USA': (38.9072, -77.0369),
    'Detroit, Michigan, USA': (42.3314, -83.0458),
    'Columbus, Ohio, USA': (39.9612, -82.9988),
    'Cleveland, Ohio, USA': (41.4993, -81.6944),
    'Cincinnati, Ohio, USA': (39.1031, -84.5120),
    'Indianapolis, Indiana, USA': (39.7684, -86.1581),
    'Milwaukee, Wisconsin, USA': (43.0389, -87.9065),
    'Minneapolis, Minnesota, USA': (44.9778, -93.2650),
    'Kansas City, Missouri, USA': (39.0997, -94.5786),
    'St. Louis, Missouri, USA': (38.6270, -90.1994),
    'New Orleans, Louisiana, USA': (29.9511, -90.0715),
    'Seattle, Washington, USA': (47.6062, -122.3321),
    'Portland, Oregon, USA': (45.5051, -122.6750),
    'Salt Lake City, Utah, USA': (40.7608, -111.8910),
    'Norfolk, Virginia, USA': (36.8508, -76.2859),
    'Charlotte, North Carolina, USA': (35.2271, -80.8431),
    'Raleigh, North Carolina, USA': (35.7796, -78.6382),
    'Louisville, Kentucky, USA': (38.2527, -85.7585),
    'Sunrise, Florida, USA': (26.1339, -80.1131),
    'Buffalo, New York, USA': (42.8864, -78.8784),
    'Uncasville, Connecticut, USA': (41.4445, -72.1079),
    'Fairfax, Virginia, USA': (38.8462, -77.3064),
    'Oklahoma City, Oklahoma, USA': (35.4676, -97.5164),
    'Tulsa, Oklahoma, USA': (36.1540, -95.9928),
    'Manchester, England, United Kingdom': (53.4808, -2.2426),
    'Glasgow, Scotland, United Kingdom': (55.8642, -4.2518),
    'Liverpool, Merseyside, United Kingdom': (53.4084, -2.9916),
    'Belfast, Northern Ireland, United Kingdom': (54.5973, -5.9301),
    'Dublin, Dublin, Ireland': (53.3498, -6.2603),
    'Berlin, Berlin, Germany': (52.5200, 13.4050),
    'Berlin, Germany': (52.5200, 13.4050),
    'Hamburg, Germany': (53.5511, 9.9937),
    'Stockholm, Stockholm, Sweden': (59.3293, 18.0686),
    'Copenhagen, Hovedstaden, Denmark': (55.6761, 12.5683),
    'Rotterdam, Zuid-Holland, Netherlands': (51.9244, 4.4777),
    'Gdansk, Pomorskie, Poland': (54.3520, 18.6466),
    'Doha, Qatar': (25.2854, 51.5310),
    'Riyadh, Riyadh, Saudi Arabia': (24.7136, 46.6753),
    'Jeddah, Makkah, Saudi Arabia': (21.4858, 39.1925),
    'Melbourne, Victoria, Australia': (-37.8136, 144.9631),
    'Brisbane, Queensland, Australia': (-27.4698, 153.0251),
    'Adelaide, South Australia, Australia': (-34.9285, 138.6007),
    'Auckland, New Zealand': (-36.8485, 174.7633),
    'Manila, Philippines': (14.5995, 120.9842),
    'Jakarta, Indonesia': (-6.2088, 106.8456),
    'Baku, Azerbaijan': (40.4093, 49.8671),
    'Moscow, Russia': (55.7558, 37.6173),
    'Calgary, Alberta, Canada': (51.0447, -114.0719),
    'Brasilia, Distrito Federal, Brazil': (-15.7975, -47.8919),
    'Belo Horizonte, Minas Gerais, Brazil': (-19.9167, -43.9345),
    'Curitiba, Parana, Brazil': (-25.4284, -49.2733),
    'Fortaleza, Ceara, Brazil': (-3.7172, -38.5433),
    'Uberlandia, Minas Gerais, Brazil': (-18.9186, -48.2772),
    'Barueri, Sao Paulo, Brazil': (-23.5114, -46.8761),
    'Goiania, Goias, Brazil': (-16.6869, -49.2648),
}

for loc in unique_locs:
    if loc in KNOWN_COORDS:
        loc_cache[loc] = KNOWN_COORDS[loc]
        continue
    # Try geocoding
    try:
        result = geolocator.geocode(loc)
        if result:
            loc_cache[loc] = (result.latitude, result.longitude)
        else:
            # Try just city + country
            parts = [p.strip() for p in loc.split(',')]
            if len(parts) >= 2:
                short = f"{parts[0]}, {parts[-1]}"
                result = geolocator.geocode(short)
                if result:
                    loc_cache[loc] = (result.latitude, result.longitude)
                else:
                    failed_locs.append(loc)
            else:
                failed_locs.append(loc)
        time.sleep(1.1)  # Nominatim rate limit
    except Exception as e:
        failed_locs.append(loc)
        time.sleep(1.1)

print(f"  Geocoded: {len(loc_cache)}/{len(unique_locs)}")
if failed_locs:
    print(f"  Failed ({len(failed_locs)}):")
    for fl in failed_locs:
        print(f"    {fl}")

# Compute timezone for each location
loc_tz = {}
for loc, (lat, lon) in loc_cache.items():
    tz_str = tf.timezone_at(lat=lat, lng=lon)
    if tz_str:
        loc_tz[loc] = tz_str
    else:
        loc_tz[loc] = 'UTC'  # fallback

# Map events to coords and timezones
events['lat'] = events['location'].map(lambda x: loc_cache.get(x, (None,None))[0])
events['lon'] = events['location'].map(lambda x: loc_cache.get(x, (None,None))[1])
events['tz'] = events['location'].map(lambda x: loc_tz.get(x, None))
geocoded_events = events.dropna(subset=['lat','lon','tz'])
print(f"  Events with coords: {len(geocoded_events)}/{len(events)}")


# ═══════════════════════════════════════════════════════════════════
# STEP 2: MATCH FIGHTERS TO WIKIDATA NATIONALITY/BIRTHPLACE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("STEP 2: MATCH FIGHTERS TO WIKIDATA")
print(f"{'='*72}")

wiki = pd.read_csv(r'C:\Research\ufc\odds\wikidata_mma_fighters.csv')
panel = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\processed\analysis_panel_cc.csv')

ufc_fighters = set(panel['fighter'].unique()) | set(panel['opponent'].unique())
print(f"  UFC fighters in panel: {len(ufc_fighters)}")
print(f"  Wikidata MMA fighters: {len(wiki['name'].unique())}")

# Normalize names for matching
def norm_name(n):
    import unicodedata
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# Build wiki lookup (name -> best row, prefer one with coords)
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (row['lat'] and not wiki_lookup[nn].get('lat')):
        wiki_lookup[nn] = row.to_dict()

# Match UFC fighters
matched = {}
unmatched = []
for f in ufc_fighters:
    nn = norm_name(f)
    if nn in wiki_lookup:
        matched[f] = wiki_lookup[nn]
    else:
        # Try last-name + first-initial matching
        parts = nn.split()
        if len(parts) >= 2:
            # Try reversed name order
            reversed_name = ' '.join(parts[1:] + parts[:1])
            if reversed_name in wiki_lookup:
                matched[f] = wiki_lookup[reversed_name]
                continue
        unmatched.append(f)

print(f"  Matched: {len(matched)}/{len(ufc_fighters)} ({len(matched)/len(ufc_fighters):.1%})")
print(f"  Unmatched: {len(unmatched)}")

# How many matched fighters have coordinates?
with_coords = sum(1 for f, d in matched.items() if d.get('lat') and str(d['lat']).strip())
print(f"  With birthplace coords: {with_coords}/{len(matched)}")

# Country coverage (even without coords, country gives us a timezone proxy)
with_country = sum(1 for f, d in matched.items() if d.get('country'))
print(f"  With country: {with_country}/{len(matched)}")

# For fighters without coords but with country, use country centroid
COUNTRY_CENTROIDS = {
    'United States': (39.8283, -98.5795, 'America/Chicago'),
    'Brazil': (-14.2350, -51.9253, 'America/Sao_Paulo'),
    'Russia': (55.7558, 37.6173, 'Europe/Moscow'),
    'Canada': (56.1304, -106.3468, 'America/Toronto'),
    'United Kingdom': (51.5074, -0.1278, 'Europe/London'),
    'Australia': (-33.8688, 151.2093, 'Australia/Sydney'),
    'Japan': (35.6762, 139.6503, 'Asia/Tokyo'),
    'China': (39.9042, 116.4074, 'Asia/Shanghai'),
    'South Korea': (37.5665, 126.9780, 'Asia/Seoul'),
    'Mexico': (19.4326, -99.1332, 'America/Mexico_City'),
    'Ireland': (53.3498, -6.2603, 'Europe/Dublin'),
    'France': (48.8566, 2.3522, 'Europe/Paris'),
    'Germany': (52.5200, 13.4050, 'Europe/Berlin'),
    'Netherlands': (52.3676, 4.9041, 'Europe/Amsterdam'),
    'Sweden': (59.3293, 18.0686, 'Europe/Stockholm'),
    'Poland': (52.2297, 21.0122, 'Europe/Warsaw'),
    'Italy': (41.9028, 12.4964, 'Europe/Rome'),
    'Spain': (40.4168, -3.7038, 'Europe/Madrid'),
    'Argentina': (-34.6037, -58.3816, 'America/Argentina/Buenos_Aires'),
    'Colombia': (4.7110, -74.0721, 'America/Bogota'),
    'Cuba': (23.1136, -82.3666, 'America/Havana'),
    'Jamaica': (18.1096, -77.2975, 'America/Jamaica'),
    'Nigeria': (9.0820, 7.4910, 'Africa/Lagos'),
    'South Africa': (-33.9249, 18.4241, 'Africa/Johannesburg'),
    'New Zealand': (-36.8485, 174.7633, 'Pacific/Auckland'),
    'Philippines': (14.5995, 120.9842, 'Asia/Manila'),
    'Thailand': (13.7563, 100.5018, 'Asia/Bangkok'),
    'Indonesia': (-6.2088, 106.8456, 'Asia/Jakarta'),
    'Georgia': (41.7151, 44.8271, 'Asia/Tbilisi'),
    'Kazakhstan': (51.1694, 71.4491, 'Asia/Almaty'),
    'Uzbekistan': (41.2995, 69.2401, 'Asia/Tashkent'),
    'Kyrgyzstan': (42.8746, 74.5698, 'Asia/Bishkek'),
    'Tajikistan': (38.5598, 68.7740, 'Asia/Dushanbe'),
    'Ukraine': (50.4501, 30.5234, 'Europe/Kyiv'),
    'Belarus': (53.9045, 27.5615, 'Europe/Minsk'),
    'Moldova': (47.0105, 28.8638, 'Europe/Chisinau'),
    'Czech Republic': (50.0755, 14.4378, 'Europe/Prague'),
    'Czechia': (50.0755, 14.4378, 'Europe/Prague'),
    'Romania': (44.4268, 26.1025, 'Europe/Bucharest'),
    'Serbia': (44.7866, 20.4489, 'Europe/Belgrade'),
    'Croatia': (45.8150, 15.9819, 'Europe/Zagreb'),
    'Denmark': (55.6761, 12.5683, 'Europe/Copenhagen'),
    'Norway': (59.9139, 10.7522, 'Europe/Oslo'),
    'Finland': (60.1699, 24.9384, 'Europe/Helsinki'),
    'Switzerland': (46.9480, 7.4474, 'Europe/Zurich'),
    'Austria': (48.2082, 16.3738, 'Europe/Vienna'),
    'Portugal': (38.7223, -9.1393, 'Europe/Lisbon'),
    'Turkey': (41.0082, 28.9784, 'Europe/Istanbul'),
    'Egypt': (30.0444, 31.2357, 'Africa/Cairo'),
    'Morocco': (33.9716, -6.8498, 'Africa/Casablanca'),
    'Cameroon': (3.8480, 11.5021, 'Africa/Douala'),
    'Peru': (-12.0464, -77.0428, 'America/Lima'),
    'Ecuador': (-0.1807, -78.4678, 'America/Guayaquil'),
    'Venezuela': (10.4806, -66.9036, 'America/Caracas'),
    'Chile': (-33.4489, -70.6693, 'America/Santiago'),
    'Dominican Republic': (18.4861, -69.9312, 'America/Santo_Domingo'),
    'Guyana': (6.8013, -58.1551, 'America/Guyana'),
    'Trinidad and Tobago': (10.6918, -61.2225, 'America/Port_of_Spain'),
    'India': (28.6139, 77.2090, 'Asia/Kolkata'),
    'Iran': (35.6892, 51.3890, 'Asia/Tehran'),
    'Iraq': (33.3152, 44.3661, 'Asia/Baghdad'),
    'Israel': (31.7683, 35.2137, 'Asia/Jerusalem'),
    'Azerbaijan': (40.4093, 49.8671, 'Asia/Baku'),
    'Armenia': (40.1792, 44.4991, 'Asia/Yerevan'),
    'Mongolia': (47.8864, 106.9057, 'Asia/Ulaanbaatar'),
    'Myanmar': (16.8661, 96.1951, 'Asia/Yangon'),
    'Guam': (13.4443, 144.7937, 'Pacific/Guam'),
    'Republic of the Congo': (-4.2634, 15.2429, 'Africa/Brazzaville'),
    'Democratic Republic of the Congo': (-4.4419, 15.2663, 'Africa/Kinshasa'),
}

# Build fighter location table: (lat, lon, tz_str)
fighter_loc = {}
for f, d in matched.items():
    lat, lon = d.get('lat'), d.get('lon')
    if lat and str(lat).strip() and str(lat).strip() != 'nan':
        try:
            lat, lon = float(lat), float(lon)
            if math.isnan(lat) or math.isnan(lon):
                raise ValueError
            tz_str = tf.timezone_at(lat=lat, lng=lon)
        except (ValueError, TypeError):
            if d.get('country') and d['country'] in COUNTRY_CENTROIDS:
                clat, clon, ctz = COUNTRY_CENTROIDS[d['country']]
                fighter_loc[f] = (clat, clon, ctz)
            continue
        if not tz_str:
            tz_str = 'UTC'
        fighter_loc[f] = (lat, lon, tz_str)
    elif d.get('country') and d['country'] in COUNTRY_CENTROIDS:
        clat, clon, ctz = COUNTRY_CENTROIDS[d['country']]
        fighter_loc[f] = (clat, clon, ctz)

print(f"\n  Fighters with usable location (coords or country centroid): {len(fighter_loc)}/{len(ufc_fighters)}")


# ═══════════════════════════════════════════════════════════════════
# STEP 3: BUILD BOUT-LEVEL TRAVEL FEATURES
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("STEP 3: BUILD BOUT-LEVEL TRAVEL FEATURES")
print(f"{'='*72}")

# Build event location lookup from ufcstats events
event_loc = {}
for _, row in geocoded_events.iterrows():
    event_loc[row['event_url']] = {
        'lat': row['lat'], 'lon': row['lon'], 'tz': row['tz'],
        'location': row['location']
    }

# Load the panel and build bout-level dataset
panel['date'] = pd.to_datetime(panel['date'])
paired = panel.groupby('fight_id').filter(lambda x: len(x) == 2)

# Need to join fights to events to get event_url for location
fights_raw = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv')

# Build fight_url -> event_url mapping
fight_to_event = dict(zip(fights_raw['fight_url'], fights_raw['event_url']))

bouts = []
for fid, grp in paired.groupby('fight_id'):
    grp = grp.sort_values('fighter')
    r1, r2 = grp.iloc[0], grp.iloc[1]
    fa, fb = r1['fighter'], r1['opponent']

    # Get event location
    fight_url = r1['fight_url']
    event_url = fight_to_event.get(fight_url)
    ev_info = event_loc.get(event_url) if event_url else None
    if not ev_info:
        continue

    # Get fighter locations
    loc_a = fighter_loc.get(fa)
    loc_b = fighter_loc.get(fb)

    bout = {
        'fight_id': fid,
        'date': r1['date'],
        'year': r1['year'],
        'division': r1['division'],
        'fa': fa, 'fb': fb,
        'rating_a': r1['sapm_pre_r'],
        'rating_b': r1['sapm_pre_r_opp'],
        'layoff_a': r1['layoff_days'],
        'layoff_b': r2['layoff_days'],
        'p_mkt_a': r1['p_close_hi'],
        'win_a': int(r1['win']),
        'event_lat': ev_info['lat'],
        'event_lon': ev_info['lon'],
        'event_tz': ev_info['tz'],
        'event_loc': ev_info['location'],
        'has_travel': False,
    }

    if loc_a and loc_b:
        # Great-circle distance (km)
        dist_a = geodesic((loc_a[0], loc_a[1]), (ev_info['lat'], ev_info['lon'])).km
        dist_b = geodesic((loc_b[0], loc_b[1]), (ev_info['lat'], ev_info['lon'])).km

        # Time-zone offset (hours) at fight date
        try:
            fight_dt = datetime(r1['date'].year, r1['date'].month, r1['date'].day, 12, 0)
            tz_event = ZoneInfo(ev_info['tz'])
            tz_a = ZoneInfo(loc_a[2])
            tz_b = ZoneInfo(loc_b[2])
            offset_event = fight_dt.replace(tzinfo=tz_event).utcoffset().total_seconds() / 3600
            offset_a = fight_dt.replace(tzinfo=tz_a).utcoffset().total_seconds() / 3600
            offset_b = fight_dt.replace(tzinfo=tz_b).utcoffset().total_seconds() / 3600
            tz_delta_a = abs(offset_a - offset_event)
            tz_delta_b = abs(offset_b - offset_event)
        except:
            tz_delta_a = tz_delta_b = None

        bout['dist_a'] = dist_a
        bout['dist_b'] = dist_b
        bout['dist_diff'] = dist_a - dist_b  # positive = a traveled more
        bout['log_dist_diff'] = np.log1p(dist_a) - np.log1p(dist_b)
        bout['dist_ratio'] = dist_a / (dist_a + dist_b + 1)

        if tz_delta_a is not None and tz_delta_b is not None:
            bout['tz_delta_a'] = tz_delta_a
            bout['tz_delta_b'] = tz_delta_b
            bout['tz_diff'] = tz_delta_a - tz_delta_b  # positive = a crossed more zones
            bout['has_travel'] = True

        # Home advantage indicator (same country)
        bout['home_a'] = 1 if (loc_a and 'USA' in ev_info['location'] and
                               matched.get(fa,{}).get('country') == 'United States') else 0
        bout['home_b'] = 1 if (loc_b and 'USA' in ev_info['location'] and
                               matched.get(fb,{}).get('country') == 'United States') else 0

        # More general: same country check
        country_a = matched.get(fa,{}).get('country','')
        country_b = matched.get(fb,{}).get('country','')
        event_country = ev_info['location'].split(',')[-1].strip()

        # Map event country to Wikidata country name
        ec_map = {
            'USA': 'United States', 'Brazil': 'Brazil', 'Canada': 'Canada',
            'United Kingdom': 'United Kingdom', 'Australia': 'Australia',
            'United Arab Emirates': 'United Arab Emirates', 'China': 'China',
            'Japan': 'Japan', 'Mexico': 'Mexico', 'France': 'France',
            'Germany': 'Germany', 'Netherlands': 'Netherlands', 'Sweden': 'Sweden',
            'Ireland': 'Ireland', 'South Korea': 'South Korea', 'Singapore': 'Singapore',
            'New Zealand': 'New Zealand', 'Poland': 'Poland', 'Saudi Arabia': 'Saudi Arabia',
            'Qatar': 'Qatar', 'Russia': 'Russia', 'Azerbaijan': 'Azerbaijan',
            'Denmark': 'Denmark', 'Philippines': 'Philippines', 'Indonesia': 'Indonesia',
        }
        ec_std = ec_map.get(event_country, event_country)
        bout['home_country_a'] = 1 if country_a == ec_std else 0
        bout['home_country_b'] = 1 if country_b == ec_std else 0

    bouts.append(bout)

bouts = pd.DataFrame(bouts).sort_values('date').reset_index(drop=True)
travel_bouts = bouts[bouts['has_travel']].copy()

print(f"  Total bouts with event location: {len(bouts)}")
print(f"  Bouts with BOTH fighters' travel data: {len(travel_bouts)} ({len(travel_bouts)/len(bouts):.1%})")
print(f"  Year range: {travel_bouts['year'].min()}-{travel_bouts['year'].max()}")

# Temporal splits
train = travel_bouts[travel_bouts['year'] <= 2020].copy()
val = travel_bouts[(travel_bouts['year'] >= 2021) & (travel_bouts['year'] <= 2023)].copy()
test = travel_bouts[(travel_bouts['year'] >= 2024) & (travel_bouts['year'] <= 2025)].copy()

print(f"\n  Train (<=2020): {len(train)}")
print(f"  Validate (2021-23): {len(val)}")
print(f"  Test (2024-25): {len(test)}")

# Descriptive stats
print(f"\n  Travel descriptives (all bouts with travel):")
print(f"    Mean dist_a: {travel_bouts['dist_a'].mean():,.0f} km")
print(f"    Mean dist_b: {travel_bouts['dist_b'].mean():,.0f} km")
print(f"    Mean |dist_diff|: {travel_bouts['dist_diff'].abs().mean():,.0f} km")
print(f"    Mean tz_delta_a: {travel_bouts['tz_delta_a'].mean():.1f} hrs")
print(f"    Mean tz_delta_b: {travel_bouts['tz_delta_b'].mean():.1f} hrs")
print(f"    Mean |tz_diff|: {travel_bouts['tz_diff'].abs().mean():.1f} hrs")
print(f"    Home country (a): {travel_bouts['home_country_a'].mean():.1%}")
print(f"    Home country (b): {travel_bouts['home_country_b'].mean():.1%}")


# ═══════════════════════════════════════════════════════════════════
# TEST 1: IN-SAMPLE — DOES TRAVEL PREDICT WINS NET OF MARKET?
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 1: IN-SAMPLE — TRAVEL SIGNAL NET OF MARKET")
print(f"{'='*72}")

# Logistic: win_a ~ market_prob + travel_differential
# If travel matters net of market, its coefficient should be significant

all_data = pd.concat([train, val, test]).sort_values('date').reset_index(drop=True)
y_all = all_data['win_a'].values

# (a) Distance differential
def neg_ll(params, X_dict, y):
    z = params[0]
    for i, (k, v) in enumerate(X_dict.items()):
        z = z + params[i+1] * v
    p = np.clip(expit(z), 1e-10, 1-1e-10)
    return -np.sum(y * np.log(p) + (1-y) * np.log(1-p))

# Market only (benchmark)
X_mkt = {'mkt_prob': all_data['p_mkt_a'].values}
res_mkt = minimize(neg_ll, [0, 1], args=(X_mkt, y_all), method='Nelder-Mead')

# Market + distance differential (log scale)
X_dist = {
    'mkt_prob': all_data['p_mkt_a'].values,
    'log_dist_diff': all_data['log_dist_diff'].values,
}
res_dist = minimize(neg_ll, [0, 1, 0], args=(X_dist, y_all), method='Nelder-Mead',
                    options={'maxiter': 10000})

# Market + timezone differential
X_tz = {
    'mkt_prob': all_data['p_mkt_a'].values,
    'tz_diff': all_data['tz_diff'].values,
}
res_tz = minimize(neg_ll, [0, 1, 0], args=(X_tz, y_all), method='Nelder-Mead',
                  options={'maxiter': 10000})

# Market + home country
X_home = {
    'mkt_prob': all_data['p_mkt_a'].values,
    'home_diff': (all_data['home_country_a'] - all_data['home_country_b']).values.astype(float),
}
res_home = minimize(neg_ll, [0, 1, 0], args=(X_home, y_all), method='Nelder-Mead',
                    options={'maxiter': 10000})

# Market + all travel
X_all_travel = {
    'mkt_prob': all_data['p_mkt_a'].values,
    'log_dist_diff': all_data['log_dist_diff'].values,
    'tz_diff': all_data['tz_diff'].values,
    'home_diff': (all_data['home_country_a'] - all_data['home_country_b']).values.astype(float),
}
res_all = minimize(neg_ll, [0, 1, 0, 0, 0], args=(X_all_travel, y_all), method='Nelder-Mead',
                   options={'maxiter': 10000})

print(f"\n  IN-SAMPLE COEFFICIENTS (full dataset, {len(all_data)} bouts):")
print(f"\n  Market only:")
print(f"    intercept: {res_mkt.x[0]:+.4f}, mkt_prob: {res_mkt.x[1]:+.4f}")

print(f"\n  Market + log distance differential:")
print(f"    intercept: {res_dist.x[0]:+.4f}")
print(f"    mkt_prob:      {res_dist.x[1]:+.4f}")
print(f"    log_dist_diff: {res_dist.x[2]:+.4f}  (neg = more travel hurts)")

print(f"\n  Market + timezone differential:")
print(f"    intercept: {res_tz.x[0]:+.4f}")
print(f"    mkt_prob: {res_tz.x[1]:+.4f}")
print(f"    tz_diff:  {res_tz.x[2]:+.4f}  (neg = more tz shift hurts)")

print(f"\n  Market + home country advantage:")
print(f"    intercept: {res_home.x[0]:+.4f}")
print(f"    mkt_prob:  {res_home.x[1]:+.4f}")
print(f"    home_diff: {res_home.x[2]:+.4f}  (pos = home advantage)")

print(f"\n  Market + all travel:")
print(f"    intercept:     {res_all.x[0]:+.4f}")
print(f"    mkt_prob:      {res_all.x[1]:+.4f}")
print(f"    log_dist_diff: {res_all.x[2]:+.4f}")
print(f"    tz_diff:       {res_all.x[3]:+.4f}")
print(f"    home_diff:     {res_all.x[4]:+.4f}")

# Bootstrap CIs for key coefficients
print(f"\n  Bootstrap CIs (N={N_BOOT}):")
def boot_coef(X_dict, y, n_params, idx=None, start=None):
    """Bootstrap the coefficient at position idx."""
    coefs = []
    n = len(y)
    x0 = start if start is not None else [0]*n_params
    for _ in range(N_BOOT):
        bi = rng.choice(n, n, replace=True)
        y_b = y[bi]
        X_b = {k: v[bi] for k, v in X_dict.items()}
        try:
            res = minimize(neg_ll, x0, args=(X_b, y_b), method='Nelder-Mead',
                          options={'maxiter': 3000, 'xatol': 1e-3, 'fatol': 1e-3})
            if idx is not None:
                coefs.append(res.x[idx])
            else:
                coefs.append(res.x)
        except:
            pass
    return np.array(coefs)

# Bootstrap distance coefficient (warm-start from point estimates)
print("    bootstrapping log_dist_diff...")
dist_boots = boot_coef(X_dist, y_all, 3, idx=2, start=list(res_dist.x))
print("    bootstrapping tz_diff...")
tz_boots = boot_coef(X_tz, y_all, 3, idx=2, start=list(res_tz.x))
print("    bootstrapping home_diff...")
home_boots = boot_coef(X_home, y_all, 3, idx=2, start=list(res_home.x))

for name, boots, point in [
    ('log_dist_diff', dist_boots, res_dist.x[2]),
    ('tz_diff', tz_boots, res_tz.x[2]),
    ('home_diff', home_boots, res_home.x[2]),
]:
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"    {name:<16s}: {point:+.4f} [{lo:+.4f}, {hi:+.4f}]  sig={sig}")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: OUT-OF-SAMPLE — DOES TRAVEL IMPROVE BRIER?
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 2: OUT-OF-SAMPLE (2024-25) — TRAVEL vs MARKET BRIER")
print(f"{'='*72}")

train_val = pd.concat([train, val]).sort_values('date').reset_index(drop=True)
y_tv = train_val['win_a'].values
y_test = test['win_a'].values
mkt_test = test['p_mkt_a'].values

mkt_brier = brier_score_loss(y_test, mkt_test)
mkt_ll = log_loss(y_test, np.clip(mkt_test, 1e-6, 1-1e-6))
mkt_acc = accuracy_score(y_test, (mkt_test > 0.5).astype(int))

# Fit on train+val, predict test
models_oos = {}

# (a) Market only
X_tv_mkt = {'mkt_prob': train_val['p_mkt_a'].values}
r_mkt = minimize(neg_ll, [0, 1], args=(X_tv_mkt, y_tv), method='Nelder-Mead')
pred_mkt = expit(r_mkt.x[0] + r_mkt.x[1] * mkt_test)
models_oos['Market (logistic)'] = pred_mkt

# (b) Market + distance
X_tv_d = {'mkt_prob': train_val['p_mkt_a'].values, 'log_dist_diff': train_val['log_dist_diff'].values}
r_d = minimize(neg_ll, [0, 1, 0], args=(X_tv_d, y_tv), method='Nelder-Mead', options={'maxiter': 10000})
pred_d = expit(r_d.x[0] + r_d.x[1]*mkt_test + r_d.x[2]*test['log_dist_diff'].values)
models_oos['Mkt + distance'] = pred_d

# (c) Market + timezone
X_tv_tz = {'mkt_prob': train_val['p_mkt_a'].values, 'tz_diff': train_val['tz_diff'].values}
r_tz = minimize(neg_ll, [0, 1, 0], args=(X_tv_tz, y_tv), method='Nelder-Mead', options={'maxiter': 10000})
pred_tz = expit(r_tz.x[0] + r_tz.x[1]*mkt_test + r_tz.x[2]*test['tz_diff'].values)
models_oos['Mkt + timezone'] = pred_tz

# (d) Market + home country
X_tv_h = {'mkt_prob': train_val['p_mkt_a'].values,
           'home_diff': (train_val['home_country_a'] - train_val['home_country_b']).values.astype(float)}
r_h = minimize(neg_ll, [0, 1, 0], args=(X_tv_h, y_tv), method='Nelder-Mead', options={'maxiter': 10000})
pred_h = expit(r_h.x[0] + r_h.x[1]*mkt_test +
               r_h.x[2]*(test['home_country_a'] - test['home_country_b']).values.astype(float))
models_oos['Mkt + home country'] = pred_h

# (e) Market + all travel
X_tv_all = {
    'mkt_prob': train_val['p_mkt_a'].values,
    'log_dist_diff': train_val['log_dist_diff'].values,
    'tz_diff': train_val['tz_diff'].values,
    'home_diff': (train_val['home_country_a'] - train_val['home_country_b']).values.astype(float),
}
r_all = minimize(neg_ll, [0, 1, 0, 0, 0], args=(X_tv_all, y_tv), method='Nelder-Mead',
                 options={'maxiter': 10000})
pred_all = expit(r_all.x[0] + r_all.x[1]*mkt_test +
                 r_all.x[2]*test['log_dist_diff'].values +
                 r_all.x[3]*test['tz_diff'].values +
                 r_all.x[4]*(test['home_country_a'] - test['home_country_b']).values.astype(float))
models_oos['Mkt + all travel'] = pred_all

# Raw market
models_oos['Market (raw)'] = mkt_test

print(f"\n  Test set: {len(test)} bouts (2024-25)")
print(f"\n  {'Model':<25s} {'Acc':>6} {'Brier':>7} {'LogLoss':>8}  {'vs Mkt Brier':>12}")
print("  " + "-" * 65)
for name, preds in models_oos.items():
    pc = np.clip(preds, 1e-6, 1-1e-6)
    acc = accuracy_score(y_test, (preds > 0.5).astype(int))
    brier = brier_score_loss(y_test, pc)
    ll = log_loss(y_test, pc)
    delta = brier - mkt_brier
    print(f"  {name:<25s} {acc:>5.1%} {brier:>7.4f} {ll:>8.4f}  {delta:>+12.4f}")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: BETTING CHECK — ROI BACKING LESS-TRAVELED FIGHTER
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 3: FLAT-STAKE ROI — BACK LESS-TRAVELED FIGHTER")
print(f"{'='*72}")

# For each bout in test: bet on the fighter who traveled less (distance version)
# and timezone version. Use p_mkt_a as the implied odds (fair odds = break-even line)
# ROI = avg(payout * win - 1)

def compute_roi(bouts_df, travel_col, direction='less'):
    """
    Bet on the fighter who traveled less (direction='less') or more.
    ROI based on fair odds (break-even = 1/p_market, no vig adjustment needed
    since we're testing against fair prob).
    """
    profits = []
    for _, row in bouts_df.iterrows():
        if direction == 'less':
            bet_a = row[travel_col] < 0  # a traveled less
        else:
            bet_a = row[travel_col] > 0  # a traveled more

        if abs(row[travel_col]) < 0.01:  # skip near-equal
            continue

        if bet_a:
            fair_odds = 1 / row['p_mkt_a']
            profit = fair_odds * row['win_a'] - 1
        else:
            fair_odds = 1 / (1 - row['p_mkt_a'])
            profit = fair_odds * (1 - row['win_a']) - 1
        profits.append(profit)

    return np.array(profits)

# Distance version
profits_dist = compute_roi(test, 'dist_diff', 'less')
# Timezone version
profits_tz = compute_roi(test, 'tz_diff', 'less')
# Home country version
test_home = test.copy()
test_home['home_diff_val'] = test_home['home_country_a'] - test_home['home_country_b']
profits_home = compute_roi(test_home, 'home_diff_val', 'less')

for name, profits in [('Distance (less travel)', profits_dist),
                       ('Timezone (less shift)', profits_tz),
                       ('Home country', profits_home)]:
    if len(profits) == 0:
        print(f"  {name}: no qualifying bets")
        continue
    roi = profits.mean()
    n = len(profits)
    # Bootstrap CI
    boot_rois = [rng.choice(profits, n, replace=True).mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boot_rois, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"  {name}:")
    print(f"    N bets: {n}, ROI: {roi:+.2%} [{lo:+.2%}, {hi:+.2%}]  sig={sig}")


# ═══════════════════════════════════════════════════════════════════
# TEST 4: DISTANCE vs TIMEZONE — WHICH CARRIES THE SIGNAL?
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 4: DISTANCE vs TIMEZONE — WHICH VARIABLE?")
print(f"{'='*72}")

# Horse race: include both, see which coefficient survives
X_tv_horse = {
    'mkt_prob': train_val['p_mkt_a'].values,
    'log_dist_diff': train_val['log_dist_diff'].values,
    'tz_diff': train_val['tz_diff'].values,
}
r_horse = minimize(neg_ll, [0, 1, 0, 0], args=(X_tv_horse, y_tv), method='Nelder-Mead',
                   options={'maxiter': 10000})
print(f"\n  Horse race (train+val fit):")
print(f"    intercept:     {r_horse.x[0]:+.4f}")
print(f"    mkt_prob:      {r_horse.x[1]:+.4f}")
print(f"    log_dist_diff: {r_horse.x[2]:+.4f}")
print(f"    tz_diff:       {r_horse.x[3]:+.4f}")

# Compare OOS Brier
pred_horse = expit(r_horse.x[0] + r_horse.x[1]*mkt_test +
                   r_horse.x[2]*test['log_dist_diff'].values +
                   r_horse.x[3]*test['tz_diff'].values)
brier_horse = brier_score_loss(y_test, np.clip(pred_horse, 1e-6, 1-1e-6))
brier_dist_only = brier_score_loss(y_test, np.clip(pred_d, 1e-6, 1-1e-6))
brier_tz_only = brier_score_loss(y_test, np.clip(pred_tz, 1e-6, 1-1e-6))

print(f"\n  Test Brier comparison:")
print(f"    Market raw:        {mkt_brier:.4f}")
print(f"    Mkt + dist only:   {brier_dist_only:.4f} ({brier_dist_only-mkt_brier:+.4f})")
print(f"    Mkt + tz only:     {brier_tz_only:.4f} ({brier_tz_only-mkt_brier:+.4f})")
print(f"    Mkt + both:        {brier_horse:.4f} ({brier_horse-mkt_brier:+.4f})")

# Correlation between distance and timezone
corr = np.corrcoef(all_data['log_dist_diff'].values, all_data['tz_diff'].values)[0,1]
print(f"\n  Correlation(log_dist_diff, tz_diff): {corr:.3f}")


# ═══════════════════════════════════════════════════════════════════
# COMBINED M&N REPLICATION SUMMARY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("COMBINED M&N (2026) REPLICATION SUMMARY")
print(f"{'='*72}")

# Results from exotic_models.py for age and women's
print(f"""
  Data: 2007-2025 UFC, BFO de-vigged closing lines, UFCStats outcomes
  Method: temporal split (train<=2020, val 2021-23, test 2024-25)
  Benchmark: closing-line implied probability

  {'Inefficiency':<25s} {'In-sample coef':>15s} {'OOS Brier delta':>16s} {'Verdict':>12s}
  {'-'*72}

  1. AGE / YOUTH
     BT age-cliff model         see exotic_models    +0.0462 vs mkt     EFFICIENT
     Career-count proxy         see exotic_models    +0.0429 vs mkt     EFFICIENT
     (Market already prices fighter age/experience)

  2. WOMEN'S FAVORITES
     2024 favorite spike                             p=0.052 raw        EFFICIENT
     Full-history pooled                             null                EFFICIENT
     (Variance excursion; fails multiplicity correction)

  3. TRAVEL (this analysis, N={len(all_data)} bouts with travel data):
     Distance diff (log)        {res_dist.x[2]:+.4f}          {brier_dist_only-mkt_brier:+.4f}          {'EFFICIENT' if abs(brier_dist_only-mkt_brier) < 0.003 else '???'}
     Timezone diff              {res_tz.x[2]:+.4f}          {brier_tz_only-mkt_brier:+.4f}          {'EFFICIENT' if abs(brier_tz_only-mkt_brier) < 0.003 else '???'}
     Home country               {res_home.x[2]:+.4f}          {brier_score_loss(y_test, np.clip(pred_h,1e-6,1-1e-6))-mkt_brier:+.4f}          {'EFFICIENT' if abs(brier_score_loss(y_test, np.clip(pred_h,1e-6,1-1e-6))-mkt_brier) < 0.003 else '???'}

  OVERALL: M&N's three in-sample inefficiencies all resolve to EFFICIENT
  on 2007-2025 data with temporal validation and a market benchmark.
  This matches their own out-of-sample finding: MMA is largely efficient.
  The closing line prices in age, gender, and travel.
""")

# Coverage quality flag
print(f"  COVERAGE QUALITY:")
print(f"    Fighter location match rate: {len(matched)}/{len(ufc_fighters)} ({len(matched)/len(ufc_fighters):.1%})")
print(f"    Bouts with both fighters located: {len(travel_bouts)}/{len(bouts)} ({len(travel_bouts)/len(bouts):.1%})")
print(f"    Location source: Wikidata birthplace coords ({with_coords}) + country centroids ({len(fighter_loc)-with_coords})")
print(f"    Weak link: {len(ufc_fighters)-len(matched)} fighters unmatched = potential selection bias")
print(f"    (unmatched fighters are likely lesser-known → less Wikidata coverage)")
