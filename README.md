# SG Utility Dashboard

## Weather and air quality

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
