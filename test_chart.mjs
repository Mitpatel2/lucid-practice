import assert from 'node:assert/strict';
import {Chart,priceTickStep} from './chart.js';
const chart=()=>Object.assign(Object.create(Chart.prototype),{cv:{dataset:{},parentElement:{style:{}}},tip:{hidden:true},count:100,offset:0,manual:false,draw(){},animateFollow(){this.followRequested=true;}});
const bars=Array.from({length:150},(_,i)=>({t:i*60,o:i,h:i+1,l:i-1,c:i,v:1}));
let c=chart();c.set(bars,'NQ',1,null,[],[],[]);assert.equal(c.cv.dataset.calculations,'1');
c.set(bars,'NQ',1,{entry:100},[],[],[]);assert.equal(c.cv.dataset.calculations,'1','overlay changes reuse indicators');
c.manual=true;c.offset=20;const priorRight=bars.length-c.offset;
c.set([...bars,{t:9000,o:150,h:151,l:149,c:150,v:1}],'NQ',1,null,[],[],[]);assert.equal(c.data.length-c.offset,priorRight,'manual viewport stays on same bar');
let end=c.data.length-c.offset,start=end-c.count,anchor=.23,at=start+c.count*anchor;c.zoom(.8,anchor);near(c.data.length-c.offset-c.count+c.count*anchor,at);
function near(a,b){assert.ok(Math.abs(a-b)<1e-9)}
c.manual=false;c.set([...c.data,{t:9060,o:151,h:152,l:150,c:151,v:1}],'NQ',1,null,[],[],[]);assert.equal(c.followRequested,true);
c.set(c.data,'NQ',1,null,[],[],[{type:'EMA',period:20,color:'#619cff',id:'a'}]);assert.equal(c.indicators.length,1);
console.log('5 chart behavior groups passed: calculation caching, manual viewport retention, cursor-anchored zoom, follow updates, configuration invalidation.');

c=chart();c.data=bars;c.zoom(.8);assert.equal(c.manual,false);assert.equal(c.offset,0);
c.geo={lo:100,hi:200};c.scalePrice(.5,.25);near(c.priceRange.lo,112.5);near(c.priceRange.hi,162.5);
c.scalePrice(1e-9);near(c.priceRange.hi-c.priceRange.lo,1);assert.equal(priceTickStep(1),.25);
c.autoPrice();assert.equal(c.priceRange,null);
console.log('Price scaling anchor, minimum span, tick precision, reset and follow-preserving zoom passed.');

// Playback releases an absolute scale; historical inspection retains it.
c=chart();c.set(bars,'NQ',1,null,[],[],[]);c.scalePrice(.5,.5,{lo:100,hi:200});
c.set([...bars,{t:9000,o:150,h:180,l:149,c:175,v:1}],'NQ',1,null,[],[],[]);
assert.ok(c.priceRange,'explicit price scaling survives new bars while time follows');
c.manual=true;c.scalePrice(.5,.5,{lo:100,hi:200});
c.set([...c.data,{t:9060,o:175,h:190,l:170,c:185,v:1}],'NQ',1,null,[],[],[]);
assert.ok(c.priceRange);
c.current();assert.equal(c.priceRange,null);assert.equal(c.manual,false);
c.displayRange=null;assert.deepEqual(c.resolvePriceRange(100,200),{lo:100,hi:200});
let r=c.resolvePriceRange(150,300);assert.ok(r.lo>100&&r.lo<150&&r.hi===300);
for(let i=0;i<50;i++)r=c.resolvePriceRange(150,300);
assert.deepEqual(r,{lo:150,hi:300});assert.equal(c.priceAnimating,false);
for(let i=0;i<50;i++)r=c.resolvePriceRange(190,210);
assert.deepEqual(r,{lo:190,hi:210});
c.drag={geometry:{lo:170,hi:250}};assert.deepEqual(c.resolvePriceRange(100,400),{lo:170,hi:250});
console.log('Dynamic price scale: new bars, manual inspection, current-bar reset, expansion/contraction convergence and bracket-drag stability passed.');

// Real pointer handlers: clicking must not disable follow, vertical drag must pan price.
c=chart();const listeners={};c.cv={dataset:{},style:{},addEventListener(k,fn){listeners[k]=fn},focus(){},setPointerCapture(){},hasPointerCapture(){return false}};c.data=bars;c.geo={lo:100,hi:200,top:40,bottom:240,right:600,dx:5};c.point=e=>({x:e.x,y:e.y});c.hits=[];c.tool='cursor';c.bind();
listeners.pointerdown({button:0,x:200,y:100,pointerId:1});
listeners.pointermove({x:201,y:101});assert.equal(c.manual,false,'incidental click motion retains follow');
listeners.pointermove({x:220,y:120});assert.equal(c.manual,true);near(c.priceRange.lo,110);near(c.priceRange.hi,210);near(c.offset,4);
c.displayRange={lo:110,hi:210};c.autoPrice();assert.equal(c.displayRange,null,'auto price clears stale animated scale immediately');
console.log('Pointer click tolerance, two-axis panning and immediate auto-scale reset passed.');

// Automatic expansion must never clip incoming extremes, even between animation frames.
c=chart();c.displayRange={lo:100,hi:200};
assert.deepEqual(c.resolvePriceRange(50,250),{lo:50,hi:250});
c.displayRange={lo:100,hi:200};r=c.resolvePriceRange(50,180);
assert.equal(r.lo,50);assert.ok(r.hi>=180);
console.log('Immediate expansion contains new extremes; contraction remains smooth.');
// Render-level regression: panning cannot hide the current-price label when in range.
c=chart();c.off={hidden:true};c.tip={hidden:false};c.set(bars,'NQ',1,null,[],[],[]);c.manual=true;c.cursor={x:20,y:100};c.priceRange={lo:100,hi:200};
const labels=[];const ctx=new Proxy({fillText:(text)=>labels.push(text),measureText:t=>({width:String(t).length*6})},{get:(obj,key)=>obj[key]??(()=>{})});
c.background(ctx,900,500);assert.equal(c.cv.dataset.currentPriceVisible,'true');assert.ok(labels.includes('149.00'),'last price remains rendered in manual mode');
c.set(bars,'NQ',30,null,[],[],[]);assert.equal(c.cursor,null);assert.equal(c.tip.hidden,true,'timeframe switch clears stale tooltip');
console.log('Rendered manual current-price label and stale timeframe tooltip checks passed.');

c=chart();c.set(bars,"NQ",1,null,[],[],[{type:"RSI",period:14,id:"r",visible:true},{type:"ATR",period:14,id:"a",visible:true}]);assert.equal(c.cv.parentElement.style.minHeight,"290px");
console.log("Oscillator panes reserve readable vertical space.");

// Numeric volume remains visible without the optional histogram, including zero/missing values.
for(const [v,expected] of [[12345,'12,345 contracts'],[0,'0 contracts'],[null,'unavailable'],[undefined,'unavailable']]){
 c=chart();c.off={hidden:true};labels.length=0;
 c.set([{t:0,o:100,h:102,l:99,c:101,v}], 'NQ',1,null,[],[],[]);
 c.background(ctx,390,300);
 assert.ok(labels.includes('NQ volume: '+expected));
 c.cursor={x:12,y:100};c.crosshair(ctx,390,300);
 assert.ok(c.tip.textContent.includes('NQ volume: '+expected));
}
c=chart();c.off={hidden:true};labels.length=0;
const partial={t:9000,o:150,h:152,l:149,c:151,v:2345,partial_coverage:true};
c.set(bars,'ES',5,null,[],[],[],partial);c.background(ctx,900,500);
assert.ok(labels.includes('ES volume: 2,345 contracts · so far · incomplete coverage'));
c.cursor={x:c.geo.ix(150),y:100};c.crosshair(ctx,900,500);
assert.ok(c.tip.textContent.includes('ES volume: 2,345 contracts · so far · incomplete coverage'));
console.log('Exact candle volume: header/tooltip, disabled histogram, zero, unavailable, ES source and partial forming coverage passed.');
