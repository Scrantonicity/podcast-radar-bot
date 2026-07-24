"""place_coords.py — a bundled place -> [lat, lon] lookup for the globe.

Geocoding an archive would mean an API key, a network call per place, and a cache
to invalidate. Podcasts talk about the same few hundred places, so this table
covers them offline and gets out of the way. Anything it misses simply doesn't plot
(and `build_observatory.py --dry-run` lists it under UNGEOCODED, so a show can add
its own via `Observatory.extra_place_coords`).

Keys are the English `canonical_key` the extractor emits (extract.py's contract),
lowercased. Coordinates are country/city centroids at ~1-2 decimal places — enough
to place a dot on a 110m world map, not a survey.

Ported from the original single-show build. Dropped on the way: two gag entries pinned
at [0,0] (which is a real spot in the Gulf of Guinea, so they plotted a phantom dot
off Africa), three Hebrew-script keys (canonical_key is English by contract; a
show's own spellings belong in extra_place_coords), and street/building-level
entries that could only ever match one show's transcripts.
"""

PLACE_COORDS = {
    "abu dhabi": [24.45, 54.38], "addis ababa": [9.03, 38.74], "aden": [12.79, 45.03],
    "aegean sea": [38.9, 25.0], "afghanistan": [33.9, 67.7], "africa": [8.8, 21.1],
    "akko": [32.93, 35.08], "alaska": [64.2, -149.5], "alberta": [53.9, -116.6],
    "alexandria": [31.2, 29.92], "algeria": [28.0, 1.7], "amazon": [-3.4, -62.2],
    "amsterdam": [52.37, 4.9], "angola": [-11.2, 17.9], "ankara": [39.93, 32.86],
    "appalachian mountains": [37.0, -82.0], "argentina": [-38.4, -63.6],
    "arizona": [34.2, -111.7], "armenia": [40.1, 45.0], "asia": [34.0, 100.0],
    "astana": [51.16, 71.47], "athens": [37.98, 23.73], "australia": [-25.3, 133.8],
    "austria": [47.6, 14.1], "azerbaijan": [40.1, 47.6], "bab al mandab": [12.6, 43.4],
    "bab el mandeb": [12.6, 43.4], "bab el mandeb strait": [12.6, 43.4],
    "bahrain": [26.0, 50.5], "baku": [40.41, 49.87], "balkans": [42.0, 21.0],
    "bangkok": [13.76, 100.5], "bangladesh": [23.7, 90.4], "basel": [47.56, 7.59],
    "bay of pigs": [22.1, -81.1], "beijing": [39.9, 116.4], "belarus": [53.7, 27.95],
    "belgium": [50.6, 4.6], "berbera": [10.44, 45.01], "bering sea": [58.0, -178.0],
    "berlin": [52.52, 13.4], "black sea": [43.4, 34.3], "bolivia": [-16.3, -63.6],
    "bosphorus": [41.1, 29.07], "bosphorus strait": [41.1, 29.07],
    "boston": [42.36, -71.06], "brasilia": [-15.79, -47.88], "brazil": [-14.2, -51.9],
    "britain": [54.0, -2.5], "brussels": [50.85, 4.35], "bucharest": [44.43, 26.1],
    "budapest": [47.5, 19.04], "bulgaria": [42.7, 25.5], "burma": [21.9, 95.96],
    "california": [36.8, -119.4], "cambodia": [12.6, 104.9],
    "camp david": [39.65, -77.47], "camp lemonnier": [11.55, 43.16],
    "canada": [56.1, -106.3], "caracas": [10.48, -66.9], "caspian sea": [41.7, 50.7],
    "castel gandolfo": [41.75, 12.65], "catalonia": [41.8, 1.5],
    "caucasus": [42.5, 44.0], "ceyhan port": [36.99, 35.82], "chechnya": [43.3, 45.7],
    "chernobyl": [51.28, 30.22], "chiapas": [16.7, -92.6], "chile": [-35.7, -71.5],
    "china": [35.9, 104.2], "colombia": [4.6, -74.3], "congo": [-4.0, 21.8],
    "crimea": [45.3, 34.4], "croatia": [45.1, 15.2], "cuba": [21.5, -77.8],
    "cyprus": [35.1, 33.4], "czech republic": [49.8, 15.5], "damascus": [33.51, 36.29],
    "dardanelles": [40.2, 26.4], "davos": [46.8, 9.83], "dead sea": [31.5, 35.5],
    "democratic republic of congo": [-4.0, 21.8],
    "democratic republic of the congo": [-4.0, 21.8], "denmark": [56.0, 9.5],
    "dimona": [31.07, 35.03], "djibouti": [11.6, 43.1], "doha": [25.29, 51.53],
    "donetsk": [48.0, 37.8], "dubai": [25.2, 55.3], "east asia": [34.0, 118.0],
    "egypt": [26.8, 30.8], "eilat": [29.56, 34.95], "el salvador": [13.8, -88.9],
    "england": [52.5, -1.5], "eritrea": [15.2, 39.8], "ethiopia": [9.1, 40.5],
    "euphrates river": [34.0, 40.0], "europe": [54.5, 15.3], "finland": [64.0, 26.0],
    "florida": [27.8, -81.7], "fordow": [34.88, 50.99], "france": [46.6, 2.2],
    "french guiana": [3.9, -53.1], "fukushima": [37.75, 140.47], "gabon": [-0.8, 11.6],
    "gaza": [31.5, 34.47], "gaza city": [31.5, 34.47], "gaza strip": [31.5, 34.47],
    "geneva": [46.2, 6.14], "georgia": [42.3, 43.4], "germany": [51.2, 10.4],
    "golan heights": [33.0, 35.75], "great britain": [54.0, -2.5],
    "greece": [39.0, 22.0], "greenland": [71.7, -42.6], "guatemala": [15.8, -90.2],
    "gulf": [26.5, 51.5], "gulf of aden": [12.0, 48.0], "gulf of mexico": [25.0, -90.0],
    "gush katif": [31.35, 34.27], "hagia sophia": [41.01, 28.98],
    "haifa": [32.79, 34.99], "havana": [23.11, -82.37], "hawaii": [20.8, -156.3],
    "herzliya": [32.16, 34.84], "hollywood": [34.09, -118.33],
    "hong kong": [22.3, 114.2], "hormuz": [26.57, 56.25], "horn of africa": [8.0, 48.0],
    "hungary": [47.2, 19.5], "ibiza": [38.98, 1.43], "iceland": [64.9, -19.0],
    "idlib": [35.93, 36.63], "india": [22.0, 79.0], "indian ocean": [-20.0, 80.0],
    "indonesia": [-2.5, 118.0], "iran": [32.4, 53.7], "iraq": [33.2, 43.7],
    "ireland": [53.4, -8.2], "israel": [31.5, 34.9], "istanbul": [41.0, 28.98],
    "italy": [42.8, 12.8], "japan": [36.2, 138.3], "jenin": [32.46, 35.3],
    "jerusalem": [31.78, 35.22], "jordan": [30.6, 36.2],
    "judea and samaria": [32.0, 35.3], "kaliningrad": [54.71, 20.45],
    "kashmir": [34.08, 74.8], "kazakhstan": [48.0, 66.9], "kenya": [-0.0, 37.9],
    "kharg island": [29.23, 50.32], "kingdom of saudi arabia": [24.0, 45.0],
    "kiryat tivon": [32.72, 35.12], "koh phangan": [9.75, 100.02],
    "koh samui": [9.51, 100.01], "korea": [37.5, 127.5], "kremlin": [55.75, 37.62],
    "kurdistan": [36.5, 44.0], "kuwait": [29.3, 47.5], "kyiv": [50.45, 30.52],
    "laos": [19.86, 102.5], "lebanon": [33.9, 35.9], "lesbos": [39.25, 26.28],
    "libya": [26.3, 17.2], "london": [51.51, -0.13], "los alamos": [35.88, -106.3],
    "los angeles": [34.05, -118.24], "lubang island": [13.83, 120.13],
    "lugano": [46.0, 8.95], "malaysia": [4.2, 101.9], "mallorca": [39.6, 3.0],
    "malmo": [55.6, 13.0], "manchuria": [45.0, 125.0], "mecca": [21.42, 39.83],
    "mecca and medina": [22.9, 39.7], "medina": [24.47, 39.61],
    "mediterranean": [35.0, 18.0], "mediterranean sea": [35.0, 18.0],
    "mexico": [23.6, -102.6], "michigan": [44.3, -85.6], "middle east": [29.3, 42.5],
    "minneapolis": [44.98, -93.27], "minnesota": [46.3, -94.3],
    "mississippi river": [32.3, -90.9], "mogadishu": [2.05, 45.34],
    "monaco": [43.73, 7.42], "mongolia": [46.9, 103.8], "morocco": [31.8, -7.1],
    "moscow": [55.75, 37.62], "mount hermon": [33.42, 35.85],
    "mount scopus": [31.79, 35.24], "munich": [48.14, 11.58], "myanmar": [21.9, 95.96],
    "nagorno karabakh": [39.8, 46.6], "negev": [30.6, 34.85], "neom": [28.0, 35.3],
    "nepal": [28.4, 84.1], "ness ziona": [31.93, 34.8], "netherlands": [52.1, 5.3],
    "new administrative capital of egypt": [30.0, 31.7], "new delhi": [28.61, 77.21],
    "new york": [40.71, -74.0], "new zealand": [-41.0, 174.9], "niger": [17.6, 8.08],
    "nigeria": [9.1, 8.7], "nile": [26.0, 32.0], "nile river": [26.0, 32.0],
    "north africa": [28.0, 15.0], "north korea": [40.3, 127.5],
    "north sea": [56.0, 3.0], "norway": [60.5, 8.5], "odesa": [46.48, 30.72],
    "okinawa": [26.5, 128.0], "oman": [21.5, 55.9], "pai": [19.36, 98.44],
    "pakistan": [30.4, 69.3], "palestine": [31.9, 35.2], "palo alto": [37.44, -122.14],
    "panama canal": [9.08, -79.68], "paraguay": [-23.4, -58.4], "paris": [48.85, 2.35],
    "pearl harbor": [21.36, -157.95], "persia": [32.4, 53.7],
    "persian gulf": [26.5, 51.5], "peru": [-9.2, -75.0],
    "philadelphi corridor": [31.24, 34.25], "philippines": [12.9, 121.8],
    "phuket": [7.88, 98.39], "poland": [52.0, 19.1], "portugal": [39.5, -8.0],
    "prussia": [52.5, 13.4], "puerto rico": [18.2, -66.5], "qatar": [25.3, 51.2],
    "quebec": [52.9, -73.5], "ramat david": [32.67, 35.18],
    "ramstein air base": [49.44, 7.6], "red sea": [20.3, 38.0],
    "rehovot": [31.9, 34.81], "riyadh": [24.71, 46.68], "romania": [45.9, 24.9],
    "rome": [41.9, 12.5], "rotherham": [53.43, -1.36], "rotterdam": [51.92, 4.48],
    "russia": [61.5, 105.3], "rwanda": [-1.94, 29.87],
    "sabra and shatila": [33.85, 35.5], "sahel region": [15.0, 10.0],
    "salt lake city": [40.76, -111.89], "san diego": [32.72, -117.16],
    "san francisco": [37.77, -122.42], "saudi arabia": [24.0, 45.0],
    "scandinavia": [63.0, 16.0], "sea of galilee": [32.8, 35.6], "serbia": [44.0, 21.0],
    "sevastopol": [44.62, 33.53], "shanghai": [31.23, 121.47],
    "sharm el sheikh": [27.91, 34.33], "sierra maestra": [20.0, -76.8],
    "silicon valley": [37.39, -122.08], "sinai": [29.5, 33.9],
    "sinai peninsula": [29.5, 33.9], "singapore": [1.35, 103.8], "sochi": [43.6, 39.73],
    "somalia": [5.15, 46.2], "somaliland": [9.4, 46.6], "south africa": [-30.6, 22.9],
    "south china sea": [12.0, 114.0], "south dakota": [44.4, -100.2],
    "south korea": [36.5, 127.8], "south yemen": [14.0, 46.0],
    "soviet union": [55.8, 49.0], "spain": [40.0, -4.0], "sparta": [37.07, 22.43],
    "sri lanka": [7.87, 80.77], "strait of hormuz": [26.57, 56.25],
    "strait of malacca": [2.5, 101.3], "sudan": [12.9, 30.2],
    "suez canal": [30.5, 32.35], "surat thani": [9.14, 99.33], "sweden": [60.1, 18.6],
    "switzerland": [46.8, 8.2], "syria": [34.8, 38.9], "tahrir square": [30.04, 31.24],
    "taiwan": [23.7, 121.0], "tartus": [34.89, 35.89], "tehran": [35.69, 51.39],
    "tel aviv": [32.08, 34.78], "temple mount": [31.78, 35.24], "texas": [31.5, -99.3],
    "thailand": [15.9, 100.9], "tigris river": [34.0, 44.0], "tivon": [32.72, 35.12],
    "tokyo": [35.68, 139.69], "tuapse": [44.1, 39.08], "tunisia": [33.9, 9.5],
    "turkey": [39.0, 35.2], "turkish republic of northern cyprus": [35.3, 33.9],
    "turkmenistan": [38.97, 59.56], "uae": [23.4, 53.8], "uk": [54.0, -2.5],
    "ukraine": [48.4, 31.2], "united arab emirates": [23.4, 53.8],
    "united kingdom": [54.0, -2.5], "united states": [39.0, -98.0],
    "uruguay": [-32.5, -55.8], "usa": [39.0, -98.0], "ussr": [55.8, 49.0],
    "utah": [39.3, -111.7], "venezuela": [6.4, -66.6], "venice": [45.44, 12.34],
    "vienna": [48.21, 16.37], "vietnam": [14.1, 108.3], "virginia": [37.5, -78.7],
    "vladivostok": [43.12, 131.89], "wall street": [40.71, -74.01],
    "warsaw": [52.23, 21.01], "washington": [38.9, -77.0],
    "washington dc": [38.9, -77.0], "west bank": [32.0, 35.3], "wuhan": [30.59, 114.31],
    "yanbu": [24.02, 38.06], "yavne": [31.88, 34.74], "yemen": [15.6, 48.0],
    "yokneam": [32.66, 35.11], "zambia": [-13.1, 27.85], "zaporizhzhia": [47.84, 35.14],
    "zurich": [47.37, 8.54],
}

KEY_ALIASES = {
    "america": "united states", "the united states": "united states",
    "united states of america": "united states",
}


def lookup(key, name="", extra=None, aliases=None):
    """Resolve one place to [lat, lon], or None if we can't place it.

    `extra` and `aliases` come from the show's Observatory and win over the bundled
    table, so a show can both add places and correct one it disagrees with.
    """
    k = (key or name or "").strip().lower()
    if not k:
        return None
    k = (aliases or {}).get(k, KEY_ALIASES.get(k, k))
    extra = extra or {}
    if k in extra:
        return list(extra[k])
    coord = PLACE_COORDS.get(k)
    return list(coord) if coord else None
