import json
from pathlib import Path

import geopandas as gpd
import folium

# States to include
TARGET_STATES = ['NY', 'NJ', 'PA', 'ME', 'VA']
STATE_FIPS = {
    'NY': '36',
    'NJ': '34',
    'PA': '42',
    'ME': '23',
    'VA': '51'
}

BASE_DIR = Path(__file__).resolve().parent
STATE_VOTES_FILE_2024 = BASE_DIR / 'data' / 'states_votes_2024.json'
STATE_VOTES_FILE_2020 = BASE_DIR / 'data' / 'states_votes_2020.json'
COUNTY_VOTES_DIR = BASE_DIR / 'data' / 'counties'

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


def vote_color(democrat_votes, republican_votes):
    """Interpolate between red (R) and blue (D) by D/(D+R)."""
    dem = max(0, int(democrat_votes or 0))
    rep = max(0, int(republican_votes or 0))
    total = dem + rep

    # If no data, use midpoint purple.
    ratio_dem = 0.5 if total == 0 else dem / total

    # Increase contrast so gradient differences are more visually drastic.
    contrast = 1.8
    ratio_dem = max(0.0, min(1.0, 0.5 + (ratio_dem - 0.5) * contrast))

    # Use a brighter interpolation range so gradient colors pop on dark background.
    low = 70
    high = 255
    red = int(low + (high - low) * (1 - ratio_dem))
    blue = int(low + (high - low) * ratio_dem)
    green = 20
    return f'#{red:02x}{green:02x}{blue:02x}'


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


def format_vote_with_pct(votes, total_votes):
    """Format vote count with percent of total region votes."""
    v = max(0, int(votes or 0))
    t = max(0, int(total_votes or 0))
    pct = 0.0 if t == 0 else (v / t) * 100.0
    return f"{v:,} ({pct:.1f}%)"

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
    
    fips_codes = list(STATE_FIPS.values())
    counties_filtered = counties[counties['state_fips'].isin(fips_codes)].copy()
    
    # Also load state boundaries at correct FIPS level for the 5 states
    states_filtered = counties_filtered.dissolve(by='state_fips', aggfunc='first').copy()
    states_filtered['state'] = states_filtered.index.map({v: k for k, v in STATE_FIPS.items()})

    # Load election data for both years.
    state_votes_by_year = {
        '2020': load_json_file(STATE_VOTES_FILE_2020),
        '2024': load_json_file(STATE_VOTES_FILE_2024)
    }
    county_votes_by_state_year = {
        year: {
            state: load_json_file(COUNTY_VOTES_DIR / f'{state}_votes_{year}.json')
            for state in TARGET_STATES
        }
        for year in ['2020', '2024']
    }
    
    # Calculate center and initial bounds
    bounds = get_state_bounds(states_filtered)
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
        .leaflet-control,
        .leaflet-tooltip,
        .leaflet-popup-content,
        .leaflet-popup-content-wrapper,
        #viewToggle,
        #yearToggle,
        #colorModeSelect {
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        }
        </style>'''
    ))
    
    # Create a GeoJson layer for states
    states_geojson = json.loads(states_filtered.to_json())
    
    # Add state metadata for labels/tooltips
    state_fips_list = list(states_filtered.index)
    for i, feature in enumerate(states_geojson['features']):
        feature['properties']['state_fips'] = state_fips_list[i]
        state_abbrev = states_filtered.loc[state_fips_list[i], 'state']
        feature['properties']['state'] = state_abbrev

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
            feature['properties'][f'gradient_color_{year}'] = vote_color(dem_votes, rep_votes)
            feature['properties'][f'winner_color_{year}'] = winner_color(dem_votes, rep_votes)
            feature['properties'][f'voting_color_{year}'] = voting_map_color(dem_votes, rep_votes)

        # Default active year at load is 2024.
        feature['properties']['democrat_display'] = feature['properties']['democrat_display_2024']
        feature['properties']['republican_display'] = feature['properties']['republican_display_2024']
        feature['properties']['third_party_display'] = feature['properties']['third_party_display_2024']
        feature['properties']['gradient_color'] = feature['properties']['gradient_color_2024']
        feature['properties']['winner_color'] = feature['properties']['winner_color_2024']
        feature['properties']['voting_color'] = feature['properties']['voting_color_2024']
    
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
            sticky=False
        ),
        name='State Boundaries'
    )
    state_layer.add_to(m)

    # County layer (toggle on/off from slider)
    counties_geojson = json.loads(counties_filtered.to_json())
    for feature in counties_geojson['features']:
        props = feature['properties']
        feature['properties']['county_name'] = props.get('NAME', 'Unknown')

        state_fips = str(props.get('STATEFP', '')).zfill(2)
        state_abbrev = next((k for k, v in STATE_FIPS.items() if v == state_fips), None)
        geoid = str(props.get('GEOID', ''))

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
            feature['properties'][f'gradient_color_{year}'] = vote_color(dem_votes, rep_votes)
            feature['properties'][f'winner_color_{year}'] = winner_color(dem_votes, rep_votes)
            feature['properties'][f'voting_color_{year}'] = voting_map_color(dem_votes, rep_votes)

        # Default active year at load is 2024.
        feature['properties']['democrat_display'] = feature['properties']['democrat_display_2024']
        feature['properties']['republican_display'] = feature['properties']['republican_display_2024']
        feature['properties']['third_party_display'] = feature['properties']['third_party_display_2024']
        feature['properties']['gradient_color'] = feature['properties']['gradient_color_2024']
        feature['properties']['winner_color'] = feature['properties']['winner_color_2024']
        feature['properties']['voting_color'] = feature['properties']['voting_color_2024']

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
            sticky=False
        ),
        name='County Overlay',
        show=False
    )
    county_layer.add_to(m)

    # Custom top-right slider control for State/County toggle
    slider_control_html = '''
    <div id="viewToggle" style="position: fixed; top: 10px; right: 10px; z-index: 9999; width: 178px; background: #242424; border: 2px solid #9D4EDD; border-radius: 999px; padding: 4px; box-sizing: border-box; user-select: none;">
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
    <div style="position: fixed; top: 62px; right: 10px; z-index: 9999; background: #242424; border: 2px solid #9D4EDD; border-radius: 10px; padding: 8px; width: 178px; box-sizing: border-box;">
        <label for="colorModeSelect" style="display:block; color:#E0AAFF; font-size:12px; font-weight:700; margin-bottom:6px;">Color Mode</label>
        <select id="colorModeSelect" style="width:100%; background:#1a1a1a; color:#E0AAFF; border:1px solid #9D4EDD; border-radius:6px; padding:4px; font-size:12px;">
            <option value="winner" selected>Winner</option>
            <option value="gradient">Gradient</option>
            <option value="voting">Voting Map</option>
        </select>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(color_mode_control_html))

    year_toggle_html = '''
    <div id="yearToggle" style="position: fixed; top: 138px; right: 10px; z-index: 9999; width: 178px; background: #242424; border: 2px solid #9D4EDD; border-radius: 999px; padding: 4px; box-sizing: border-box; user-select: none;">
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

    slider_script = f'''
    <script>
    (function() {{
        var mapVar = "{m.get_name()}";
        var stateVar = "{state_layer.get_name()}";
        var countyVar = "{county_layer.get_name()}";

        function initSlider() {{
            var mapObj = window[mapVar];
            var stateLayer = window[stateVar];
            var countyLayer = window[countyVar];
            var pill = document.getElementById('togglePill');
            var stateBtn = document.getElementById('stateBtn');
            var countyBtn = document.getElementById('countyBtn');
            var colorModeSelect = document.getElementById('colorModeSelect');
            var yearPill = document.getElementById('yearTogglePill');
            var year2020Btn = document.getElementById('year2020Btn');
            var year2024Btn = document.getElementById('year2024Btn');

            if (!mapObj || !stateLayer || !countyLayer || !pill || !stateBtn || !countyBtn || !colorModeSelect || !yearPill || !year2020Btn || !year2024Btn) {{
                return false;
            }}

            var activeColorMode = 'winner';
            var activeViewMode = 'state';
            var activeYear = '2024';

            function syncFeaturePropertiesToYear(layer) {{
                if (!layer || !layer.feature || !layer.feature.properties) return;
                var props = layer.feature.properties;
                var suffix = '_' + activeYear;

                props.democrat_display = props['democrat_display' + suffix] || '0 (0.0%)';
                props.republican_display = props['republican_display' + suffix] || '0 (0.0%)';
                props.third_party_display = props['third_party_display' + suffix] || '0 (0.0%)';

                props.winner_color = props['winner_color' + suffix] || props.winner_color || '#7f5fbf';
                props.gradient_color = props['gradient_color' + suffix] || props.gradient_color || '#7f5fbf';
                props.voting_color = props['voting_color' + suffix] || props.voting_color || '#7f5fbf';
            }}

            function styleFeatureLayer(layer, isCountyLayer, isHover) {{
                if (!layer || !layer.feature || !layer.feature.properties) return;
                var props = layer.feature.properties;
                var key = activeColorMode + '_color';
                var color = props[key] || props.gradient_color || '#7f5fbf';

                // In county mode, keep state outlines thick but neutral (no election color).
                if (!isCountyLayer && activeViewMode === 'county') {{
                    color = '#9a9a9a';
                }}

                var baseWeight = isCountyLayer ? 1.1 : 2.5;
                var hoverWeight = isCountyLayer ? 1.8 : 3.5;
                var baseFill = (!isCountyLayer && activeViewMode === 'county') ? 0.0 : 0.2;
                var hoverFill = (!isCountyLayer && activeViewMode === 'county') ? 0.0 : 0.35;

                layer.setStyle({{
                    fillColor: color,
                    color: color,
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
                applyColorMode(activeColorMode);
            }}

            function setStatePointerEvents(enabled) {{
                if (!stateLayer.eachLayer) return;
                stateLayer.eachLayer(function(layer) {{
                    if (layer.options) {{
                        layer.options.interactive = enabled;
                    }}
                    if (layer._path) {{
                        layer._path.style.pointerEvents = enabled ? 'auto' : 'none';
                    }}
                }});
            }}

            function setStateFillForMode(isCountyMode) {{
                if (!stateLayer.eachLayer) return;
                stateLayer.eachLayer(function(layer) {{
                    if (!layer || !layer.feature || !layer.feature.properties) return;
                    var props = layer.feature.properties;
                    var key = activeColorMode + '_color';
                    var color = isCountyMode ? '#9a9a9a' : (props[key] || props.gradient_color || '#7f5fbf');
                    layer.setStyle({{
                        fillColor: color,
                        color: color,
                        weight: 2.5,
                        fillOpacity: isCountyMode ? 0.0 : 0.2,
                        opacity: 1.0
                    }});
                }});
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
                }}
            }}

            stateBtn.addEventListener('click', function() {{ setMode('state'); }});
            countyBtn.addEventListener('click', function() {{ setMode('county'); }});
            colorModeSelect.addEventListener('change', function(e) {{
                applyColorMode(e.target.value);
            }});
            year2020Btn.addEventListener('click', function() {{
                applyYear('2020');
            }});
            year2024Btn.addEventListener('click', function() {{
                applyYear('2024');
            }});

            bindHoverHandlers(stateLayer, false);
            bindHoverHandlers(countyLayer, true);

            applyYear('2024');
            applyColorMode(colorModeSelect.value);
            setMode('state');
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
                font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;">
        <b>East Coast Magic Wall</b><br>
        NY, NJ, PA, ME, VA<br>
        <span style="font-size: 12px; font-weight: normal; color: #B59FFF;">
            2020/2024 election county and state view
        </span>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(title_html))
    
    return m, counties_filtered, states_filtered

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
