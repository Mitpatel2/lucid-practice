import assert from 'node:assert/strict';
import {normalizeConfig,calculate,catalog,defaults} from './indicators.js';
const bars=Array.from({length:300},(_,i)=>({t:1791842400+i*60,o:100+i/10,h:102+i/10,l:98+i/10,c:101+i/10,v:20+i}));
for(const type of Object.keys(catalog)){
 const cfg=normalizeConfig([defaults(type)])[0];const first=calculate(bars.slice(0,150),cfg).lines;
 const extended=calculate(bars,cfg).lines;
 first.forEach((line,j)=>assert.deepEqual(line.values,extended[j].values.slice(0,150),`${type} causal prefix`));
 for(const line of extended)assert(line.values.every(v=>v===null||Number.isFinite(v)),`${type} finite output`);
}
const n=normalizeConfig([{...defaults('MACD'),period:999,fast:999,slow:-1,signal:999,color:'bad'}])[0];
assert.equal(n.period,200);assert.equal(n.fast,100);assert.equal(n.slow,3);assert.equal(n.signal,100);assert.equal(n.color,'#619cff');
assert.equal(normalizeConfig(Array.from({length:20},()=>defaults('SMA'))).length,16);
console.log('8 indicator causal-prefix and finite-output checks; bounds, invalid-color fallback and 16-item cap passed.');
