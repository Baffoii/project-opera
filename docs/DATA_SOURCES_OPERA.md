# OPERA data sources and terms

OPERA = God's Eye View (GEV) + photo geolocation. This file (a) copies forward every
third-party source upstream uses, with its terms, and (b) adds OPERA's own sources.
Authoritative upstream text: [`DATA_SOURCES.md`](../DATA_SOURCES.md). The machine-readable
registry for OPERA's additions is `backend/registry/datasets.yaml` (created in M3/M5).

**Licensing is a human decision.** Anything below not marked as read in this session is
`needs_human_review`. OPERA does not download bulk datasets for training and never scrapes
Google Maps/Earth imagery.

## OPERA additions (V1)

| Source | OPERA use | Terms to record | license_status |
|---|---|---|---|
| God's Eye View (upstream) | 3D globe UI, public feeds | Code: MIT (`LICENSE` read in M0). Third-party data/assets keep their own terms (tables below). | code: read (MIT); data: see tables |
| GeoCLIP (`VicenteVivan/geo-clip`) | Geolocation baseline (adapter C) | Code **and** weights licenses recorded in `backend/registry/models.yaml` after the license files are read | needs_human_review |
| OSV-5M (`gastruc/osv5m`) | Fallback baseline / benchmark reference | Image-level rights; training and commercial-use terms | needs_human_review |
| OpenStreetMap / Nominatim | Reverse geocoding of candidates | ODbL 1.0 (attribution + share-alike). Nominatim usage policy: real User-Agent, <=1 req/s, cache results, no bulk geocoding. UI shows "© OpenStreetMap contributors" (panel + Cesium credit) when a name was used. Implemented in M4 (`backend/app/geo/context_provider.py`): only rounded predicted coordinates are sent; User-Agent contact must be set by the owner; not yet exercised against the public service. | needs_human_review |
| Overture Maps | Optional places/buildings context | Licenses vary per theme; not verified in this session | needs_human_review |
| OpenAI API (VLM clues) | Clue extraction from the sanitized, downscaled image only | OpenAI API terms; user content sent to a third party - see `docs/PRIVACY.md` | needs_human_review |
| Wikimedia Commons | Benchmark images (CC0/CC-BY only, manifest records license + author) | Per-file license; attribution required for CC-BY | needs_human_review |
| KartaView / Mapillary | Not used in V1 | Provider API terms; no assumed training rights | n/a |
| Sentinel-2 / Landsat | Not used in V1 | Attribution; resolution/timing limits | n/a |
| Google Maps / Earth | Optional display only (upstream feature) | Never used for training or scraping | n/a |
| Niantic Spatial | Not used in V1 | SDK access is not data export rights | n/a |

## Upstream sources (copied forward)

### Upstream live sources (copied forward from `DATA_SOURCES.md`; runtime-fetched, not stored)

| Source | Used for (upstream) | License / terms |
|---|---|---|
| **NOAA GFS (wind)** (`noaa-gfs-bdp-pds.s3.amazonaws.com`) | Global 10 m wind, optional 2 m temperature and mean sea-level pressure for Wind. Keyless; latest 6-hourly 0.25° cycle, byte-range GRIB2 reads, cached for an hour | U.S. public domain (NOAA); keyless via NOAA Open Data on AWS |
| **ECMWF IFS (wind)** (`data.ecmwf.int/forecasts`, ECMWF Open Data) | The alternative Wind model: 10 m wind, optional 2 m temperature and mean sea-level pressure. Keyless; latest 6-hourly 0.25° run, byte-range GRIB2 reads, cached for an hour | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) plus the [ECMWF Terms of Use](https://apps.ecmwf.int/datasets/licences/general/) |
| **NOAA nowCOAST observed weather** (`nowcoast.noaa.gov/geoserver/observations/{weather_radar,satellite}/ows`, WMS 1.1.1) | Rain radar (MRMS base reflectivity, contiguous US, about 4-minute updates) and Satellite clouds (GOES-19/18 Band 14 regional infrared, about 5-minute updates; global infrared mosaic, hourly). Keyless; layer metadata refreshed every 2 minutes, exact-time images cached for up to 24 hours | [NOAA disclaimer](https://oceanservice.noaa.gov/disclaimer.html) |
| **NOAA nowCOAST lightning density** (`nowcoast.noaa.gov/geoserver/observations/lightning_detection/ows`) | Lightning density: 15-minute accumulated strike density on an approximately 8 km grid, Americas and Pacific. Keyless; layer metadata refreshed every 10 minutes, exact-time images cached for up to 24 hours | NOAA Level-5 derived product from Vaisala NLDN/GLD360; the [product description](https://ocean.weather.gov/lightning/lightning_pdd.php) permits public distribution of this density product, not of raw Vaisala detections |
| **NOAA NHC / CPHC advisories** (`www.nhc.noaa.gov/CurrentStorms.json` + the `mapservices.weather.noaa.gov` tropical weather summary MapServer) | Cyclone advisories: storm positions, forecast tracks, points and cones for the Atlantic and eastern/central North Pacific. Keyless through `/api/cyclones`; cached for 5 minutes | [NWS public-data terms](https://www.weather.gov/disclaimer); no endorsement implied |
| **Mapillary** (vector tiles, Graph API, MapillaryJS) | Street Level: coverage lines, image cones and the embedded viewer. Coverage tiles cached for 24 h | Imagery [CC BY-SA 4.0](https://www.mapillary.com/terms); API under the Mapillary terms with a client token |
| **Google Street View** (Maps JavaScript API) | Street Level, on the Google 3D map only (Google's terms): Google's panorama viewer and nearest-panorama lookups; panorama dates and addresses kept for the session only | Google Maps Platform ToS (your own key + billing; every panorama load is billed) |
| **KartaView** (`api.kartaview.org` coverage tiles and photo API, `cdn.kartaview.org` image proxy, `storage*.openstreetcam.org` photos) | Street Level: coverage lines (z13–14 JSON tiles; with the imagery filter on, KartaView's filtered PNG tiles as a mask), nearest-photo lookups, the photo's sequence and the photo itself, fetched by the browser. Keyless; nothing cached beyond the session | Imagery [CC BY-SA 4.0](https://kartaview.org/terms) (KartaView terms §4); the public API needs no token |
| **OpenStreetMap** | Map and place data (roads, military areas and names, ALPR, place search, outlines); via vector tiles, hourly ALPR extract, bundled data, Nominatim and optional self-configured Overpass | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| **Google Map Tiles API** (Photorealistic 3D Tiles) + Places/Geocoding | The 3D globe, voice scene context, and on-demand nearby installation search | Google Maps Platform ToS (proprietary, your own key + billing) |
| **OpenSky Network** | Primary worldwide live-flight snapshot | Non-commercial research/education license |
| **adsb.lol point API** | Bounded live-flight fallback when OpenSky has no usable snapshot | ODbL 1.0 |
| **adsb.lol** | Military flights + aircraft traces | ODbL 1.0 |
| **adsbdb** (`api.adsbdb.com`) | Aircraft type, model name and registration by ICAO hex for enriched flights; airline and origin/destination airports for the tracked flight's callsign | No licence or rate limit is published for the service. Its own credits: aircraft data from PlaneBase, ICAO-to-N-number conversion by Guillaume Michel, and flight route data that "is the work of David Taylor, Edinburgh and Jim Mason, Glasgow, and may not be copied, published, or incorporated into other databases without the explicit permission of David J Taylor, Edinburgh" |
| **AISStream.io** | Live vessels (AIS) | Free, beta, no formal ToS; AIS is a public broadcast |
| **CelesTrak** | Satellite TLEs (SGP4) | US-government-origin data, no license; citation requested |
| **The Space Devs — Launch Library 2 v2.3** | Recent launch, payload, stage, and recovery metadata for Space Missions (30d) | [The Space Devs terms of use](https://github.com/TheSpaceDevs/Tutorials/blob/main/faqs/faq_TSD.md#terms-of-use): data may be used and shared in any form; avoid forwarding it without added value; attribution is encouraged (not mandatory). [Official API limits](https://ll.thespacedevs.com/docs/): 15 unauthenticated calls/hour; optional token |
| **Esri World Imagery** (ArcGIS Online tile service) | The keyless satellite basemap — the default landing when no Google/ion credential is configured, and the "Esri Satellite" map stack | [Esri Master Agreement](https://www.esri.com/en-us/legal/terms/full-master-agreement): the public World Imagery service is usable in public-facing apps with attribution; no key is required for this classic endpoint, but Esri governs and can change access — an app at scale should review current ArcGIS Location Platform terms |
| **USGS** | Earthquakes | U.S. public domain |
| **NASA GIBS** (WMTS tiles + Worldview Snapshots) and **NASA CMR** (granule catalog) | Recent Imagery layer: HLS S30/L30 (Sentinel-2, Landsat 8/9) and VIIRS true-colour tiles draped on the map, per-day thumbnails and PNG exports; the HLS granule catalog (dates, cloud, footprints) for a selected box | U.S. public domain (NASA data); keyless, browser-direct (CORS `*`); no bulk use — one 30-day catalog query per box, tiles bounded to the box, six tile requests in flight |
| **NIFC WFIGS** (Wildland Fire Interagency Geospatial Services, ArcGIS feature service) | Fire Perimeters layer: current interagency wildfire incident perimeters, containment, and incident facts | U.S. public domain (interagency wildland-fire data published through the [NIFC Open Data portal](https://data-nifc.opendata.arcgis.com/)); fetched keyless through `/api/fire-perimeters` (5-minute server cache) with `exceededTransferLimit` paging |
| **InciWeb** (inciweb.wildfire.gov) | Per-incident "InciWeb ↗" card links to official incident pages (narratives, evacuation/closure notices) | U.S. government public incident information. Links are matched best-effort by incident name and state, with incident page origin and update times checked on selection. Same-origin `/api/fire-perimeters/inciweb` routes cache the catalog for 1 hour and publication metadata for 30 minutes; linked pages remain InciWeb content |
| **OpenFreeMap / OpenMapTiles** | Vector tiles | OpenStreetMap data under ODbL 1.0 |
| **Overture Maps Foundation** | Military area names pack | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| **TomTom Traffic API** (flow vector tiles) | Traffic roads and live congestion (optional, BYOK) | [TomTom for Developers terms](https://docs.tomtom.com/legal/terms-and-conditions) (proprietary, your own key; free tier currently 200K tile requests/month — see [current pricing](https://docs.tomtom.com/pricing/)) |
| **Photon** (komoot) | Keyless place search — the fallback when no Google Maps key is configured, or when Google declines the Geocoding request | Service: free public instance, [fair use](https://photon.komoot.io) (no bulk/heavy use); underlying data: **ODbL 1.0** |
| **Open-Meteo** | Current weather in the cockpit Local Info page and cockpit-local dynamic atmospheric effects | [CC BY 4.0 data licence and adjacent-link attribution requirement](https://open-meteo.com/en/licence) |
| **Google News RSS** | Primary locality-matched headlines in the cockpit Regional News page | [Google News Terms of Service](https://www.google.com/intl/en_us/terms_google_news.html) restrict use to personal, noncommercial use; linked articles remain third-party publisher content and retain publisher terms |
| **GDELT Project DOC 2.0** | Fail-soft fallback for location-matched cockpit headlines | [GDELT Terms of Use](https://www.gdeltproject.org/about.html#termsofuse): unrestricted academic/commercial/governmental dataset use, with citation and link required; linked articles retain publisher terms |
| **City of Austin Open Data** | CCTV camera catalog + frames | City of Austin Open Data Terms of Use |
| **TxDOT ITS (its.txdot.gov)** | CCTV camera catalogs + frames, Texas districts | Public TxDOT traffic camera data |
| **City of Tallinn (ristmikud.tallinn.ee)** | CCTV camera catalog + frames, Tallinn intersections | Public City of Tallinn traffic camera data |
| **Transpordiamet / Tarktee** | CCTV camera catalog + frames, Estonia road-weather cameras | Public Transpordiamet / Tarktee road camera data |
| **Stadt Warendorf webcam** | Webcam frames, Marktplatz / Historisches Rathaus (`config/cctv_sources.warendorf.json`) | Public municipal webcam data |
| **Live Traffic NSW (Transport for NSW)** | CCTV camera catalog + frames, New South Wales | [CC BY 4.0](https://opendata.transport.nsw.gov.au/) — attribution REQUIRED |
| **Caltrans (cwwp2.dot.ca.gov)** | CCTV camera catalogs + frames, California districts | Public Caltrans traffic camera data |
| **DelDOT (video.deldot.gov)** | CCTV camera catalog (`tmc.deldot.gov/json/videocamera.json`, cached for 15 minutes) + live HTTPS HLS video, Delaware. Keyless | Public DelDOT traffic camera streams via the [DelDOT traffic map](https://deldot.gov/map/) |
| **TfL Open Data (JamCams)** | CCTV camera catalog + frames, London | [TfL Open Data terms](https://tfl.gov.uk/info-for/open-data-users/) — attribution REQUIRED |
| **Ontario 511** | CCTV camera catalog + frames, Ontario highways including Kitchener-area routes | [Open Government Licence – Ontario](https://www.ontario.ca/page/open-government-licence-ontario) |
| **Fintraffic / Digitraffic (weathercams)** | CCTV camera catalog + frames, Finland | [CC BY 4.0](https://www.digitraffic.fi/en/terms-of-service/) — attribution REQUIRED |
| **DriveBC** (Government of British Columbia) | CCTV camera catalog + frames, British Columbia highways | [Open Government Licence – British Columbia](https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc) — attribution REQUIRED |
| **Open Calgary** (`data.calgary.ca`) | CCTV camera catalog + frames, Calgary | [Open Government Licence – City of Calgary](https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa) — attribution REQUIRED |
| **Statens vegvesen** (catalog `ogckart-sn1.atlas.vegvesen.no`, frames `kamera.atlas.vegvesen.no`, HLS `kamera.vegvesen.no`) | CCTV camera catalog + frames + live HLS video, Norway road cameras | [NLOD 2.0](https://data.norge.no/nlod/en/2.0) — attribution REQUIRED |
| **NYC DOT Traffic Management Center** (`webcams.nyctmc.org`) | CCTV camera catalog + frames, New York City five boroughs | NYC DOT requires developers to sign a [data-sharing agreement](https://www.nyc.gov/html/dot/html/about/datafeeds.shtml) for the camera feed. **Off by default**; enable only under your own agreement |
| **GBFS (Lyft / BCycle)** | Bikeshare availability | Per-feed (attribution-only) |
| **MBTA / MassDOT** (cdn.mbta.com) | Transit layer live vehicles and up to 15 minutes of recently observed positions, Greater Boston | MBTA / MassDOT open realtime vehicle data, used for the live view and up to fifteen minutes of recently observed positions; published for developer use and not against their use. |
| **CapMetro** (data.texas.gov) | Transit layer live vehicles, Austin TX | CapMetro open realtime vehicle data, used for the live view; published for developer use and not against their use. |
| **Metro Transit** (Metropolitan Council) | Transit layer live vehicles, Minneapolis–St Paul | Metro Transit / Metropolitan Council open realtime vehicle data, used for the live view; published for developer use and not against their use. |
| **OVapi / Stichting OpenGeo** | Transit layer live vehicles, Netherlands | OVapi / Stichting OpenGeo open realtime vehicle data, used for the live view; published for developer use and not against their use. The client sends a User-Agent and conditional requests. |
| **Entur** (api.entur.io) | Transit layer live vehicles, Norway | Entur open realtime vehicle data, used for the live view; published for developer use and not against their use. The client sends the `ET-Client-Name` identifying header. |
| **TransLink** (Queensland Government) | Transit layer live vehicles, South East Queensland | TransLink / Queensland Government open realtime vehicle data, used for the live view; published for developer use and not against their use. |
| **HSL** (realtime.hsl.fi) | Transit layer live vehicles, Helsinki | HSL (Helsinki Region Transport) open realtime vehicle data, used for the live view; published for developer use and not against their use. |
| **Radio Browser** | Geolocated internet-radio station directory and station-level tags | Public-domain directory data under PDDL 1.0; individual broadcaster stream terms apply |
| **Re:Earth Terrain** (Mapterhorn) | Terrain (keyless globe stacks — OSM etc. — + `/api/terrain/heights` ellipsoidal-height lookups) | Terrain mesh: CC BY 4.0; geoid: EGM2008 (NGA, public domain) |
| **OSRM on the FOSSGIS routing servers** (`routing.openstreetmap.de`) | Street-following routes for the Directions layer and voice route annotations, via `/api/route` | [FOSSGIS routing usage policy](https://routing.openstreetmap.de/about.html): "Display the required attribution and display a link to 'fix the map'", "Use a valid user agent and, if applicable, a correct referrer", "One request per second max", "No scraping, no heavy usage". The full policy is the German [FOSSGIS Nutzungsbedingungen](https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/); FOSSGIS also states that the server may be embedded in your own pages but "eine gewerbliche Nutzung ist nur mit Einschränkungen erlaubt" (commercial use only with restrictions). Route data derives from OpenStreetMap (ODbL 1.0) |

### Upstream bundled snapshots (copied forward; none are MIT)

| Dataset | Folder | License | Commercial use? | Attribution |
|---|---|---|---|---|
| **Datacenters** (4,351) | `datacenters/` | **ODbL 1.0** (OpenStreetMap extract) | ✅ (attribution + share-alike on data) | © OpenStreetMap contributors (shared credit) |
| **Dams** (704) | `dams/` | **ODbL 1.0** (OpenInfraMap / OSM extract) | ✅ (attribution + share-alike on data) | © OpenStreetMap contributors (shared credit) + Open Infrastructure Map |
| **Military area names** (36,466) | `osm_military_names/` | **ODbL 1.0** (OpenStreetMap, via Overture Maps) | ✅ (attribution + share-alike on data) | © OpenStreetMap contributors (shared credit) + Overture Maps Foundation |
| **TeleGeography Submarine Cable Map** (712 cables + 1,917 landing points) | `telegeography_submarine_cables/` | **CC BY-NC-SA 3.0** | ❌ **NonCommercial — remove for commercial use** | "© TeleGeography — submarinecablemap.com" |
| **Natural Earth physical regions** (1,046 land + 292 marine named polygons) | `natural_earth/` | **Public domain** | ✅ (no restrictions) | "Made with Natural Earth" (courtesy credit — not legally required) |
| **DataSF Analysis Neighborhoods** (41 SF neighborhood polygons) | `neighborhoods/` | **PDDL 1.0** (public domain) | ✅ (no restrictions) | "City & County of San Francisco — DataSF" (courtesy — not legally required) |
| **Natural Earth countries, states and provinces** (260 admin-0/map units + 4,587 admin-1 polygons) | `natural_earth/` | **Public domain** | ✅ (no restrictions) | "Made with Natural Earth" (courtesy credit — not legally required) |
| **US Census Bureau counties** (3,235 county polygons) | `us_census_counties/` | **Public domain** | ✅ (no restrictions) | "U.S. Census Bureau" (courtesy — not legally required) |
| **CCTV ground heights** (3,445 cameras) | `cctv_ground_heights/` | Precomputed camera placement heights, aligned to work with Google Photorealistic 3D Tiles (folder README) | — | — |

Notable carve-outs inherited from upstream: TeleGeography submarine cables are CC BY-NC-SA 3.0
(NonCommercial); the Bhote Koshi event pack is CC BY-NC 4.0; NYC DOT cameras are off by default
pending a data-sharing agreement; OpenSky is non-commercial research/education. See
`DATA_SOURCES.md` for the complete notes and in-app attribution policy.
