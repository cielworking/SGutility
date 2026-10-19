"use strict";

(() => {
  const root = document.querySelector('[data-combined-weather]');
  if (!root) return;
  const byId = id => document.getElementById(id);
  const escapeText = value => String(value ?? 'Unavailable').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const sgBase = 'https://api-open.data.gov.sg/v2/real-time/api/';
  const format = value => {
    const d = new Date(value);
    return Number.isFinite(d.getTime()) ? d.toLocaleString('en-SG', {timeZone:'Asia/Singapore',day:'numeric',month:'short',hour:'numeric',minute:'2-digit',hour12:true}) : 'Unavailable';
  };
  const dateInSG = (time = Date.now()) => new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Singapore',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(time));
  async function json(url) {
    const response = await fetch(url, {cache:'no-store',signal:AbortSignal.timeout(20000)});
    if (!response.ok) throw new Error(`Source returned ${response.status}`);
    const data = await response.json();
    if (data.code !== undefined && data.code !== 0) throw new Error('Source unavailable');
    return data;
  }
  let cache = {}, map, overlay, frames = [], frameIndex = 0, playing, radarBusy = false, weatherBusy = false;
  let loadedRange, imageTicket = 0, lastForecast = '', lastRadar = '', radarBounds;
  const range = byId('radar-range'), slider = byId('radar-time'), play = byId('radar-play');

  function stop() { clearInterval(playing); playing = null; play.textContent = '▶ Play'; play.setAttribute('aria-pressed','false'); }
  async function showFrame(index) {
    if (!frames.length) return;
    index = Math.max(0, Math.min(frames.length - 1, index));
    const record = frames[index], ticket = ++imageTicket;
    byId('radar-status').textContent = 'Loading radar image…';
    try {
      const image = new Image();
      image.src = record.image.url;
      await image.decode();
      if (ticket !== imageTicket) return;
      if (overlay) overlay.setUrl(record.image.url).setBounds(radarBounds);
      else overlay = L.imageOverlay(record.image.url, radarBounds, {opacity:.8,interactive:false,alt:'Observed rain intensity'}).addTo(map);
      frameIndex = index;
      slider.value = String(index);
      slider.setAttribute('aria-valuetext', format(record.timestamp) + ' UTC+08');
      byId('radar-stamp').textContent = format(record.timestamp) + ' UTC+08';
      const age = Date.now() - Date.parse(frames.at(-1).timestamp);
      byId('radar-status').textContent = age > 20*60000 ? 'Radar source is delayed — latest available image shown.' : 'NEA observed rainfall · latest frame ' + format(frames.at(-1).timestamp) + ' UTC+08';
    } catch {
      if (ticket !== imageTicket) return;
      stop(); slider.value = String(frameIndex);
      byId('radar-status').textContent = 'That radar image could not load. Keeping the previous image; use Refresh to renew the frames.';
    }
  }
  async function refreshRadar() {
    if (radarBusy) return {same:true};
    radarBusy = true; stop();
    const selectedRange = range.value;
    range.disabled = true;
    try {
      if (!window.L) throw new Error('Map unavailable');
      if (!map) {
        map = L.map('rain-map',{scrollWheelZoom:false}).setView([1.45,103.82],10);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:15,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · Rain: NEA / data.gov.sg'}).addTo(map);
        new ResizeObserver(()=>map.invalidateSize()).observe(byId('rain-map'));
      }
      let data = (await json(`${sgBase}weather-radar-images/${selectedRange}?date=${dateInSG()}`)).data;
      if (!data?.records?.length || !data.boundaryBox) throw new Error('No radar frames');
      let rows = data.records;
      if (rows.length < 13) {
        try {
          const previous = (await json(`${sgBase}weather-radar-images/${selectedRange}?date=${dateInSG(Date.now()-86400000)}`)).data;
          rows = rows.concat(previous?.records || []);
        } catch { /* Today's frames are still useful at midnight. */ }
      }
      rows = [...new Map(rows.filter(r=>r.image?.url && r.timestamp).map(r=>[r.timestamp,r])).values()].sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp)).slice(-13);
      if (!rows.length) throw new Error('No usable radar frames');
      // Check the new image before replacing an existing range or its timeline.
      const check = new Image(); check.src = rows.at(-1).image.url; await check.decode();
      const signature = selectedRange + rows.at(-1).timestamp;
      const same = signature === lastRadar; lastRadar = signature;
      const box = data.boundaryBox;
      radarBounds = [[box.lowerRight.latitude,box.upperLeft.longitude],[box.upperLeft.latitude,box.lowerRight.longitude]];
      if (loadedRange !== selectedRange) {
        if (selectedRange === '70km') map.setView([1.42,103.85],10);
        else map.fitBounds(radarBounds,{padding:[8,8]});
      }
      loadedRange = selectedRange; frames = rows;
      slider.max = String(rows.length-1); slider.disabled = false; play.disabled = rows.length < 2; byId('radar-latest').disabled = false;
      byId('radar-start').textContent = format(rows[0].timestamp);
      byId('radar-end').textContent = format(rows.at(-1).timestamp);
      await showFrame(rows.length-1);
      rows.slice(0,-1).forEach(record=>{const preload = new Image();preload.src=record.image.url;});
      return {same};
    } catch {
      if (loadedRange) range.value = loadedRange;
      byId('radar-status').textContent = 'Radar refresh failed — previous image retained if available. Check NEA rain areas for the latest view.';
      return {failed:true};
    } finally {radarBusy = false;range.disabled = false;}
  }
  slider.addEventListener('input',()=>{stop();showFrame(Number(slider.value));});
  play.addEventListener('click',()=>{
    if (playing) return stop();
    play.textContent = 'Ⅱ Pause';play.setAttribute('aria-pressed','true');
    playing = setInterval(()=>showFrame((Number(slider.value)+1)%frames.length),1100);
  });
  byId('radar-latest').addEventListener('click',()=>{stop();showFrame(frames.length-1);});
  range.addEventListener('change',refreshRadar);

  function regional() {
    const select = byId('sg-area'), area = select.value, forecast = cache.sg_rain?.data || {};
    if (area) {
      const row = forecast.forecasts?.find(r=>r.area === area), window = forecast.valid_period || {};
      byId('sg-outlook-result').innerHTML = `<article class="region-card local-forecast"><h3>${escapeText(area)} · next two hours</h3><p>${escapeText(format(window.start))} – ${escapeText(format(window.end))} UTC+08</p><strong>${escapeText(row?.forecast)}</strong><p>${Date.parse(window.end)<Date.now() ? 'This forecast has expired. Refresh for the latest available period.' : 'Conditions expected within this forecast period; exact rain-start times are not provided.'}</p></article>`;
      byId('outlook-source-time').textContent = 'Source issued: ' + format(forecast.timestamp) + ' UTC+08';
      return;
    }
    const outlook = cache.sg_outlook?.data;
    if (!outlook) return;
    byId('outlook-source-time').textContent = 'Source issued: ' + format(outlook.timestamp) + ' UTC+08 · Last checked: ' + format(cache.sg_outlook.fetched_at) + ' UTC+08';
    byId('sg-outlook-result').innerHTML = '<div class="region-grid">' + ['north','south','east','west','central'].map(region=>{
      const periods = (outlook.periods||[]).filter(p=>Date.parse(p.timePeriod?.end)>Date.now());
      const items = periods.map(p=>`<li data-period-end="${escapeText(p.timePeriod.end)}"><span>${escapeText(format(p.timePeriod.start))} – ${escapeText(format(p.timePeriod.end))}</span><strong>${escapeText(p.regions?.[region]?.text)}</strong></li>`).join('');
      return `<article class="region-card"><h3>${region[0].toUpperCase()+region.slice(1)}</h3><ol class="outlook-timeline">${items || '<li>Forecast expired or unavailable. Refresh for the latest outlook.</li>'}</ol></article>`;
    }).join('') + '</div>';
  }
  function malaysia() {
    const feed = cache.my_rain;
    if (!feed?.data) return;
    const rows = feed.data.filter(r=>r.location.location_id === byId('my-weather-location').value && r.date >= dateInSG()).sort((a,b)=>a.date.localeCompare(b.date));
    const tile = row => `<article class="malaysia-day"><h4>${escapeText(row.location.location_name)} · ${escapeText(row.date)}</h4><dl class="day-periods">${[['Morning','morning_forecast'],['Afternoon','afternoon_forecast'],['Night','night_forecast']].map(([label,key])=>`<div><dt>${label}</dt><dd>${escapeText(weatherCondition(row[key]))}</dd></div>`).join('')}</dl><p>${escapeText(row.min_temp)}–${escapeText(row.max_temp)} °C</p></article>`;
    byId('my-outlook-result').innerHTML = rows.length ? tile(rows[0]) + `<details class="more-forecast"><summary>View the next ${rows.length-1} days</summary>${rows.slice(1).map(tile).join('')}</details>` : '<p>No current forecast available for this location. Try Refresh.</p>';
    byId('my-source-time').textContent = 'Last source check: ' + format(feed.fetched_at) + ' UTC+08 · General forecast published daily. ' + (!feed.ok || Date.now()-Date.parse(feed.fetched_at)>36*3600000 ? 'Older saved data — check MET Malaysia.' : '');
  }
  function warnings() {
    const feed = cache.my_warnings;
    if (!feed) return;
    const active = (feed.data||[]).filter(r=>{
      const local = t=>t ? Date.parse(/[Zz]|[+-]\d\d:\d\d$/.test(t) ? t : t+'+08:00') : NaN;
      return local(r.valid_from)<=Date.now() && local(r.valid_to)>Date.now();
    });
    byId('combined-warnings').innerHTML = '<h4>Malaysia warnings · all affected locations</h4>' + (!feed.ok ? '<p>Warning feed unavailable; saved notices may be out of date.</p>' : '') + (active.map(r=>`<article class="weather-tile"><h4>${escapeText(r.heading_en||r.heading_bm)}</h4><p>${escapeText(r.text_en||r.text_bm)}</p><p>Valid until ${escapeText(r.valid_to)} UTC+08</p></article>`).join('') || '<p>No currently valid warnings in the saved feed. Check MET Malaysia for the latest notices.</p>') + '<p><a href="https://www.met.gov.my/">MET Malaysia warnings</a> · <a href="https://www.weather.gov.sg/">Singapore MSS warnings</a></p>';
  }
  function renderForecasts() {
    const select = byId('sg-area'), previous = select.value;
    if (cache.sg_rain?.data?.forecasts) {
      select.innerHTML = '<option value="">All areas · five-region overview</option>' + cache.sg_rain.data.forecasts.map(r=>`<option>${escapeText(r.area)}</option>`).join('');
      if ([...select.options].some(o=>o.value===previous)) select.value = previous;
    }
    regional();malaysia();warnings();
  }
  async function refreshForecasts() {
    if (weatherBusy) return {same:true};
    weatherBusy = true;
    const failures = [];
    try {
      // Saved data also supplies Malaysia locations and warnings if a live source fails.
      try {
        const saved = await json('/data/weather.json');
        for (const [key,feed] of Object.entries(saved)) {
          if (!cache[key] || Date.parse(feed.fetched_at)>Date.parse(cache[key].fetched_at)) cache[key] = feed;
        }
      } catch { failures.push('saved feed'); }
      const tasks = [
        ['sg_outlook',sgBase+'twenty-four-hr-forecast',r=>r.data?.records?.[0]],
        ['sg_rain',sgBase+'two-hr-forecast',r=>r.data?.items?.[0]],
        ['my_rain','https://api.data.gov.my/weather/forecast?limit=10000',r=>Array.isArray(r)&&r.length&&r.length<10000?r:null]
      ];
      const results = await Promise.allSettled(tasks.map(async ([key,url,parse])=>{
        const payload = parse(await json(url));
        if (!payload || (key==='sg_outlook'&&!payload.periods?.length) || (key==='sg_rain'&&!payload.forecasts?.length)) throw new Error('No usable forecast');
        cache[key] = {data:payload,ok:true,fetched_at:new Date().toISOString()};
      }));
      results.forEach((r,i)=>{if(r.status==='rejected')failures.push(tasks[i][0]);});
      renderForecasts();
      const signature = JSON.stringify([cache.sg_outlook?.data,cache.sg_rain?.data,cache.my_rain?.data]);
      const same = signature===lastForecast;lastForecast=signature;
      return {same,failed:failures.length>0};
    } finally {weatherBusy=false;}
  }
  byId('sg-area').addEventListener('change',regional);
  byId('my-weather-location').addEventListener('change',malaysia);
  const refresh = byId('refresh-weather');
  async function refreshAll(manual=false) {
    if (refresh.disabled) return;
    refresh.disabled = true;refresh.textContent='Refreshing…';
    byId('weather-refresh-status').textContent='Checking official radar and forecast sources…';
    try {
      const results = await Promise.allSettled([refreshRadar(),refreshForecasts()]);
      const failed = results.some(r=>r.status==='rejected'||r.value.failed);
      const same = results.every(r=>r.status==='fulfilled'&&r.value.same);
      byId('weather-refresh-status').textContent=(failed?'Some sources could not refresh; previous available data is retained. ':same?'No newer radar or forecast information available. ':'Latest available radar and forecasts loaded. ')+'Last checked: '+format(new Date().toISOString())+' UTC+08';
    } finally {
      const unlock=()=>{refresh.disabled=false;refresh.textContent='↻ Refresh weather';};
      if(manual)setTimeout(unlock,5000);else unlock();
    }
  }
  refresh.addEventListener('click',()=>refreshAll(true));
  refreshAll();
  setInterval(()=>{if(!document.hidden&&root.getBoundingClientRect().bottom>0&&root.getBoundingClientRect().top<innerHeight)refreshAll();},300000);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
})();
