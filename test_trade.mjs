import assert from 'node:assert/strict';
import {estimate,practiceDraft,mutationPayload,status} from './trade.js';
const state={session:{id:'session-id',revision:4,risk:125,balance:25000,floor:24500,fee:.77,slip:0},known_prices:{NQ:{price:100,fresh:true}}};
let d=practiceDraft(state,'MNQ',1);assert.equal(d.qty,1);assert.equal(d.target-100,2*(100-d.stop));assert.equal(estimate(d,state).error,'');
assert.match(estimate({...d,stop:101},state).error,/bracket/);
assert.match(estimate({...d,qty:10},state).error,/risk/);
assert.match(estimate({...d,qty:1.5},state).error,/whole/);
assert.match(estimate(d,{...state,known_prices:{NQ:{price:100,fresh:false}}}).error,/fresh/);
let payload=mutationPayload(state,60,{...d,id:'order-id'},'request-id');assert.equal(payload.id,'session-id');assert.equal(payload.tf,60);assert.equal(payload.revision,4);
assert.equal(status({...state.session,pending:d}),'Pending');assert.equal(status({...state.session,position:{...d,flatten:true}}),'Exit queued');
console.log('8 frontend behavior groups passed (practice defaults, bracket, size/risk, freshness, request identity, states).');
let flexible={...state,session:{...state.session,risk_enforced:false,max_micro:30}};
assert.equal(estimate({...d,qty:20},flexible).error,'');
assert.match(estimate({...d,qty:20},flexible).warning,/warning only/);
assert.match(estimate({...d,qty:31},flexible).error,/whole contracts/);
assert.match(estimate({...d,qty:20},{...flexible,session:{...flexible.session,challenge:{floor:24950,config:{max_micro:30}}}}).error,/challenge/);
console.log('Personal risk warning toggle, editable quantity cap and independent challenge limit passed.');
for(const side of [-1,1])for(const qty of [1,9,10]){
 const large={...state,session:{...state.session,risk:1e6,balance:2e6,floor:5e5}};
 const bracket=practiceDraft(large,'MNQ',side,qty);
 assert.equal(bracket.qty,qty);assert.ok(bracket.stop>0&&bracket.target>0);assert.equal(estimate(bracket,large).error,'');
}
console.log('High-budget long/short previews remain positive and quantity-aware.');

const {needsEntryStop}=await import('./trade.js');
assert.equal(needsEntryStop({},1,1,false),true);
assert.equal(needsEntryStop({risk_enforced:false},1,1,false),false);
assert.equal(needsEntryStop({risk_enforced:false,challenge:{}},1,1,false),true);
assert.equal(needsEntryStop({},1,1,true),false);
assert.equal(needsEntryStop({position:{side:1,qty:1}},-1,1,false),false);
assert.equal(needsEntryStop({pending:{side:1,qty:2,stop:100}},1,1,false),false);
assert.equal(needsEntryStop({pending:{side:1,qty:2,stop:100}},-1,2,false),false);
assert.equal(needsEntryStop({pending:{side:1,qty:2,stop:100}},-1,3,false),true);
console.log('Entry-stop preflight: enforced/default/warning/challenge, brackets, position exits, pending accumulation/cancellation/reversal passed.');
