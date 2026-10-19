# SG Utility Dashboard

## Weather and air quality

The homepage Haze & Air Quality panel now has Singapore / Malaysia tabs, a selected
reading gauge, clickable reporting-region or station markers, separate PSI and
one-hour PM2.5 bands, source timestamps and accessible hourly trend values. The map
uses the five NEA reporting-region label positions or public APIMS station coordinates.
Malaysia defaults to Johor's Larkin station; it never presents one station as a
national reading. SG official history is fetched for today and yesterday and displayed
as 24 hourly reports with gaps preserved. Malaysia history is recorded from the first
successful deployment onward, deduplicated by station/report time and retained for
48 hours; the chart states how many readings exist while history builds.
Manual refresh checks official feeds where browser access is available, retaining
saved readings if a source fails. Automatic visible-panel checks run every five
minutes, alongside the existing 15-minute saved-data workflow. Current complete SG
history is reused until a newer reporting hour appears, reducing unnecessary requests.

Air-panel validation: `node tests/test-air-quality.cjs` checks metric boundaries,
missing readings, region isolation and gaps; Python tests also check snapshot escaping
and official history ordering.

The primary weather experience is now `/weather/` and the combined weather section
on the homepage. Country rain URLs retain working entry points and canonicalise
to `/weather/`. NEA radar playback offers the latest 13 available frames, a draggable
time slider, play/pause, latest-frame control and 70/240/480 km coverage selectors.
Radar is observed rainfall, not future rain prediction. Leaflet displays the
georeferenced transparent radar over OpenStreetMap with source attribution.
Public image URLs expire, so the browser obtains fresh URLs directly from
data.gov.sg; signed image URLs are not stored in the repository.

The default Singapore outlook uses the official 24-hour feed's five regions and
time periods, without manufacturing neighbourhood-to-region mappings. Individual
areas use the two-hour forecast through a dropdown. Malaysia forecasts share the
same experience, default to Johor Bahru, and expose later days in a disclosure.
While weather is visible, radar and forecasts refresh every five minutes. Manual
refresh checks official radar and SG/MY forecast APIs directly, independently
retaining the previous usable data when a source fails. Malaysia warnings and haze
use the published saved feed. News and other dashboard Refresh buttons re-read
published JSON with browser caching bypassed; they do not trigger server scraping.
Feedback distinguishes unchanged data from failures and keeps source dates intact.

The homepage links to four static, indexable pages: `/singapore/rain-forecast/`,
`/malaysia/rain-forecast/`, `/singapore/haze/`, and `/malaysia/haze/`.
The existing SG Alerts name, tagline, and icon assets are retained.

`scripts/update-weather.py` caches MSS / NEA data.gov.sg forecasts, PSI and PM2.5,
MET Malaysia forecasts and warnings from data.gov.my, and DOE APIMS station API.
Each feed fails independently and retains its previous successful snapshot.
`scripts/render-weather-pages.py` renders data into HTML so it is readable without
JavaScript. JavaScript adds location filters and checks for expired or delayed data.
All reporting times are displayed in UTC+08. The legacy APIMS ArcGIS layer encodes
Malaysia wall time as epoch milliseconds; normalization follows the official
portal's legacy UTC-component display. Only public station display fields are cached.

The weather workflow runs at minutes 7, 22, 37 and 52 each hour (GitHub schedules
can be delayed). It explicitly requests a GitHub Pages rebuild after the bot commit
because GITHUB_TOKEN commits do not trigger branch-based Pages publishing. The
repository must retain its existing GitHub Pages branch publishing configuration.
Both data workflows share a concurrency group to avoid overlapping bot pushes.
The sitemap renderer preserves all four new URLs on existing dashboard refreshes.

Run locally after installing `requests`:

```text
python scripts/update-weather.py
python scripts/render-weather-pages.py
python scripts/render-static-pages.py
python -m unittest discover -s tests -v
python -m http.server 8765
```

SEO verification after publishing: submit `https://sgalerts.com/sitemap.xml` in
Google Search Console and inspect the four URLs. Indexing is Google's decision.

A modern Singapore utility dashboard built using HTML, CSS, and JavaScript.

This project combines useful Singapore daily information into a single clean dashboard interface.

---

# 📌 Features

- 🎲 Singapore Pools 4D & TOTO results
- 🚗 Latest COE prices
- ⛽ Petrol price comparison
- 🏠 Upcoming BTO projects
- 🇸🇬 Upcoming holiday or Vouchers
- 🎰 Lucky Pick generator
- 📱 Fully responsive design

---

# 📱 Responsive Design

The website supports:

- Desktop layout
- Tablet layout
- Mobile layout
- Small mobile optimization

Responsive breakpoints:

```css
@media screen and (max-width: 1024px)
@media screen and (max-width: 768px)
@media screen and (max-width: 420px)
```

---

# 🛠 Built With

- HTML5
- CSS3
- JavaScript
- GitHub Pages

---

# 📂 Project Structure

```bash
SGutility/
│
├── .github/
├── assets/
├── data/
├── scripts/
├── index.html
├── style.css
├── script.js
└── README.md
```

---

# 🚀 Running Locally

Clone repository:

```bash
git clone https://github.com/cielworking/SGutility.git
```

Open project folder:

```bash
cd SGutility
```

Run locally by opening:

```bash
index.html
```

You may also use VSCode Live Server.

---

# ☁️ Deployment

This project is deployed using GitHub Pages.

Future deployment plans may include:
- Custom Cloudflare domain
- Performance optimizations
- Additional dashboard utilities

---

# 🔄 Git Workflow

Basic workflow:

```powershell
git add .
git commit -m "update"
git push
```

If push is rejected:

```powershell
git pull --rebase
git push
```

---

# 🎯 Planned Improvements

- Live API integration
- MRT service alerts
- Weather information
- Dark mode
- UI/UX improvements
- Accessibility enhancements

---

# 📄 License

This project is for educational and personal portfolio purposes.

---

# 👨‍💻 Author

Created by Ciel

GitHub:
https://github.com/cielworking
