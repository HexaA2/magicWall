import json
import csv
from pathlib import Path

import geopandas as gpd
import folium

# States to include
TARGET_STATES = ['NY', 'NJ', 'PA', 'ME', 'VA', 'OH']
TARGET_STATE_FIPS = {
    'NY': '36',
    'NJ': '34',
    'PA': '42',
    'ME': '23',
    'VA': '51',
    'OH': '39'
}

ALL_STATE_FIPS = {
    'AL': '01', 'AK': '02', 'AZ': '04', 'AR': '05', 'CA': '06', 'CO': '08', 'CT': '09', 'DE': '10',
    'DC': '11', 'FL': '12', 'GA': '13', 'HI': '15', 'ID': '16', 'IL': '17', 'IN': '18', 'IA': '19',
    'KS': '20', 'KY': '21', 'LA': '22', 'ME': '23', 'MD': '24', 'MA': '25', 'MI': '26', 'MN': '27',
    'MS': '28', 'MO': '29', 'MT': '30', 'NE': '31', 'NV': '32', 'NH': '33', 'NJ': '34', 'NM': '35',
    'NY': '36', 'NC': '37', 'ND': '38', 'OH': '39', 'OK': '40', 'OR': '41', 'PA': '42', 'RI': '44',
    'SC': '45', 'SD': '46', 'TN': '47', 'TX': '48', 'UT': '49', 'VT': '50', 'VA': '51', 'WA': '53',
    'WV': '54', 'WI': '55', 'WY': '56'
}
FIPS_TO_STATE = {v: k for k, v in ALL_STATE_FIPS.items()}
EXCLUDED_STATE_FIPS = {'02', '15'}  # Alaska, Hawaii

BASE_DIR = Path(__file__).resolve().parent
VOTES_2024_CSV = BASE_DIR / 'data' / '2024_US_County_Level_Presidential_Results.csv'
VOTES_2020_CSV = BASE_DIR / 'data' / '2020_US_County_Level_Presidential_Results.csv'

def get_state_bounds(states_gdf):
    """Calculate the bounds to center the map on all selected states"""
    bounds = states_gdf.total_bounds
    return bounds


def load_json_file(path):
    """Load JSON data from disk, returning empty dict if file is missing."""
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def load_votes_from_csvs():
    """Load 2020/2024 vote data from CSV files for all states/counties."""
    state_votes_by_year = {'2020': {}, '2024': {}}
    county_votes_by_state_year = {'2020': {}, '2024': {}}

    # 2024 county-level source
    with VOTES_2024_CSV.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            geoid = str(row.get('county_fips') or row.get('FIPS') or '').zfill(5)
            if not geoid or geoid == '00000':
                continue
            state_fips = geoid[:2]
            if state_fips in EXCLUDED_STATE_FIPS:
                continue
            state_abbrev = FIPS_TO_STATE.get(state_fips)
            if not state_abbrev:
                continue

            dem = int(float(row.get('votes_dem') or row.get('Votes_Harris') or 0))
            rep = int(float(row.get('votes_gop') or row.get('Votes_Trump') or 0))
            if row.get('total_votes'):
                total = int(float(row.get('total_votes') or 0))
                third = max(0, total - dem - rep)
            else:
                third = int(float(row.get('Votes_Stein') or 0))

            county_votes_by_state_year['2024'].setdefault(state_abbrev, {})[geoid] = {
                'democrat': dem,
                'republican': rep,
                'third_party': third,
            }

            st = state_votes_by_year['2024'].setdefault(
                state_abbrev, {'democrat': 0, 'republican': 0, 'third_party': 0}
            )
            st['democrat'] += dem
            st['republican'] += rep
            st['third_party'] += third

    # 2020 county-level source
    with VOTES_2020_CSV.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            geoid = str(row.get('county_fips', '')).zfill(5)
            if not geoid or geoid == '00000':
                continue
            state_fips = geoid[:2]
            if state_fips in EXCLUDED_STATE_FIPS:
                continue
            state_abbrev = FIPS_TO_STATE.get(state_fips)
            if not state_abbrev:
                continue

            dem = int(float(row.get('votes_dem', 0) or 0))
            rep = int(float(row.get('votes_gop', 0) or 0))
            total = int(float(row.get('total_votes', 0) or 0))
            third = max(0, total - dem - rep)

            county_votes_by_state_year['2020'].setdefault(state_abbrev, {})[geoid] = {
                'democrat': dem,
                'republican': rep,
                'third_party': third,
            }

            st = state_votes_by_year['2020'].setdefault(
                state_abbrev, {'democrat': 0, 'republican': 0, 'third_party': 0}
            )
            st['democrat'] += dem
            st['republican'] += rep
            st['third_party'] += third

    return state_votes_by_year, county_votes_by_state_year


def vote_color(democrat_votes, republican_votes, third_party_votes=0):
    """Dark-mode red-white-blue gradient by Democratic vote share."""
    dem = max(0, int(democrat_votes or 0))
    rep = max(0, int(republican_votes or 0))
    third = max(0, int(third_party_votes or 0))
    total = dem + rep + third

    # Exact diverging scale: 0% D -> red, 50% D -> white, 100% D -> blue.
    dem_share = 0.5 if total == 0 else dem / total
    dem_share = max(0.0, min(1.0, dem_share))

    if dem_share <= 0.5:
        t = dem_share / 0.5
        red = 255
        green = int(255 * t)
        blue = int(255 * t)
    else:
        t = (dem_share - 0.5) / 0.5
        red = int(255 * (1 - t))
        green = int(255 * (1 - t))
        blue = 255

    return f'#{red:02x}{green:02x}{blue:02x}'


def vote_color_light(democrat_votes, republican_votes, third_party_votes=0):
    """Light-mode red-white-blue gradient by Democratic vote share."""
    dem = max(0, int(democrat_votes or 0))
    rep = max(0, int(republican_votes or 0))
    third = max(0, int(third_party_votes or 0))
    total = dem + rep + third
    dem_share = 0.5 if total == 0 else dem / total
    dem_share = max(0.0, min(1.0, dem_share))

    # Exact diverging scale: 0% D -> red, 50% D -> white, 100% D -> blue.
    if dem_share <= 0.5:
        t = dem_share / 0.5
        r = 255
        g = int(255 * t)
        b = int(255 * t)
    else:
        t = (dem_share - 0.5) / 0.5
        r = int(255 * (1 - t))
        g = int(255 * (1 - t))
        b = 255

    return f'#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}'


def winner_color_light(democrat_votes, republican_votes):
    """Return pure blue for Democrat winner, pure red for Republican winner, white for tie."""
    dem = max(0, int(democrat_votes or 0))
    rep = max(0, int(republican_votes or 0))
    if dem > rep:
        return '#0000ff'
    if rep > dem:
        return '#ff0000'
    return '#ffffff'


def winner_color(democrat_votes, republican_votes):
    """Return blue for Democrat winner, red for Republican winner, and purple for tie."""
    dem = max(0, int(democrat_votes or 0))
    rep = max(0, int(republican_votes or 0))
    if dem > rep:
        return '#1f77ff'
    if rep > dem:
        return '#ff2b2b'
    return '#7f5fbf'


def voting_map_color(democrat_votes, republican_votes):
    """Return a standard election-map style color by winner + margin intensity."""
    dem = max(0, int(democrat_votes or 0))
    rep = max(0, int(republican_votes or 0))
    total = dem + rep
    if total == 0:
        return '#7f5fbf'

    margin = abs(dem - rep) / total
    dem_wins = dem >= rep

    # Typical voting-map buckets: closer races are lighter, blowouts are darker.
    if dem_wins:
        if margin < 0.03:
            return '#a8c1ff'
        if margin < 0.10:
            return '#6f95ff'
        if margin < 0.20:
            return '#3f73ff'
        return '#1f4fff'

    if margin < 0.03:
        return '#ffb3b3'
    if margin < 0.10:
        return '#ff8080'
    if margin < 0.20:
        return '#ff4d4d'
    return '#ff2020'


def voting_map_color_light(democrat_votes, republican_votes):
    """Light-mode winner+margin palette with white near toss-up and black borders via theme."""
    dem = max(0, int(democrat_votes or 0))
    rep = max(0, int(republican_votes or 0))
    total = dem + rep
    if total == 0:
        return '#ffffff'

    margin = abs(dem - rep) / total
    dem_wins = dem >= rep

    if margin < 0.03:
        return '#ffffff'

    if dem_wins:
        if margin < 0.10:
            return '#d6d6ff'
        if margin < 0.20:
            return '#8080ff'
        return '#0000ff'

    if margin < 0.10:
        return '#ffd6d6'
    if margin < 0.20:
        return '#ff8080'
    return '#ff0000'


def change_color_dark(delta_dem_share):
    """Dark-mode voting-map style color for 2024 vs 2020 Democratic vote-share change."""
    shift = float(delta_dem_share or 0.0)
    mag = abs(shift)

    if mag < 0.005:
        return '#9a9a9a'

    moved_dem = shift > 0
    if moved_dem:
        if mag < 0.015:
            return '#a8c1ff'
        if mag < 0.03:
            return '#6f95ff'
        if mag < 0.06:
            return '#3f73ff'
        return '#1f4fff'

    if mag < 0.015:
        return '#ffb3b3'
    if mag < 0.03:
        return '#ff8080'
    if mag < 0.06:
        return '#ff4d4d'
    return '#ff2020'


def change_color_light(delta_dem_share):
    """Light-mode voting-map style color for 2024 vs 2020 Democratic vote-share change."""
    shift = float(delta_dem_share or 0.0)
    mag = abs(shift)

    if mag < 0.005:
        return '#ffffff'

    moved_dem = shift > 0
    if moved_dem:
        if mag < 0.015:
            return '#cfcfff'
        if mag < 0.03:
            return '#7f7fff'
        if mag < 0.06:
            return '#2f2fff'
        return '#0000ff'

    if mag < 0.015:
        return '#ffcfcf'
    if mag < 0.03:
        return '#ff7f7f'
    if mag < 0.06:
        return '#ff2f2f'
    return '#ff0000'


def format_vote_with_pct(votes, total_votes):
    """Format vote count with percent of total region votes."""
    v = max(0, int(votes or 0))
    t = max(0, int(total_votes or 0))
    pct = 0.0 if t == 0 else (v / t) * 100.0
    return f"{v:,} ({pct:.1f}%)"


def format_share_change_pp(share_2024, share_2020):
    """Format candidate vote-share change from 2020 to 2024 in percentage points."""
    delta_pp = (float(share_2024 or 0.0) - float(share_2020 or 0.0)) * 100.0
    return f"{delta_pp:+.1f}%"

def create_state_level_map():
    """Create the initial state-level map view"""
    
    # Load US county boundaries from TIGER
    try:
        print("Downloading TIGER county boundaries (2021)...")
        counties = gpd.read_file('https://www2.census.gov/geo/tiger/GENZ2021/shp/cb_2021_us_county_5m.zip')
    except Exception as e:
        print(f"Error loading 2021 data, trying 2020: {e}")
        try:
            print("Downloading TIGER county boundaries (2020)...")
            counties = gpd.read_file('https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_5m.zip')
        except Exception as e2:
            print(f"Error loading 2020 data: {e2}")
            raise
    
    # Map state abbreviations to FIPS codes and filter counties
    counties['state_fips'] = counties['STATEFP'].astype(str).str.zfill(2)

    country_fips_codes = set(ALL_STATE_FIPS.values()) - EXCLUDED_STATE_FIPS
    group_fips_codes = set(TARGET_STATE_FIPS.values())

    counties_country = counties[counties['state_fips'].isin(country_fips_codes)].copy()
    counties_group = counties_country[counties_country['state_fips'].isin(group_fips_codes)].copy()

    # Build state boundaries from county geometry.
    states_country = counties_country.dissolve(by='state_fips', aggfunc='first').copy()
    states_country['state'] = states_country.index.map(FIPS_TO_STATE)

    # Load election data for both years from CSVs.
    state_votes_by_year, county_votes_by_state_year = load_votes_from_csvs()
    
    # Calculate center and initial bounds
    bounds = get_state_bounds(states_country[states_country['state'].isin(TARGET_STATES)])
    group_bounds = get_state_bounds(states_country[states_country['state'].isin(TARGET_STATES)])
    country_bounds = get_state_bounds(states_country)
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    # Create the base map with no tiles (minimal look)
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles=None
    )
    
    # Set map background to dark theme and add cursor styling
    m.get_root().html.add_child(folium.Element(
        '''<style>
        .leaflet-container {
            background-color: #1a1a1a !important;
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        }
        .leaflet-interactive {
            cursor: pointer !important;
        }
        .leaflet-pane svg path.leaflet-interactive:focus,
        .leaflet-pane svg path.leaflet-interactive:focus-visible,
        .leaflet-pane svg:focus {
            outline: none !important;
        }
        .leaflet-control,
        .leaflet-tooltip,
        .leaflet-popup-content,
        .leaflet-popup-content-wrapper,
        #viewToggle,
        #dataModeToggle,
        #scopeToggle,
        #yearToggle,
        #colorModeSelect {
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        }
        </style>'''
    ))
    
    # Create a GeoJson layer for states
    states_geojson = json.loads(states_country.to_json())
    
    # Add state metadata for labels/tooltips
    state_fips_list = list(states_country.index)
    for i, feature in enumerate(states_geojson['features']):
        feature['properties']['state_fips'] = state_fips_list[i]
        state_abbrev = states_country.loc[state_fips_list[i], 'state']
        feature['properties']['state'] = state_abbrev
        feature['properties']['in_group'] = state_abbrev in TARGET_STATES

        for year in ['2020', '2024']:
            vote_data = state_votes_by_year.get(year, {}).get(
                state_abbrev,
                {'democrat': 0, 'republican': 0, 'third_party': 0}
            )
            dem_votes = int(vote_data.get('democrat', 0) or 0)
            rep_votes = int(vote_data.get('republican', 0) or 0)
            third_votes = int(vote_data.get('third_party', 0) or 0)
            total_votes = dem_votes + rep_votes + third_votes

            feature['properties'][f'democrat_votes_{year}'] = dem_votes
            feature['properties'][f'republican_votes_{year}'] = rep_votes
            feature['properties'][f'third_party_votes_{year}'] = third_votes
            feature['properties'][f'democrat_display_{year}'] = format_vote_with_pct(dem_votes, total_votes)
            feature['properties'][f'republican_display_{year}'] = format_vote_with_pct(rep_votes, total_votes)
            feature['properties'][f'third_party_display_{year}'] = format_vote_with_pct(third_votes, total_votes)
            feature['properties'][f'gradient_color_dark_{year}'] = vote_color(dem_votes, rep_votes, third_votes)
            feature['properties'][f'gradient_color_light_{year}'] = vote_color_light(dem_votes, rep_votes, third_votes)
            feature['properties'][f'winner_color_dark_{year}'] = winner_color(dem_votes, rep_votes)
            feature['properties'][f'winner_color_light_{year}'] = winner_color_light(dem_votes, rep_votes)
            feature['properties'][f'voting_color_dark_{year}'] = voting_map_color(dem_votes, rep_votes)
            feature['properties'][f'voting_color_light_{year}'] = voting_map_color_light(dem_votes, rep_votes)

        dem_2020 = int(feature['properties'].get('democrat_votes_2020', 0) or 0)
        rep_2020 = int(feature['properties'].get('republican_votes_2020', 0) or 0)
        third_2020 = int(feature['properties'].get('third_party_votes_2020', 0) or 0)
        total_2020 = dem_2020 + rep_2020 + third_2020
        dem_share_2020 = 0.5 if total_2020 == 0 else (dem_2020 / total_2020)
        rep_share_2020 = 0.5 if total_2020 == 0 else (rep_2020 / total_2020)
        third_share_2020 = 0.0 if total_2020 == 0 else (third_2020 / total_2020)

        dem_2024 = int(feature['properties'].get('democrat_votes_2024', 0) or 0)
        rep_2024 = int(feature['properties'].get('republican_votes_2024', 0) or 0)
        third_2024 = int(feature['properties'].get('third_party_votes_2024', 0) or 0)
        total_2024 = dem_2024 + rep_2024 + third_2024
        dem_share_2024 = 0.5 if total_2024 == 0 else (dem_2024 / total_2024)
        rep_share_2024 = 0.5 if total_2024 == 0 else (rep_2024 / total_2024)
        third_share_2024 = 0.0 if total_2024 == 0 else (third_2024 / total_2024)

        delta_share = dem_share_2024 - dem_share_2020
        feature['properties']['change_color_dark'] = change_color_dark(delta_share)
        feature['properties']['change_color_light'] = change_color_light(delta_share)
        feature['properties']['democrat_change_display'] = format_share_change_pp(dem_share_2024, dem_share_2020)
        feature['properties']['republican_change_display'] = format_share_change_pp(rep_share_2024, rep_share_2020)
        feature['properties']['third_party_change_display'] = format_share_change_pp(third_share_2024, third_share_2020)

        # Default active year at load is 2024.
        feature['properties']['democrat_display'] = feature['properties']['democrat_display_2024']
        feature['properties']['republican_display'] = feature['properties']['republican_display_2024']
        feature['properties']['third_party_display'] = feature['properties']['third_party_display_2024']
        feature['properties']['gradient_color'] = feature['properties']['gradient_color_dark_2024']
        feature['properties']['winner_color'] = feature['properties']['winner_color_dark_2024']
        feature['properties']['voting_color'] = feature['properties']['voting_color_dark_2024']
    
    # State boundaries layer (default visible)
    state_layer = folium.GeoJson(
        states_geojson,
        style_function=lambda x: {
            'fillColor': x['properties']['winner_color'],
            'color': x['properties']['winner_color'],
            'weight': 2.5,
            'fillOpacity': 0.2
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['state', 'democrat_display', 'republican_display', 'third_party_display'],
            aliases=['State:', 'Democrat:', 'Republican:', 'Third-Party:'],
            labels=True,
            localize=True,
            sticky=False,
            style=(
                "background-color: #242424; color: #E0AAFF; "
                "border: 1px solid #9D4EDD; border-radius: 4px; "
                "font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;"
            )
        ),
        name='State Boundaries'
    )
    state_layer.add_to(m)

    # County layer (toggle on/off from slider)
    counties_geojson = json.loads(counties_country.to_json())
    for feature in counties_geojson['features']:
        props = feature['properties']
        feature['properties']['county_name'] = props.get('NAME', 'Unknown')

        state_fips = str(props.get('STATEFP', '')).zfill(2)
        state_abbrev = FIPS_TO_STATE.get(state_fips)
        feature['properties']['state'] = state_abbrev if state_abbrev else ''
        geoid = str(props.get('GEOID', '')).zfill(5)
        feature['properties']['in_group'] = state_abbrev in TARGET_STATES if state_abbrev else False
        feature['properties']['hide_in_county_view'] = (state_abbrev == 'CT')

        for year in ['2020', '2024']:
            vote_data = {}
            if state_abbrev:
                vote_data = county_votes_by_state_year.get(year, {}).get(state_abbrev, {}).get(
                    geoid,
                    {'democrat': 0, 'republican': 0, 'third_party': 0}
                )

            dem_votes = int(vote_data.get('democrat', 0) or 0)
            rep_votes = int(vote_data.get('republican', 0) or 0)
            third_votes = int(vote_data.get('third_party', 0) or 0)
            total_votes = dem_votes + rep_votes + third_votes

            feature['properties'][f'democrat_votes_{year}'] = dem_votes
            feature['properties'][f'republican_votes_{year}'] = rep_votes
            feature['properties'][f'third_party_votes_{year}'] = third_votes
            feature['properties'][f'democrat_display_{year}'] = format_vote_with_pct(dem_votes, total_votes)
            feature['properties'][f'republican_display_{year}'] = format_vote_with_pct(rep_votes, total_votes)
            feature['properties'][f'third_party_display_{year}'] = format_vote_with_pct(third_votes, total_votes)
            feature['properties'][f'gradient_color_dark_{year}'] = vote_color(dem_votes, rep_votes, third_votes)
            feature['properties'][f'gradient_color_light_{year}'] = vote_color_light(dem_votes, rep_votes, third_votes)
            feature['properties'][f'winner_color_dark_{year}'] = winner_color(dem_votes, rep_votes)
            feature['properties'][f'winner_color_light_{year}'] = winner_color_light(dem_votes, rep_votes)
            feature['properties'][f'voting_color_dark_{year}'] = voting_map_color(dem_votes, rep_votes)
            feature['properties'][f'voting_color_light_{year}'] = voting_map_color_light(dem_votes, rep_votes)

        dem_2020 = int(feature['properties'].get('democrat_votes_2020', 0) or 0)
        rep_2020 = int(feature['properties'].get('republican_votes_2020', 0) or 0)
        third_2020 = int(feature['properties'].get('third_party_votes_2020', 0) or 0)
        total_2020 = dem_2020 + rep_2020 + third_2020
        dem_share_2020 = 0.5 if total_2020 == 0 else (dem_2020 / total_2020)
        rep_share_2020 = 0.5 if total_2020 == 0 else (rep_2020 / total_2020)
        third_share_2020 = 0.0 if total_2020 == 0 else (third_2020 / total_2020)

        dem_2024 = int(feature['properties'].get('democrat_votes_2024', 0) or 0)
        rep_2024 = int(feature['properties'].get('republican_votes_2024', 0) or 0)
        third_2024 = int(feature['properties'].get('third_party_votes_2024', 0) or 0)
        total_2024 = dem_2024 + rep_2024 + third_2024
        dem_share_2024 = 0.5 if total_2024 == 0 else (dem_2024 / total_2024)
        rep_share_2024 = 0.5 if total_2024 == 0 else (rep_2024 / total_2024)
        third_share_2024 = 0.0 if total_2024 == 0 else (third_2024 / total_2024)

        delta_share = dem_share_2024 - dem_share_2020
        feature['properties']['change_color_dark'] = change_color_dark(delta_share)
        feature['properties']['change_color_light'] = change_color_light(delta_share)
        feature['properties']['democrat_change_display'] = format_share_change_pp(dem_share_2024, dem_share_2020)
        feature['properties']['republican_change_display'] = format_share_change_pp(rep_share_2024, rep_share_2020)
        feature['properties']['third_party_change_display'] = format_share_change_pp(third_share_2024, third_share_2020)

        # Default active year at load is 2024.
        feature['properties']['democrat_display'] = feature['properties']['democrat_display_2024']
        feature['properties']['republican_display'] = feature['properties']['republican_display_2024']
        feature['properties']['third_party_display'] = feature['properties']['third_party_display_2024']
        feature['properties']['gradient_color'] = feature['properties']['gradient_color_dark_2024']
        feature['properties']['winner_color'] = feature['properties']['winner_color_dark_2024']
        feature['properties']['voting_color'] = feature['properties']['voting_color_dark_2024']

    county_layer = folium.GeoJson(
        counties_geojson,
        style_function=lambda x: {
            'fillColor': x['properties']['winner_color'],
            'color': x['properties']['winner_color'],
            'weight': 1.1,
            'fillOpacity': 0.2
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['county_name', 'democrat_display', 'republican_display', 'third_party_display'],
            aliases=['County:', 'Democrat:', 'Republican:', 'Third-Party:'],
            labels=True,
            localize=True,
            sticky=False,
            style=(
                "background-color: #242424; color: #E0AAFF; "
                "border: 1px solid #9D4EDD; border-radius: 4px; "
                "font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;"
            )
        ),
        name='County Overlay',
        show=False
    )
    county_layer.add_to(m)

    available_states = sorted([s for s in states_country['state'].dropna().unique().tolist()])
    group_filter_states = sorted(['NY', 'NJ', 'PA', 'ME', 'VA', 'OH'])

    state_filter_control_html = f'''
    <div style="position: fixed; top: 100px; left: 50px; z-index: 9999; background: #242424; border: 2px solid #9D4EDD; border-radius: 10px; padding: 8px; width: 178px; box-sizing: border-box;">
        <label for="stateFilterSelect" style="display:block; color:#E0AAFF; font-size:12px; font-weight:700; margin-bottom:6px;">State Filter</label>
        <select id="stateFilterSelect" style="width:100%; background:#1a1a1a; color:#E0AAFF; border:1px solid #9D4EDD; border-radius:6px; padding:4px; font-size:12px;">
            <option value="ALL" selected>All States</option>
        </select>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(state_filter_control_html))

    # Custom top-right slider control for State/County toggle
    slider_control_html = '''
    <div id="viewToggle" style="position: fixed; top: 92px; right: 10px; z-index: 9999; width: 178px; background: #242424; border: 2px solid #9D4EDD; border-radius: 999px; padding: 4px; box-sizing: border-box; user-select: none;">
        <div style="position: relative; height: 30px; overflow: hidden; border-radius: 999px;">
            <div style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">State</div>
            <div style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">County</div>
            <div id="togglePill" style="position: absolute; left: 2px; top: 1px; width: 84px; height: 28px; border-radius: 999px; background: #D6C2F8; display: flex; align-items: center; justify-content: center; z-index: 3; color: #1F1530; font-weight: 700; font-size: 12px; transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);">State</div>
            <button id="stateBtn" type="button" style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">State</button>
            <button id="countyBtn" type="button" style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">County</button>
        </div>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(slider_control_html))

    color_mode_control_html = '''
    <div style="position: fixed; top: 10px; right: 10px; z-index: 9999; background: #242424; border: 2px solid #9D4EDD; border-radius: 10px; padding: 8px; width: 178px; box-sizing: border-box;">
        <label for="colorModeSelect" style="display:block; color:#E0AAFF; font-size:12px; font-weight:700; margin-bottom:6px;">Color Mode</label>
        <select id="colorModeSelect" style="width:100%; background:#1a1a1a; color:#E0AAFF; border:1px solid #9D4EDD; border-radius:6px; padding:4px; font-size:12px;">
            <option value="winner" selected>Winner</option>
            <option value="gradient">Gradient</option>
            <option value="voting">Voting Map</option>
        </select>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(color_mode_control_html))

    data_mode_toggle_html = '''
    <div id="dataModeToggle" style="position: fixed; top: 320px; right: 10px; z-index: 9999; width: 178px; background: #242424; border: 2px solid #9D4EDD; border-radius: 999px; padding: 4px; box-sizing: border-box; user-select: none;">
        <div style="position: relative; height: 30px; overflow: hidden; border-radius: 999px;">
            <div style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">Year</div>
            <div style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">Swing</div>
            <div id="dataModePill" style="position: absolute; left: 2px; top: 1px; width: 84px; height: 28px; border-radius: 999px; background: #D6C2F8; display: flex; align-items: center; justify-content: center; z-index: 3; color: #1F1530; font-weight: 700; font-size: 12px; transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);">Year</div>
            <button id="yearModeBtn" type="button" style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">Year</button>
            <button id="changeModeBtn" type="button" style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">Swing</button>
        </div>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(data_mode_toggle_html))

    scope_toggle_html = '''
    <div id="scopeToggle" style="position: fixed; top: 396px; right: 10px; z-index: 9999; width: 178px; background: #242424; border: 2px solid #9D4EDD; border-radius: 999px; padding: 4px; box-sizing: border-box; user-select: none;">
        <div style="position: relative; height: 30px; overflow: hidden; border-radius: 999px;">
            <div style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">Group</div>
            <div style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">Country</div>
            <div id="scopePill" style="position: absolute; left: 2px; top: 1px; width: 84px; height: 28px; border-radius: 999px; background: #D6C2F8; display: flex; align-items: center; justify-content: center; z-index: 3; color: #1F1530; font-weight: 700; font-size: 12px; transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);">Group</div>
            <button id="groupBtn" type="button" style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">Group</button>
            <button id="countryBtn" type="button" style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">Country</button>
        </div>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(scope_toggle_html))

    year_toggle_html = '''
    <div id="yearToggle" style="position: fixed; top: 168px; right: 10px; z-index: 9999; width: 178px; background: #242424; border: 2px solid #9D4EDD; border-radius: 999px; padding: 4px; box-sizing: border-box; user-select: none;">
        <div style="position: relative; height: 30px; overflow: hidden; border-radius: 999px;">
            <div style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">2020</div>
            <div style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">2024</div>
            <div id="yearTogglePill" style="position: absolute; left: 2px; top: 1px; width: 84px; height: 28px; border-radius: 999px; background: #D6C2F8; display: flex; align-items: center; justify-content: center; z-index: 3; color: #1F1530; font-weight: 700; font-size: 12px; transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);">2024</div>
            <button id="year2020Btn" type="button" style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">2020</button>
            <button id="year2024Btn" type="button" style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">2024</button>
        </div>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(year_toggle_html))

    theme_toggle_html = '''
    <div id="themeToggle" style="position: fixed; top: 244px; right: 10px; z-index: 9999; width: 178px; background: #242424; border: 2px solid #9D4EDD; border-radius: 999px; padding: 4px; box-sizing: border-box; user-select: none;">
        <div style="position: relative; height: 30px; overflow: hidden; border-radius: 999px;">
            <div style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">Light</div>
            <div style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 1; color: #CFAEF4; font-weight: 700; font-size: 12px;">Dark</div>
            <div id="themeTogglePill" style="position: absolute; left: 2px; top: 1px; width: 84px; height: 28px; border-radius: 999px; background: #D6C2F8; display: flex; align-items: center; justify-content: center; z-index: 3; color: #1F1530; font-weight: 700; font-size: 12px; transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);">Dark</div>
            <button id="themeLightBtn" type="button" style="position: absolute; left: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">Light</button>
            <button id="themeDarkBtn" type="button" style="position: absolute; right: 0; top: 0; width: 84px; height: 30px; border: none; background: transparent; color: transparent; z-index: 4; cursor: pointer;">Dark</button>
        </div>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(theme_toggle_html))

    stats_bars_html = '''
    <div id="statsContainer" style="position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; width: 90%; max-width: 600px; background: #242424; border: 2px solid #9D4EDD; border-radius: 10px; padding: 12px; display: none; box-sizing: border-box;">
        <div style="position: relative; margin-bottom: 8px; min-height: 22px;">
            <div style="font-size: 11px; color: #B59FFF; font-weight: 600; text-align: center;">Election Statistics</div>
            <button id="statsToggleBtn" type="button" aria-label="Collapse statistics" title="Collapse statistics" style="display:none; position:absolute; right:0; top:50%; transform:translateY(-50%); width:22px; height:22px; background:#1a1a1a; color:#E0AAFF; border:1px solid #9D4EDD; border-radius:6px; padding:0; font-size:11px; font-weight:700; line-height:1; cursor:pointer;">&#9660;</button>
        </div>

        <div id="statsPanelContent">
        <div style="margin-bottom: 10px;">
            <div style="font-size: 10px; color: #9D4EDD; margin-bottom: 4px;">Overall Vote: </div>
            <div style="display: flex; align-items: center; height: 24px; background: #1a1a1a; border-radius: 4px; overflow: hidden;">
                <div id="voteBarDem" style="background: #1f77ff; height: 100%; flex: 0; display: flex; align-items: center; justify-content: center; font-size: 9px; color: #ffffff; min-width: 0; transition: flex 0.3s ease;"></div>
                <div style="background: #ffffff; width: 2px; height: 100%; flex: 0 0 auto;"></div>
                <div id="voteBarRep" style="background: #ff2b2b; height: 100%; flex: 0; display: flex; align-items: center; justify-content: center; font-size: 9px; color: #ffffff; min-width: 0; transition: flex 0.3s ease;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 9px; color: #B59FFF; margin-top: 3px;">
                <span id="voteCountDem"></span>
                <span id="voteCountRep"></span>
            </div>
        </div>

        <div id="countiesSection" style="margin-bottom: 0;">
            <div style="font-size: 10px; color: #9D4EDD; margin-bottom: 4px;">Counties Won: </div>
            <div style="display: flex; align-items: center; height: 24px; background: #1a1a1a; border-radius: 4px; overflow: hidden;">
                <div id="countyBarDem" style="background: #1f77ff; height: 100%; flex: 0; display: flex; align-items: center; justify-content: center; font-size: 9px; color: #ffffff; font-weight: 600; min-width: 0; transition: flex 0.3s ease;"></div>
                <div style="background: #ffffff; width: 2px; height: 100%; flex: 0 0 auto;"></div>
                <div id="countyBarRep" style="background: #ff2b2b; height: 100%; flex: 0; display: flex; align-items: center; justify-content: center; font-size: 9px; color: #ffffff; font-weight: 600; min-width: 0; transition: flex 0.3s ease;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 9px; color: #B59FFF; margin-top: 3px;">
                <span id="countyCountDem"></span>
                <span id="countyCountRep"></span>
            </div>
        </div>
        </div>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(stats_bars_html))

    slider_script = f'''
    <script>
    (function() {{
        var mapVar = "{m.get_name()}";
        var stateVar = "{state_layer.get_name()}";
        var countyVar = "{county_layer.get_name()}";
        var countryStateOptions = {json.dumps(available_states)};
        var groupStateOptions = {json.dumps(group_filter_states)};
        var groupBounds = [[{group_bounds[1]}, {group_bounds[0]}], [{group_bounds[3]}, {group_bounds[2]}]];
        var countryBounds = [[{country_bounds[1]}, {country_bounds[0]}], [{country_bounds[3]}, {country_bounds[2]}]];

        function initSlider() {{
            var mapObj = window[mapVar];
            var stateLayer = window[stateVar];
            var countyLayer = window[countyVar];
            var pill = document.getElementById('togglePill');
            var stateBtn = document.getElementById('stateBtn');
            var countyBtn = document.getElementById('countyBtn');
            var colorModeSelect = document.getElementById('colorModeSelect');
            var stateFilterSelect = document.getElementById('stateFilterSelect');
            var dataModePill = document.getElementById('dataModePill');
            var yearModeBtn = document.getElementById('yearModeBtn');
            var changeModeBtn = document.getElementById('changeModeBtn');
            var scopePill = document.getElementById('scopePill');
            var groupBtn = document.getElementById('groupBtn');
            var countryBtn = document.getElementById('countryBtn');
            var yearToggle = document.getElementById('yearToggle');
            var yearPill = document.getElementById('yearTogglePill');
            var year2020Btn = document.getElementById('year2020Btn');
            var year2024Btn = document.getElementById('year2024Btn');
            var themePill = document.getElementById('themeTogglePill');
            var themeLightBtn = document.getElementById('themeLightBtn');
            var themeDarkBtn = document.getElementById('themeDarkBtn');
            var statsToggleBtn = document.getElementById('statsToggleBtn');

            if (!mapObj || !stateLayer || !countyLayer || !pill || !stateBtn || !countyBtn || !colorModeSelect || !stateFilterSelect || !dataModePill || !yearModeBtn || !changeModeBtn || !scopePill || !groupBtn || !countryBtn || !yearToggle || !yearPill || !year2020Btn || !year2024Btn || !themePill || !themeLightBtn || !themeDarkBtn || !statsToggleBtn) {{
                return false;
            }}

            var activeColorMode = 'winner';
            var activeStateFilter = 'ALL';
            var activeDataMode = 'year';
            var activeScope = 'group';
            var activeViewMode = 'state';
            var activeYear = '2024';
            var activeTheme = 'dark';
            var statsCollapsed = false;

            function setStatsCollapsed(collapsed) {{
                var statsPanelContent = document.getElementById('statsPanelContent');
                if (!statsPanelContent) return;
                statsCollapsed = !!collapsed;
                statsPanelContent.style.display = statsCollapsed ? 'none' : 'block';
                statsToggleBtn.innerHTML = statsCollapsed ? '&#9650;' : '&#9660;';
                statsToggleBtn.setAttribute('aria-label', statsCollapsed ? 'Expand statistics' : 'Collapse statistics');
                statsToggleBtn.setAttribute('title', statsCollapsed ? 'Expand statistics' : 'Collapse statistics');
            }}

            function matchesStateFilter(props) {{
                if (activeStateFilter === 'ALL') return true;
                return !!(props && props.state === activeStateFilter);
            }}

            function refreshStateFilterOptions(forceAll) {{
                var options = (activeScope === 'group') ? groupStateOptions : countryStateOptions;
                var previousValue = activeStateFilter;
                var html = '<option value="ALL">All States</option>';
                options.forEach(function(abbr) {{
                    html += '<option value="' + abbr + '">' + abbr + '</option>';
                }});
                stateFilterSelect.innerHTML = html;

                var canKeepSelection = !forceAll && previousValue !== 'ALL' && options.indexOf(previousValue) !== -1;
                activeStateFilter = canKeepSelection ? previousValue : 'ALL';
                stateFilterSelect.value = activeStateFilter;
            }}

            function isInScope(props) {{
                if (activeScope === 'country') return true;
                return !!(props && props.in_group);
            }}

            function syncFeaturePropertiesToYear(layer) {{
                if (!layer || !layer.feature || !layer.feature.properties) return;
                var props = layer.feature.properties;
                var suffix = '_' + activeYear;

                if (activeDataMode === 'change') {{
                    props.democrat_display = props.democrat_change_display || '+0.0%';
                    props.republican_display = props.republican_change_display || '+0.0%';
                    props.third_party_display = props.third_party_change_display || '+0.0%';
                }} else {{
                    props.democrat_display = props['democrat_display' + suffix] || '0 (0.0%)';
                    props.republican_display = props['republican_display' + suffix] || '0 (0.0%)';
                    props.third_party_display = props['third_party_display' + suffix] || '0 (0.0%)';
                }}

                props.winner_color = props['winner_color_' + activeTheme + suffix] || props.winner_color || '#7f5fbf';
                props.gradient_color = props['gradient_color_' + activeTheme + suffix] || props.gradient_color || '#7f5fbf';
                props.voting_color = props['voting_color_' + activeTheme + suffix] || props.voting_color || '#7f5fbf';
                props.change_color = props['change_color_' + activeTheme] || props.change_color || '#9a9a9a';
            }}

            function applyTheme(theme) {{
                activeTheme = theme;
                var container = mapObj.getContainer();
                var mapPane = mapObj.getPane && mapObj.getPane('mapPane');

                if (theme === 'light') {{
                    themePill.style.transform = 'translateX(0px)';
                    themePill.textContent = 'Light';
                    container.style.setProperty('background-color', '#e8dbc6', 'important');
                    if (mapPane) {{
                        mapPane.style.setProperty('background-color', '#e8dbc6', 'important');
                    }}
                    document.body.style.backgroundColor = '#e8dbc6';
                }} else {{
                    themePill.style.transform = 'translateX(88px)';
                    themePill.textContent = 'Dark';
                    container.style.setProperty('background-color', '#1a1a1a', 'important');
                    if (mapPane) {{
                        mapPane.style.setProperty('background-color', '#1a1a1a', 'important');
                    }}
                    document.body.style.backgroundColor = '#1a1a1a';
                }}

                applyColorMode(activeColorMode);
            }}

            function styleFeatureLayer(layer, isCountyLayer, isHover) {{
                if (!layer || !layer.feature || !layer.feature.properties) return;
                var props = layer.feature.properties;

                if (isCountyLayer && props.hide_in_county_view) {{
                    if (layer._path) {{
                        layer._path.style.display = 'none';
                    }}
                    return;
                }}

                if (!matchesStateFilter(props)) {{
                    if (layer._path) {{
                        layer._path.style.display = 'none';
                    }}
                    return;
                }}

                if (!isInScope(props)) {{
                    if (layer._path) {{
                        layer._path.style.display = 'none';
                    }}
                    return;
                }}
                if (layer._path) {{
                    layer._path.style.display = '';
                }}

                var key = (activeDataMode === 'change') ? 'change_color' : (activeColorMode + '_color');
                var color = props[key] || props.gradient_color || '#7f5fbf';
                var strokeColor = (activeTheme === 'light') ? '#000000' : color;

                // Keep outlines from looking too thick at low zoom levels.
                var zoom = (mapObj && mapObj.getZoom) ? mapObj.getZoom() : 6;
                var weightScale = Math.max(0.35, Math.min(1.0, zoom / 6.0));

                // In county mode, keep state outlines thick but neutral (no election color).
                if (!isCountyLayer && activeViewMode === 'county') {{
                    color = (activeTheme === 'light') ? '#ffffff' : '#9a9a9a';
                    strokeColor = (activeTheme === 'light') ? '#000000' : color;
                }}

                var baseWeight = (isCountyLayer ? 1.1 : 2.5) * weightScale;
                var hoverWeight = (isCountyLayer ? 1.8 : 3.5) * weightScale;
                var baseFill = (!isCountyLayer && activeViewMode === 'county') ? 0.0 : 0.2;
                var hoverFill = (!isCountyLayer && activeViewMode === 'county') ? 0.0 : 0.35;

                layer.setStyle({{
                    fillColor: color,
                    color: strokeColor,
                    weight: isHover ? hoverWeight : baseWeight,
                    fillOpacity: isHover ? hoverFill : baseFill
                }});
            }}

            function bindHoverHandlers(layerGroup, isCountyLayer) {{
                if (!layerGroup || !layerGroup.eachLayer) return;
                layerGroup.eachLayer(function(layer) {{
                    if (!layer || layer.__hoverBound) return;
                    layer.__hoverBound = true;
                    layer.on('mouseover', function() {{
                        styleFeatureLayer(layer, isCountyLayer, true);
                    }});
                    layer.on('mouseout', function() {{
                        styleFeatureLayer(layer, isCountyLayer, false);
                    }});
                }});
            }}

            function applyColorMode(mode) {{
                activeColorMode = mode;
                if (stateLayer.eachLayer) {{
                    stateLayer.eachLayer(function(layer) {{
                        syncFeaturePropertiesToYear(layer);
                        styleFeatureLayer(layer, false, false);
                        if (layer.closeTooltip) layer.closeTooltip();
                    }});
                }}
                if (countyLayer.eachLayer) {{
                    countyLayer.eachLayer(function(layer) {{
                        syncFeaturePropertiesToYear(layer);
                        styleFeatureLayer(layer, true, false);
                        if (layer.closeTooltip) layer.closeTooltip();
                    }});
                }}
                updateStatsBar();
            }}

            function refreshStylesForZoom() {{
                if (stateLayer.eachLayer) {{
                    stateLayer.eachLayer(function(layer) {{
                        syncFeaturePropertiesToYear(layer);
                        styleFeatureLayer(layer, false, false);
                    }});
                }}
                if (countyLayer.eachLayer) {{
                    countyLayer.eachLayer(function(layer) {{
                        syncFeaturePropertiesToYear(layer);
                        styleFeatureLayer(layer, true, false);
                    }});
                }}
                updateStatsBar();
            }}

            function applyYear(year) {{
                activeYear = year;
                if (year === '2020') {{
                    yearPill.style.transform = 'translateX(0px)';
                    yearPill.textContent = '2020';
                }} else {{
                    yearPill.style.transform = 'translateX(88px)';
                    yearPill.textContent = '2024';
                }}
                if (activeDataMode === 'change') {{
                    return;
                }}
                applyColorMode(activeColorMode);
                updateStatsBar();
            }}

            function setDataMode(mode) {{
                activeDataMode = mode;

                if (mode === 'change') {{
                    dataModePill.style.transform = 'translateX(88px)';
                    dataModePill.textContent = 'Swing';
                    yearToggle.style.opacity = '0.55';
                    yearToggle.style.pointerEvents = 'none';
                    colorModeSelect.style.opacity = '0.55';
                    colorModeSelect.style.pointerEvents = 'none';
                }} else {{
                    dataModePill.style.transform = 'translateX(0px)';
                    dataModePill.textContent = 'Year';
                    yearToggle.style.opacity = '1';
                    yearToggle.style.pointerEvents = 'auto';
                    colorModeSelect.style.opacity = '1';
                    colorModeSelect.style.pointerEvents = 'auto';
                }}

                applyColorMode(activeColorMode);
            }}

            function setStatePointerEvents(enabled) {{
                if (!stateLayer.eachLayer) return;
                stateLayer.eachLayer(function(layer) {{
                    var inScope = !!(layer && layer.feature && layer.feature.properties && isInScope(layer.feature.properties) && matchesStateFilter(layer.feature.properties));
                    var shouldEnable = enabled && inScope;
                    if (layer.options) {{
                        layer.options.interactive = shouldEnable;
                    }}
                    if (layer._path) {{
                        layer._path.style.pointerEvents = shouldEnable ? 'auto' : 'none';
                    }}
                }});
            }}

            function setStateFillForMode(isCountyMode) {{
                if (!stateLayer.eachLayer) return;
                stateLayer.eachLayer(function(layer) {{
                    styleFeatureLayer(layer, false, false);
                }});
            }}

            function zoomToSelectedState() {{
                if (activeStateFilter === 'ALL' || !stateLayer.eachLayer) {{
                    return;
                }}
                var selectedBounds = null;
                stateLayer.eachLayer(function(layer) {{
                    if (!layer || !layer.feature || !layer.feature.properties) return;
                    if (layer.feature.properties.state !== activeStateFilter) return;
                    if (!layer.getBounds) return;
                    var b = layer.getBounds();
                    if (!b || !b.isValid || !b.isValid()) return;
                    if (!selectedBounds) {{
                        selectedBounds = b;
                    }} else {{
                        selectedBounds.extend(b);
                    }}
                }});
                if (selectedBounds && selectedBounds.isValid && selectedBounds.isValid()) {{
                    mapObj.fitBounds(selectedBounds, {{padding: [16, 16]}});
                }}
            }}

            function updateStatsBar() {{
                var statsContainer = document.getElementById('statsContainer');
                var countiesSection = document.getElementById('countiesSection');
                if (!statsContainer) return;

                // State mode with single state selected
                if (activeViewMode === 'state' && activeStateFilter !== 'ALL') {{
                    if (!stateLayer.eachLayer) {{
                        statsContainer.style.display = 'none';
                        return;
                    }}

                    var demVotes = 0;
                    var repVotes = 0;

                    stateLayer.eachLayer(function(layer) {{
                        if (!layer || !layer.feature || !layer.feature.properties) return;
                        var props = layer.feature.properties;

                        if (props.state !== activeStateFilter) return;

                        var suffix = '_' + activeYear;
                        var dem = parseInt(props['democrat_votes' + suffix] || 0);
                        var rep = parseInt(props['republican_votes' + suffix] || 0);

                        demVotes += dem;
                        repVotes += rep;
                    }});

                    var totalVotes = demVotes + repVotes;
                    var demVotesFlex = totalVotes > 0 ? (demVotes / totalVotes) * 100 : 50;
                    var repVotesFlex = totalVotes > 0 ? (repVotes / totalVotes) * 100 : 50;

                    var voteBarDem = document.getElementById('voteBarDem');
                    var voteBarRep = document.getElementById('voteBarRep');
                    var voteCountDem = document.getElementById('voteCountDem');
                    var voteCountRep = document.getElementById('voteCountRep');

                    if (voteBarDem) {{
                        voteBarDem.style.flex = demVotesFlex;
                        voteBarDem.textContent = demVotesFlex > 10 ? Math.round(demVotesFlex) + '%' : '';
                    }}
                    if (voteBarRep) {{
                        voteBarRep.style.flex = repVotesFlex;
                        voteBarRep.textContent = repVotesFlex > 10 ? Math.round(repVotesFlex) + '%' : '';
                    }}
                    if (voteCountDem) voteCountDem.textContent = 'D: ' + demVotes.toLocaleString();
                    if (voteCountRep) voteCountRep.textContent = 'R: ' + repVotes.toLocaleString();

                    // Hide county bars in state mode
                    if (countiesSection) countiesSection.style.display = 'none';
                    statsToggleBtn.style.display = 'none';
                    setStatsCollapsed(false);

                    statsContainer.style.display = 'block';
                    return;
                }}

                // County mode
                if (activeViewMode !== 'county' || !countyLayer.eachLayer) {{
                    statsContainer.style.display = 'none';
                    return;
                }}

                var demVotes = 0;
                var repVotes = 0;
                var demCounties = 0;
                var repCounties = 0;

                countyLayer.eachLayer(function(layer) {{
                    if (!layer || !layer.feature || !layer.feature.properties) return;
                    var props = layer.feature.properties;

                    if (props.hide_in_county_view) return;
                    if (!matchesStateFilter(props)) return;
                    if (!isInScope(props)) return;

                    var suffix = '_' + activeYear;
                    var dem = parseInt(props['democrat_votes' + suffix] || 0);
                    var rep = parseInt(props['republican_votes' + suffix] || 0);

                    demVotes += dem;
                    repVotes += rep;

                    if (dem > rep) {{
                        demCounties += 1;
                    }} else if (rep > dem) {{
                        repCounties += 1;
                    }}
                }});

                var totalVotes = demVotes + repVotes;
                var totalCounties = demCounties + repCounties;

                var demVotesFlex = totalVotes > 0 ? (demVotes / totalVotes) * 100 : 50;
                var repVotesFlex = totalVotes > 0 ? (repVotes / totalVotes) * 100 : 50;

                var demCountiesFlex = totalCounties > 0 ? (demCounties / totalCounties) * 100 : 50;
                var repCountiesFlex = totalCounties > 0 ? (repCounties / totalCounties) * 100 : 50;

                var voteBarDem = document.getElementById('voteBarDem');
                var voteBarRep = document.getElementById('voteBarRep');
                var countyBarDem = document.getElementById('countyBarDem');
                var countyBarRep = document.getElementById('countyBarRep');
                var voteCountDem = document.getElementById('voteCountDem');
                var voteCountRep = document.getElementById('voteCountRep');
                var countyCountDem = document.getElementById('countyCountDem');
                var countyCountRep = document.getElementById('countyCountRep');

                if (voteBarDem) {{
                    voteBarDem.style.flex = demVotesFlex;
                    voteBarDem.textContent = demVotesFlex > 10 ? Math.round(demVotesFlex) + '%' : '';
                }}
                if (voteBarRep) {{
                    voteBarRep.style.flex = repVotesFlex;
                    voteBarRep.textContent = repVotesFlex > 10 ? Math.round(repVotesFlex) + '%' : '';
                }}
                if (countyBarDem) {{
                    countyBarDem.style.flex = demCountiesFlex;
                    countyBarDem.textContent = demCounties > 0 ? demCounties : '';
                }}
                if (countyBarRep) {{
                    countyBarRep.style.flex = repCountiesFlex;
                    countyBarRep.textContent = repCounties > 0 ? repCounties : '';
                }}
                if (voteCountDem) voteCountDem.textContent = 'D: ' + demVotes.toLocaleString();
                if (voteCountRep) voteCountRep.textContent = 'R: ' + repVotes.toLocaleString();
                if (countyCountDem) countyCountDem.textContent = 'D: ' + demCounties;
                if (countyCountRep) countyCountRep.textContent = 'R: ' + repCounties;

                // Show county bars in county mode
                if (countiesSection) countiesSection.style.display = 'block';
                statsToggleBtn.style.display = 'inline-block';

                statsContainer.style.display = 'block';
            }}

            function setScope(mode) {{
                activeScope = mode;
                refreshStateFilterOptions(mode === 'country');
                if (mode === 'country') {{
                    scopePill.style.transform = 'translateX(88px)';
                    scopePill.textContent = 'Country';
                    mapObj.fitBounds(countryBounds, {{padding: [16, 16]}});
                }} else {{
                    scopePill.style.transform = 'translateX(0px)';
                    scopePill.textContent = 'Group';
                    mapObj.fitBounds(groupBounds, {{padding: [16, 16]}});
                }}

                setStatePointerEvents(activeViewMode === 'state');
                applyColorMode(activeColorMode);
                updateStatsBar();
            }}

            function setMode(mode) {{
                if (mode === 'county') {{
                    activeViewMode = 'county';
                    if (!mapObj.hasLayer(stateLayer)) mapObj.addLayer(stateLayer);
                    if (!mapObj.hasLayer(countyLayer)) mapObj.addLayer(countyLayer);
                    // Keep state boundaries visible, but let county hover/click win.
                    setStatePointerEvents(false);
                    setStateFillForMode(true);
                    if (countyLayer.bringToFront) countyLayer.bringToFront();
                    pill.style.transform = 'translateX(88px)';
                    pill.textContent = 'County';
                    updateStatsBar();
                }} else {{
                    activeViewMode = 'state';
                    if (mapObj.hasLayer(countyLayer)) mapObj.removeLayer(countyLayer);
                    if (!mapObj.hasLayer(stateLayer)) mapObj.addLayer(stateLayer);
                    // Restore state interactions in state-only mode.
                    setStatePointerEvents(true);
                    setStateFillForMode(false);
                    if (stateLayer.bringToFront) stateLayer.bringToFront();
                    pill.style.transform = 'translateX(0px)';
                    pill.textContent = 'State';
                    updateStatsBar();
                }}

                // Ensure scope-based visibility (group vs country) is reapplied on mode switch.
                applyColorMode(activeColorMode);
            }}

            stateBtn.addEventListener('click', function() {{ setMode('state'); }});
            countyBtn.addEventListener('click', function() {{ setMode('county'); }});
            colorModeSelect.addEventListener('change', function(e) {{
                applyColorMode(e.target.value);
            }});
            stateFilterSelect.addEventListener('change', function(e) {{
                activeStateFilter = e.target.value;
                setStatePointerEvents(activeViewMode === 'state');
                applyColorMode(activeColorMode);
                zoomToSelectedState();
                updateStatsBar();
            }});
            yearModeBtn.addEventListener('click', function() {{
                setDataMode('year');
            }});
            changeModeBtn.addEventListener('click', function() {{
                setDataMode('change');
            }});
            groupBtn.addEventListener('click', function() {{
                setScope('group');
            }});
            countryBtn.addEventListener('click', function() {{
                setScope('country');
            }});
            year2020Btn.addEventListener('click', function() {{
                applyYear('2020');
            }});
            year2024Btn.addEventListener('click', function() {{
                applyYear('2024');
            }});
            themeLightBtn.addEventListener('click', function() {{
                applyTheme('light');
            }});
            themeDarkBtn.addEventListener('click', function() {{
                applyTheme('dark');
            }});
            statsToggleBtn.addEventListener('click', function() {{
                if (activeViewMode !== 'county') return;
                setStatsCollapsed(!statsCollapsed);
            }});

            bindHoverHandlers(stateLayer, false);
            bindHoverHandlers(countyLayer, true);
            if (mapObj && mapObj.on) {{
                mapObj.on('zoomend', refreshStylesForZoom);
            }}

            setStatsCollapsed(false);
            applyTheme('dark');
            applyYear('2024');
            setDataMode('year');
            setMode('state');
            setScope('group');
            refreshStateFilterOptions(false);
            applyColorMode(colorModeSelect.value);
            return true;
        }}

        var tries = 0;
        var timer = setInterval(function() {{
            tries += 1;
            if (initSlider() || tries > 40) {{
                clearInterval(timer);
            }}
        }}, 75);
    }})();
    </script>
    '''
    m.get_root().html.add_child(folium.Element(slider_script))
    
    # Add title
    title_html = '''
    <div style="position: fixed; 
                top: 10px; left: 50px; width: 300px; height: 80px; 
                background-color: #2a2a2a; border:2px solid #9D4EDD; z-index:9999; 
                font-size:16px; font-weight: bold; padding: 10px; color: #E0AAFF; border-radius: 5px;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <b>East Coast Magic Wall</b><br>
        ME, NJ, NY, OH, PA, VA<br>
        <span style="font-size: 12px; font-weight: normal; color: #B59FFF;">
            2020/2024 election county and state view
        </span>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(title_html))
    
    return m, counties_group, states_country[states_country['state'].isin(TARGET_STATES)]

def main():
    """Main function to create both map levels"""
    print("Creating interactive TIGER-based map...")
    
    # Create state-level map
    state_map, counties_data, states_data = create_state_level_map()
    
    # Save state-level map
    state_map.save('state_level_map.html')
    print("✓ State-level map saved as 'state_level_map.html'")

    print("\nMaps created successfully!")
    print("\nOpen 'state_level_map.html' in your browser.")
    print("Use the top-right State/County slider to switch views.")

if __name__ == '__main__':
    main()
