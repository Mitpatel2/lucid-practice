// OB-v1: completed chart candles only; recognition starts at confirmation, not origin.
export function orderBlocks(bars,{lookback=12,bodyMultiple=1}={}){
 const zones=[];
 for(let i=lookback;i<bars.length;i++){
  const b=bars[i],prior=bars.slice(i-lookback,i);
  for(const z of zones){if(z.invalidated)continue;
   if(z.side===1?b.c<z.low:b.c>z.high){z.invalidated=b.t;z.status='invalidated'}
   else if(b.l<=z.high&&b.h>=z.low){z.mitigated??=b.t;z.status='mitigated'}
  }
  const typical=prior.reduce((a,b)=>a+b.h-b.l,0)/lookback;
  const side=b.c>Math.max(...prior.map(x=>x.h))?1:b.c<Math.min(...prior.map(x=>x.l))?-1:0;
  if(!side||Math.abs(b.c-b.o)<typical*bodyMultiple)continue;
  let origin=prior.findLast(x=>side===1?x.c<x.o:x.c>x.o);
  if(!origin||zones.some(z=>z.origin===origin.t&&z.side===side))continue;
  zones.push({origin:origin.t,confirmed:b.t,low:origin.l,high:origin.h,side,status:'active'});
 }
 return zones;
}
