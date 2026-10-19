"use strict";

const AirQuality = (() => {
  const PSI = [[50,'Good','#249b42'],[100,'Moderate','#80c5aa'],[200,'Unhealthy','#f5bc00'],[300,'Very unhealthy','#f58216'],[Infinity,'Hazardous','#a92c22']];
  const PM = [[55,'Normal','#80c5aa'],[150,'Elevated','#80b9e5'],[250,'High','#f5bc00'],[Infinity,'Very high','#bb3a39']];
  const valid = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
  function band(value, metric='psi') {
    if (!valid(value)) return {label:'Unavailable',color:'#d8dee8',value:null};
    const match=(metric==='pm25'?PM:PSI).find(row=>value<=row[0]);
    return {label:match[1],color:match[2],value};
  }
  function points(rows, region, metric) {
    const field=metric==='pm25'?'pm25_one_hourly':'psi_twenty_four_hourly';
    const unique=new Map();
    for(const row of rows || []) {
      const value=row.readings?.[field]?.[region], time=Date.parse(row.timestamp);
      if(valid(value)&&Number.isFinite(time))unique.set(time,{time,value});
    }
    return [...unique.values()].sort((a,b)=>a.time-b.time).slice(-24);
  }
  return {PSI,PM,valid,band,points};
})();
if (typeof module !== 'undefined') module.exports=AirQuality;

if (typeof document !== 'undefined') (() => {
  const root=document.querySelector('[data-air-dashboard]');
  if(!root)return;
  const $=id=>document.getElementById(id);
  const escape=value=>String(value??'Unavailable').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const time=value=>Number.isFinite(Date.parse(value))?new Date(value).toLocaleString('en-SG',{timeZone:'Asia/Singapore',day:'numeric',month:'short',hour:'numeric',minute:'2-digit',hour12:true}):'Unavailable';
  const hour=value=>new Date(value).toLocaleTimeString('en-SG',{timeZone:'Asia/Singapore',hour:'numeric',hour12:true});
  const day=value=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Singapore',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
  const sg='https://api-open.data.gov.sg/v2/real-time/api/';
  const apims='https://eqms.doe.gov.my/api3/publicmapproxy/PUBLIC_DISPLAY/CAQM_MCAQM_Current_Reading/MapServer/0/query';
  const coords={north:[1.41803,103.82],south:[1.29587,103.82],east:[1.35735,103.94],west:[1.35735,103.7],central:[1.35735,103.82]};
  let cache={};try{cache=JSON.parse($('air-quality-snapshot').textContent);}catch{}
  let country='sg',metric='psi',region=root.dataset.defaultRegion||'west',state='Johor',station='',map,markers,busy=false,lastSignature='';
  let previousMapGroup='', activeBounds=[];

  async function json(url) {
    const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(18000)});
    if(!response.ok)throw new Error('Source unavailable');
    const payload=await response.json();
    if(payload.code!==undefined&&payload.code!==0)throw new Error('Source unavailable');
    return payload;
  }
  const stations=()=>cache.my_haze?.data||[];
  function options() {
    const names=[...new Set(stations().map(r=>r.state))].sort();
    if(state!==''&&!names.includes(state))state=names.includes('Johor')?'Johor':names[0]||'';
    $('air-state').innerHTML='<option value="">All Malaysia</option>'+names.map(name=>`<option>${escape(name)}</option>`).join('');
    $('air-state').value=state;
    const rows=stations().filter(row=>!state||row.state===state);
    if(!rows.some(row=>row.id===station))station=(rows.find(row=>row.location.toLowerCase().includes('larkin'))||rows[0])?.id||'';
    $('air-station').innerHTML=rows.map(row=>`<option value="${escape(row.id)}">${escape(row.location)}</option>`).join('');
    $('air-station').value=station;
    return rows;
  }
  function current() {
    if(country==='sg') {
      const feed=cache[metric==='psi'?'sg_psi':'sg_pm25']||{}, data=feed.data||{}, field=metric==='psi'?'psi_twenty_four_hourly':'pm25_one_hourly';
      return {value:data.readings?.[field]?.[region],location:region[0].toUpperCase()+region.slice(1)+' · Singapore',stamp:data.timestamp,feed,category:null};
    }
    const row=stations().find(r=>r.id===station)||{};
    return {value:row.api,location:row.location||'Station unavailable',stamp:row.reported_at,feed:cache.my_haze||{},category:row.category};
  }
  function readings() {
    if(country==='sg') {
      const key=metric==='psi'?'sg_psi_history':'sg_pm25_history';
      const rows=[...(cache[key]?.data||[]),cache[metric==='psi'?'sg_psi':'sg_pm25']?.data||{}];
      return AirQuality.points(rows,region,metric);
    }
    const unique=new Map();
    for(const row of cache.my_haze_history?.data?.[station]||[]) {
      const stamp=Date.parse(row.timestamp);
      if(AirQuality.valid(row.value)&&Number.isFinite(stamp))unique.set(stamp,{time:stamp,value:row.value});
    }
    const selected=current();
    if(AirQuality.valid(selected.value)&&Number.isFinite(Date.parse(selected.stamp)))unique.set(Date.parse(selected.stamp),{time:Date.parse(selected.stamp),value:selected.value});
    return [...unique.values()].sort((a,b)=>a.time-b.time).slice(-24);
  }
  function chart() {
    const points=readings(), activeMetric=country==='sg'?metric:'api';
    const label=activeMetric==='pm25'?'1-hr PM2.5 (µg/m³)':activeMetric==='api'?'API / IPU':'24-hr PSI';
    $('air-chart-title').textContent='Recent hourly readings · '+label;
    if(!points.length) {
      $('air-trend').innerHTML='<p class="air-empty-chart">No valid history available for this selection.</p>';
      $('air-history-note').textContent='Previous readings have not been supplied yet. Refresh to check again.';
      $('air-history-values').textContent='No hourly values available.';return;
    }
    const end=points.at(-1).time, start=end-23*3600000;
    const shown=points.filter(p=>p.time>=start), peak=Math.max(...shown.map(p=>p.value));
    const step=peak<=250?50:peak<=500?100:Math.ceil(peak/500)*100;
    const max=Math.max(step,Math.ceil(peak/step)*step);
    const x=t=>44+(t-start)/(24*3600000)*570;
    const y=v=>202-v/max*166;
    const grid=Array.from({length:max/step+1},(_,i)=>i*step).map(value=>`<line x1="40" y1="${y(value)}" x2="620" y2="${y(value)}" stroke="#dce4ef" stroke-dasharray="2 3"/><text x="32" y="${y(value)+4}" text-anchor="end">${value}</text>`).join('');
    const bars=shown.map(p=>`<rect x="${x(p.time)}" y="${y(p.value)}" width="17" height="${Math.max(1,202-y(p.value))}" fill="${AirQuality.band(p.value,activeMetric).color}" tabindex="0" role="img" aria-label="${escape(time(new Date(p.time).toISOString()))}: ${p.value} ${escape(label)}"><title>${escape(time(new Date(p.time).toISOString()))}: ${p.value} ${escape(label)}</title></rect>`).join('');
    const ticks=[0,6,12,18,23].map(n=>`<text x="${x(start+n*3600000)+8}" y="225" text-anchor="middle">${escape(hour(start+n*3600000))}</text>`).join('');
    $('air-trend').innerHTML=`<svg viewBox="0 0 640 240" role="img" aria-label="${escape(label)} hourly history for ${escape(current().location)}. ${shown.length} available readings; gaps mean unavailable data.">${grid}${bars}${ticks}</svg>`;
    const short=shown.length<24;
    $('air-history-note').textContent=(country==='my'?'Official station readings recorded by SG Alerts. ':'Official NEA hourly reports. ')+(short?`${shown.length} reading${shown.length===1?'':'s'} available; history is building. `:'Latest 24 available hourly readings. ')+'Times use UTC+08. Empty periods are not interpolated.';
    $('air-history-values').innerHTML=`<table><thead><tr><th scope="col">Reported time (UTC+08)</th><th scope="col">${escape(label)}</th></tr></thead><tbody>${shown.map(p=>`<tr><td>${escape(time(new Date(p.time).toISOString()))}</td><td>${p.value}</td></tr>`).join('')}</tbody></table>`;
  }
  function drawMap() {
    if(!window.L){$('air-map-note').textContent='Map unavailable. Use the region buttons or station selector.';return;}
    if(!map) {
      $('air-map').replaceChildren();
      map=L.map('air-map',{scrollWheelZoom:false,zoomSnap:.25});
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:14,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
      markers=L.layerGroup().addTo(map);
      new ResizeObserver(()=>{
        map.invalidateSize();
        if(activeBounds.length)map.fitBounds(activeBounds,{padding:country==='sg'?[48,46]:[38,38],maxZoom:country==='sg'?11:10});
      }).observe($('air-map'));
    }
    markers.clearLayers();
    const entries=country==='sg'?Object.keys(coords).map(name=>({id:name,location:name.toUpperCase(),value:cache[metric==='psi'?'sg_psi':'sg_pm25']?.data?.readings?.[metric==='psi'?'psi_twenty_four_hourly':'pm25_one_hourly']?.[name],position:coords[name]})):stations().filter(r=>(!state||r.state===state)&&typeof r.latitude==='number'&&typeof r.longitude==='number').map(r=>({id:r.id,location:r.location.split(',')[0],value:r.api,position:[r.latitude,r.longitude]}));
    const bounds=[];
    entries.forEach(row=>{
      const active=country==='sg'?row.id===region:row.id===station;
      const band=AirQuality.band(row.value,country==='sg'?metric:'api');
      const icon=L.divIcon({className:'air-marker-wrap',html:`<span class="air-map-marker ${active?'is-selected':''}" style="background:${band.color};color:${band.color==='#a92c22'||band.color==='#bb3a39'?'white':'#172033'}"><strong>${AirQuality.valid(row.value)?row.value:'—'}</strong><small>${escape(row.location)}</small></span>`,iconSize:country==='sg'?[64,64]:[62,62],iconAnchor:[32,32]});
      L.marker(row.position,{icon,title:row.location,alt:row.location+' '+(AirQuality.valid(row.value)?row.value:'unavailable'),keyboard:true}).on('click',()=>{if(country==='sg')region=row.id;else{station=row.id;$('air-station').value=station;}render();}).addTo(markers);
      bounds.push(row.position);
    });
    const group=country+(country==='my'?state:'');
    activeBounds=bounds;
    if(group!==previousMapGroup&&bounds.length){map.fitBounds(bounds,{padding:country==='sg'?[48,46]:[38,38],maxZoom:country==='sg'?11:10});previousMapGroup=group;}
    $('air-map-note').textContent=country==='sg'?'Select a reporting region on the map or below.':'Select a monitoring station on the map or in the dropdown. Each reading represents that station.';
  }
  function render() {
    const malaysia=country==='my';
    $('air-metric-controls').hidden=malaysia;$('air-malaysia-controls').hidden=!malaysia;$('air-region-list').hidden=malaysia;
    root.querySelectorAll('[data-air-country]').forEach(button=>{const active=button.dataset.airCountry===country;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;});
    $('air-country-panel').setAttribute('aria-labelledby','air-country-'+country);
    if(malaysia)options();
    root.querySelectorAll('[data-air-metric]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.airMetric===metric)));
    const selected=current(), band=AirQuality.band(selected.value,malaysia?'api':metric);
    $('air-metric-label').textContent=malaysia?'Malaysia Air Pollutant Index':metric==='psi'?'Singapore 24-hour PSI':'Singapore one-hour PM2.5';
    $('air-number').textContent=AirQuality.valid(selected.value)?String(selected.value):'—';
    $('air-unit').textContent=malaysia?'API / IPU':metric==='psi'?'PSI':'µg/m³';
    $('air-gauge').style.background=band.color;$('air-gauge').style.color=band.color==='#a92c22'||band.color==='#bb3a39'?'white':'#172033';
    $('air-category-label').textContent=AirQuality.valid(selected.value)&&malaysia&&selected.category?selected.category:band.label;
    $('air-location-label').textContent=selected.location;
    $('air-reading-context').textContent=malaysia?'Selected monitoring station':'Selected reporting region';
    const age=Date.now()-Date.parse(selected.stamp), stale=!selected.feed.ok||!Number.isFinite(age)||age>3*3600000||age< -900000;
    $('air-source-stamp').textContent='Source reported: '+time(selected.stamp)+' UTC+08 · Last source check: '+time(selected.feed.fetched_at)+' UTC+08'+(stale?' · Older or unavailable reading — check the official source.':'');
    $('air-source-stamp').classList.toggle('is-stale',stale);
    root.querySelectorAll('[data-air-region]').forEach(button=>{
      const name=button.dataset.airRegion,value=cache[metric==='psi'?'sg_psi':'sg_pm25']?.data?.readings?.[metric==='psi'?'psi_twenty_four_hourly':'pm25_one_hourly']?.[name];
      button.querySelector('strong').textContent=AirQuality.valid(value)?value:'—';button.setAttribute('aria-pressed',String(name===region));button.style.borderColor=AirQuality.band(value,metric).color;
    });
    const bands=!malaysia&&metric==='pm25'?AirQuality.PM:AirQuality.PSI;
    let low=0;
    $('air-legend').innerHTML=bands.map(([high,label,color])=>{const range=high===Infinity?`${low}+`:`${low}–${high}`;low=high+1;return `<span><i style="background:${color}"></i><strong>${range}${!malaysia&&metric==='pm25'?' µg/m³':''}</strong> ${escape(label)}</span>`;}).join('');
    $('air-source-link').innerHTML=malaysia?'Source: <a href="https://eqms.doe.gov.my/APIMS/main">DOE Malaysia / APIMS</a>. API / IPU is Malaysia’s national index, not Singapore PSI.':'Source: <a href="https://www.haze.gov.sg/">NEA / data.gov.sg</a>. 24-hour PSI is an index; one-hour PM2.5 is a concentration with separate bands.';
    drawMap();chart();
  }
  root.querySelectorAll('[data-air-country]').forEach(button=>{
    button.addEventListener('click',()=>{country=button.dataset.airCountry;render();$('air-refresh-feedback').textContent='Showing the latest available '+(country==='sg'?'Singapore':'Malaysia')+' readings. Use Refresh to check the source.';});
    button.addEventListener('keydown',event=>{
      if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const key=event.key==='Home'?'sg':event.key==='End'?'my':country==='sg'?'my':'sg';const next=root.querySelector(`[data-air-country="${key}"]`);next.click();next.focus();}
    });
  });
  root.querySelectorAll('[data-air-metric]').forEach(button=>button.addEventListener('click',()=>{metric=button.dataset.airMetric;render();}));
  root.querySelectorAll('[data-air-region]').forEach(button=>button.addEventListener('click',()=>{region=button.dataset.airRegion;render();}));
  $('air-state').addEventListener('change',()=>{state=$('air-state').value;station='';render();});
  $('air-station').addEventListener('change',()=>{station=$('air-station').value;render();});

  async function refresh(manual=false) {
    if(busy)return;busy=true;const button=$('refresh-air-dashboard');button.disabled=true;button.textContent='Refreshing…';
    const requested=country;let failures=0;
    try {
      try {
        const saved=await json('/data/weather.json');
        for(const key of ['sg_psi','sg_pm25','sg_psi_history','sg_pm25_history','my_haze','my_haze_history'])if(saved[key]&&(!cache[key]||Date.parse(saved[key].fetched_at)>Date.parse(cache[key].fetched_at)))cache[key]=saved[key];
      } catch {failures++;}
      if(requested==='sg') {
        const tasks=['psi','pm25'].map(async endpoint=>{
          const key=endpoint==='psi'?'sg_psi':'sg_pm25';
          try {
            const payload=await json(sg+endpoint), data=payload.data?.items?.[0];
            if(!data?.readings)throw new Error('No readings');
            cache[key]={ok:true,fetched_at:new Date().toISOString(),data};
          } catch {failures++;}
          try {
            const available=cache[key+'_history']?.data||[];
            const latest=Math.max(...available.map(row=>Date.parse(row.timestamp)).filter(Number.isFinite));
            if(available.length>=24&&latest>=Date.parse(cache[key]?.data?.timestamp))return;
            const days=[day(Date.now()-86400000),day(Date.now())];
            const payloads=await Promise.all(days.map(date=>json(sg+endpoint+'?date='+date)));
            const rows=payloads.flatMap(p=>p.data?.items||[]);
            if(!rows.length)throw new Error('No history');
            cache[key+'_history']={ok:true,fetched_at:new Date().toISOString(),data:rows};
          } catch {failures++;}
        });
        await Promise.all(tasks);
      } else {
        try {
          const payload=await json(apims+'?f=json&where=1%3D1&outFields=STATION_ID,DATETIME,API,CLASS,STATION_LOCATION,STATE_NAME,LATITUDE,LONGITUDE&returnGeometry=false');
          if(!payload.features?.length)throw new Error('No stations');
          const rows=payload.features.map(({attributes:a})=>({id:a.STATION_ID,location:a.STATION_LOCATION,state:a.STATE_NAME,api:a.API,category:a.CLASS,latitude:a.LATITUDE,longitude:a.LONGITUDE,reported_at:a.DATETIME?new Date(a.DATETIME).toISOString().replace('Z','').slice(0,19)+'+08:00':null}));
          cache.my_haze={ok:true,fetched_at:new Date().toISOString(),data:rows};
        } catch {failures++;}
      }
      const signature=JSON.stringify(requested==='sg'?[cache.sg_psi?.data,cache.sg_pm25?.data]:cache.my_haze?.data);
      const same=signature===lastSignature;lastSignature=signature;render();
      if(country===requested)$('air-refresh-feedback').textContent=(failures?'Some sources could not refresh; the latest available saved readings remain visible. ':same?'No newer air-quality readings available. ':'Latest available air-quality readings loaded. ')+'Checked '+time(new Date().toISOString())+' UTC+08';
    } catch {$('air-refresh-feedback').textContent='Refresh failed — previous readings retained. Please try again.';}
    finally {const unlock=()=>{busy=false;button.disabled=false;button.textContent='↻ Refresh air quality';};if(manual)setTimeout(unlock,10000);else unlock();}
  }
  $('refresh-air-dashboard').addEventListener('click',()=>refresh(true));
  render();refresh();
  setInterval(()=>{if(!document.hidden&&root.getBoundingClientRect().bottom>0&&root.getBoundingClientRect().top<innerHeight)refresh();},300000);
})();
