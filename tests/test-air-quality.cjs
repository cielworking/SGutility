const assert=require('node:assert/strict');
const air=require('../air-quality.js');
assert.equal(air.band(100,'psi').label,'Moderate');
assert.equal(air.band(101,'psi').label,'Unhealthy');
assert.equal(air.band(55,'pm25').label,'Normal');
assert.equal(air.band(56,'pm25').label,'Elevated');
assert.equal(air.band(151,'pm25').label,'High');
assert.equal(air.band(251,'pm25').label,'Very high');
for(const missing of [null,undefined,-1,NaN,'0'])assert.equal(air.band(missing).label,'Unavailable');
assert.equal(air.band(0).label,'Good');
const rows=[
 {timestamp:'2026-10-19T03:00:00+08:00',readings:{psi_twenty_four_hourly:{north:103,east:5}}},
 {timestamp:'2026-10-19T01:00:00+08:00',readings:{psi_twenty_four_hourly:{north:101,east:4}}},
 {timestamp:'2026-10-19T03:00:00+08:00',readings:{psi_twenty_four_hourly:{north:104,east:6}}}
];
const result=air.points(rows,'north','psi');
assert.deepEqual(result.map(p=>p.value),[101,104]);
assert.equal(result[1].time-result[0].time,2*3600000,'Missing hours must remain gaps');
assert.deepEqual(air.points(rows,'west','psi'),[],'A missing region must not borrow another region’s readings');
console.log('Air-quality metric boundaries, missing data, region isolation and history gaps passed.');
