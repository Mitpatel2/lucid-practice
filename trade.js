export const POINT={MNQ:2,MES:5,NQ:20,ES:50};
export const source=i=>i.endsWith('NQ')?'NQ':'ES';
export const snap=n=>Math.round(n*4)/4;
export const money=n=>Number.isFinite(n)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n):'—';
export const price=n=>Number.isFinite(n)?n.toFixed(2):'—';
export function estimate(d,state){
 if(!d||!state)return {error:'Start a replay first.'};
 const s=state.session,k=state.known_prices[source(d.instrument)],entry=k?.price,p=POINT[d.instrument],q=d.qty;
 const costs=q*(2*s.fee+2*s.slip*.25*p),risk=Math.abs(entry-d.stop)*p*q+costs,reward=Math.abs(d.target-entry)*p*q-costs;
 const cap=Math.min(s.max_micro??s.challenge?.config.max_micro??10,s.challenge?.config.max_micro??1000),personalExceeded=risk>Math.min(s.risk,s.balance-s.floor)+1e-7;
 let error='';
 if(!k?.fresh)error='No fresh completed source-bar price. Step to a liquid session.';
 else if(!Number.isSafeInteger(q)||q<1||q>(d.instrument.startsWith('M')?cap:Math.floor(cap/(s.challenge?.config.micro_per_mini??10))))error='Use whole contracts within this attempt contract cap.';
 else if(![d.stop,d.target].every(x=>Number.isFinite(x)&&x>0&&Math.abs(x*4-Math.round(x*4))<1e-7))error='Use positive prices in 0.25-point ticks.';
 else if(!(d.side===1?d.stop<entry&&entry<d.target:d.target<entry&&entry<d.stop))error='Stop and target must bracket entry in the selected direction.';
 else if(s.challenge&&risk>s.balance-s.challenge.floor+1e-7)error='Estimated risk exceeds the challenge loss allowance.';
 else if(s.risk_enforced!==false&&personalExceeded)error='Estimated risk exceeds the trade limit or remaining loss allowance.';
 else if(s.ended)error='This replay has ended. Start another attempt.';
 return {entry,risk,reward,ratio:reward/risk,distance:Math.abs(entry-d.stop),error,warning:s.risk_enforced===false&&personalExceeded?'Above your personal risk allowance — warning only.':'',costs};
}
export function quantityLimit(s,instrument){
 if(s.challenge?.config.micro_only&&!instrument.startsWith('M'))return 0;
 const cap=Math.min(s.max_micro??s.challenge?.config.max_micro??10,s.challenge?.config.max_micro??1000);
 return instrument.startsWith('M')?cap:Math.floor(cap/(s.challenge?.config.micro_per_mini??10));
}
export function practiceDraft(state,instrument,side,qty=1){
 const s=state.session,p=POINT[instrument],entry=state.known_prices[source(instrument)]?.price;
 if(!Number.isFinite(entry)||entry<=.5)return null;
 const allowance=Math.min(s.risk,s.balance-Math.max(s.floor,s.challenge?.floor??s.floor))*.5; // half of available budget provides room; explicitly editable
 // An editable preview, not a recommendation: never turn a large dollar budget into a negative price.
 const ranges=(state.bars?.[source(instrument)]||[]).slice(-20).map(b=>b.h-b.l).filter(x=>Number.isFinite(x)&&x>0);
 const typical=ranges.length?ranges.reduce((a,b)=>a+b,0)/ranges.length:entry/4;
 const affordable=Math.max(0,allowance/qty-2*s.fee-2*s.slip*.25*p)/p;
 const distance=Math.max(.25,Math.floor(Math.min(affordable,typical,entry/4)*4)/4);
 return {instrument,side,qty,stop:snap(entry-side*distance),target:snap(entry+side*distance*2)};
}
export function status(s){
 if(s.position)return s.position.flatten?'Exit queued':'Open';
 if(s.pending)return 'Pending';if(s.draft)return 'Draft';
 let e=s.activity?.at(-1);return ['Closed','Cancelled','Rejected'].includes(e?.kind)?e.kind:s.ended?'Ended':'Flat';
}
export function mutationPayload(state,tf,data,requestId){return {...data,id:state?.session.id,revision:state?.session.revision,request_id:requestId,tf}}

export function needsEntryStop(s,side,qty,brackets){
 if(!s||brackets||(s.risk_enforced===false&&!s.challenge)||s.position)return false;
 if(!s.pending)return true;
 const p=s.pending,net=p.qty*p.side+qty*side;
 if(net===0)return false;
 return Math.sign(net)!==p.side||p.stop==null;
}
