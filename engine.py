from challenge import update as update_challenge, entry_block, schedule, v2 as challenge_v2, unresolved, day as challenge_day
"""Local, causal OHLCV replay. No brokerage/network data dependencies."""
import csv, json, math, bisect, hashlib, uuid, os
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

POINT = {'NQ':20., 'ES':50., 'MNQ':2., 'MES':5.}
SOURCE = Path(__file__).parent/'data'

def timestamp(s):
    dt=datetime.fromisoformat(s.replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('Timestamp must include timezone')
    return int(dt.timestamp())

def load_data(source=SOURCE):
    data, manifest = {}, {}
    for symbol in ('NQ','ES'):
        path=source/f'{symbol}_yahoo_5m.csv'; rows={}; invalid=duplicates=0
        with path.open() as f:
            for r in csv.DictReader(f):
                try:
                    t=timestamp(r['ts_event']); values=[float(r[k]) for k in ('open','high','low','close','volume')]
                    o,h,l,c,v=values
                    if not all(math.isfinite(x) for x in values) or not (0<l<=min(o,c)<=max(o,c)<=h and v>=0) or t%300: raise ValueError()
                    if t in rows: duplicates+=1; continue
                    rows[t]=dict(t=t,o=o,h=h,l=l,c=c,v=v)
                except (ValueError,KeyError): invalid+=1
        bars=sorted(rows.values(),key=lambda b:b['t']); data[symbol]=bars
        manifest[symbol]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bars=len(bars),first=bars[0]['t'],last=bars[-1]['t']+300,invalid=invalid,duplicates=duplicates,gaps=sum(b['t']-a['t']!=300 for a,b in zip(bars,bars[1:])),base_minutes=5,order_flow='unavailable: OHLCV only',provenance='Existing combined archive; continuous-contract roll and Yahoo revisions can affect interpretation. NQ/ES proxy prices for micro simulation, not actual micro fills.')
    return data,manifest

def aggregate(bars, clock, minutes, base=300):
    if minutes not in (1,5,15,30,60,240) or minutes*60<base: raise ValueError('Supported: 5, 15, 30, 60, 240 minutes')
    width=minutes*60; groups={}
    for b in bars:
        if b['t']+base>clock: break
        key=b['t']//width*width
        if key+width<=clock: groups.setdefault(key,[]).append(b)
    result=[]
    for t,g in groups.items():
        if len(g)!=width//base or any(b['t']!=t+i*base for i,b in enumerate(g)): continue
        if len({b.get('contract') for b in g})>1: continue
        result.append(dict(t=t,o=g[0]['o'],h=max(x['h'] for x in g),l=min(x['l'] for x in g),c=g[-1]['c'],v=sum(x['v'] for x in g)))
    return result

def forming_bar(bars, clock, minutes, base=300):
    """Display only: never feed unfinished buckets into completed-bar features."""
    width=minutes*60
    start=clock//width*width
    if clock==start:return None
    g=[b for b in bars if start<=b['t'] and b['t']+base<=clock]
    if not g:return None
    contiguous=g[0]['t']==start and all(b['t']==start+i*base for i,b in enumerate(g))
    if len({b.get('contract') for b in g})>1:return None
    return dict(t=start,o=g[0]['o'],h=max(b['h'] for b in g),l=min(b['l'] for b in g),c=g[-1]['c'],v=sum(b['v'] for b in g),forming=True,partial_coverage=not contiguous,available=g[-1]['t']+base)

def evidence(bars,clock,base=300):
    return {'method':'manual replay','context':'Review your own trade thesis and risk decisions.','order_flow':'Unavailable: candle data only.'}

class Replay:
    def __init__(self,data,store,base_seconds=300,dataset="legacy-5m"):
        self.base=base_seconds;self.dataset=dataset
        self.data=data; self.times={k:[b['t'] for b in v] for k,v in data.items()};self.maps={k:{b['t']:b for b in v} for k,v in data.items()}
        self.timeline=sorted(set(self.times['NQ'])|set(self.times['ES']));self.store=Path(store);self.store.mkdir(parents=True,exist_ok=True)
    @contextmanager
    def transaction(self):
        # The HTTP server holds its global lock. Publish state and retry identity
        # together only after mutation and response construction both succeed.
        if getattr(self,'_transaction',False):raise RuntimeError('Nested session transaction')
        self._transaction=True;self._pending_save=None
        try:
            yield
            pending=self._pending_save
        finally:
            self._transaction=False;self._pending_save=None
        if pending is not None:self.save(pending)
    def save(self,s):
        if getattr(self,'_transaction',False):
            self._pending_save=s;return
        p=self.store/(s['id']+'.json');tmp=p.with_suffix('.tmp')
        body=json.dumps(s,allow_nan=False)
        with tmp.open('w') as f:
            f.write(body);f.flush();os.fsync(f.fileno())
        tmp.replace(p)
    def get(self,id):
        if not isinstance(id,str) or len(id)!=32 or any(c not in '0123456789abcdef' for c in id):raise ValueError('Invalid session ID')
        s=json.loads((self.store/(id+'.json')).read_text())
        self.upgrade(s)
        return s
    def upgrade(self,s):
        # Additive migration: old journals and string events remain intact.
        s.setdefault('revision',0);s.setdefault('draft',None);s.setdefault('ui',{})
        if 'cash_ledger' not in s:
            s['cash_ledger']=[{'at':t['exit_available'],'amount':t['net'],'kind':'legacy closed net'} for t in s['trades']]
            if s.get('position'):s['cash_ledger'].append({'at':s['position']['entry_at'],'amount':-s['fee']*s['position']['qty'],'kind':'legacy entry fee'})
        s.setdefault('activity',[]);s.setdefault('requests',[])
        for i,t in enumerate(s['trades']):t.setdefault('id',s['id']+'-legacy-'+str(i))
        for k in ('pending','position'):
            if s.get(k):s[k].setdefault('id',s['id']+'-'+k+'-'+str(s[k].get('decision',s['clock'])))
        return s
    def event(self,s,kind,reason='',order=None,price=None,at=None):
        self.upgrade(s)
        e=dict(id=uuid.uuid4().hex,kind=kind,at=s['clock'] if at is None else at,reason=reason,price=price,order_id=order.get('id') if order else None,instrument=order.get('instrument') if order else None)
        s['activity'].append(e)
        return e
    def predict(self,s,order):
        return {'available':False,'reason':'Manual practice edition: no private models or automated signals included.'}
    def draft(self,s,d):
        if d is not None and s['initial']>1e9:raise ValueError('This saved account exceeds the supported $1 billion balance. It is preserved; start a new attempt to trade.')
        if d is not None and entry_block(s):raise ValueError(entry_block(s))
        self.upgrade(s)
        if s['pending'] or s['position'] or s['ended']:raise ValueError('Finish the current trade before starting a draft')
        if d is None:
            if s['draft']:self.event(s,'Cancelled','Unsent draft discarded',s['draft'])
            s['draft']=None;self.save(s);return
        if d.get('instrument') not in POINT or d.get('side') not in (-1,1):raise ValueError('Invalid contract or direction')
        if not isinstance(d.get('qty'),int) or not 1<=d['qty']<=self.quantity_limit(s,d['instrument']):raise ValueError('Quantity exceeds this attempt contract cap')
        if not all(isinstance(d.get(k),(float,int)) and math.isfinite(d[k]) and d[k]>0 for k in ('stop','target')):raise ValueError('Enter finite positive prices')
        previous=s.get('draft')
        s['draft']={k:d[k] for k in ('instrument','side','qty','stop','target')}
        s['draft']['id']=previous['id'] if previous else uuid.uuid4().hex
        s['draft']['ml_prediction']=self.predict(s,s['draft'])
        if not previous:self.event(s,'Draft','Editable practice defaults; not submitted',s['draft'])
        self.save(s)
    def cancel(self,s):
        if not s['pending']:raise ValueError('No pending order')
        self.event(s,'Cancelled','Pending entry cancelled before execution',s['pending']);s['pending']=None;self.save(s)
    def create(self,date,balance=25000,risk=125,loss=500,fee=.77,slip=0):
        for x in (balance,risk,loss,fee,slip):
            if not math.isfinite(x) or x<0:raise ValueError('Settings must be finite and nonnegative')
        if balance>1e9:raise ValueError('Starting balance must not exceed $1 billion; larger accounts cannot be simulated reliably. Use a new attempt with a supported balance.')
        if not 0<risk<=loss<balance or slip%1:raise ValueError('Require 0 < risk <= loss < balance, integer slippage ticks')
        t=timestamp(date);i=bisect.bisect_left(self.timeline,t)
        if i==len(self.timeline):raise ValueError('Date outside history')
        if t<self.timeline[0]:raise ValueError('Date before history')
        if self.timeline[i]!=t:raise ValueError('No source bar at requested time. Next available UTC: '+datetime.fromtimestamp(self.timeline[i],timezone.utc).isoformat()+'. Choose that date explicitly; no session was created.')
        missing=[k for k in self.data if not self.maps[k].get(t)]
        if missing:raise ValueError('Missing '+', '.join(missing)+' source data at requested time. Choose a date with both NQ and ES coverage; no session was created.')
        s=dict(dataset=self.dataset,base_seconds=self.base,id=uuid.uuid4().hex,clock=self.timeline[i],start=self.timeline[i],balance=balance,initial=balance,risk=risk,floor=balance-loss,fee=fee,slip=slip,pending=None,position=None,trades=[],events=[],drawings=[],notes='',ended=False)
        self.upgrade(s);self.save(s);return s
    def checkpoint(self,s):
        """Immutable local snapshot; never served or included in the public bundle."""
        folder=self.store/'.replay-history';folder.mkdir(exist_ok=True)
        key=uuid.uuid4().hex
        path=folder/(key+'.json')
        with path.open('x') as f:
            json.dump(s,f,allow_nan=False);f.flush();os.fsync(f.fileno())
        return key
    def rewind(self,s):
        stack=s.get('rewind_stack',[])
        if not stack:raise ValueError('No earlier replay step is saved for this attempt.')
        key=stack[-1]
        if len(key)!=32 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Invalid replay checkpoint')
        prior=json.loads((self.store/'.replay-history'/(key+'.json')).read_text())
        if prior['id']!=s['id'] or prior['clock']>=s['clock']:raise ValueError('Checkpoint does not belong to this replay step')
        archive=self.checkpoint(s)
        # Preserve local review/layout edits and concurrency protection while restoring execution state.
        for field in ('ui','notes','revision','requests'):
            prior[field]=s.get(field,prior.get(field))
        prior['rewind_count']=s.get('rewind_count',0)+1
        prior['rewind_archives']=s.get('rewind_archives',[])+[archive]
        s.clear();s.update(prior);self.save(s)
    def visible(self,s,minutes=5):
        self.upgrade(s)
        if minutes==1 and self.base==300:minutes=5
        result={};forming={}
        if not hasattr(self,'candle_cache'):self.candle_cache={}
        for k,b in self.data.items():
            key=(k,s['clock'],minutes)
            if key not in self.candle_cache:
                end=bisect.bisect_right(self.times[k],s['clock']-self.base)
                # Fetch only the chart window, expanding through gaps when needed.
                # Keep the original 40-day ceiling and exact last-2000 result.
                ceiling=min(end,60000 if self.base==60 else 12000)
                count=min(ceiling,2002*minutes*60//self.base)
                while True:
                    recent=b[end-count:end]
                    completed=aggregate(recent,s['clock'],minutes,self.base)
                    if len(completed)>=2000 or count>=ceiling:break
                    count=min(ceiling,max(1,count*2))
                self.candle_cache[key]=(completed[-2000:],forming_bar(recent,s['clock'],minutes,self.base))
                if len(self.candle_cache)>16:self.candle_cache.pop(next(iter(self.candle_cache)))
            result[k],forming[k]=self.candle_cache[key]
        last={k:(self.maps[k].get(s['clock']-self.base) or {}) for k in self.data}
        position=s['position'];unrealized=None
        if position and last[position['source']]:unrealized=(last[position['source']]['c']-position['entry'])*position['side']*position['qty']*POINT[position['instrument']]
        known={}
        for k in self.data:
            i=bisect.bisect_right(self.times[k],s['clock']-self.base)-1
            b=self.data[k][i] if i>=0 else None
            known[k]=dict(price=b['c'],available=b['t']+self.base,fresh=b['t']+self.base==s['clock']) if b else None
        markers=[]
        for p in s['trades']+([position] if position else []):
            markers.append(dict(id=p['id']+'-entry',trade_id=p['id'],kind='Entry',at=p['entry_at'],available=p['entry_at']+self.base,price=p.get('original_entry',p['entry']),source=p['source'],side=p['side'],qty=p.get('original_qty',p['qty']),instrument=p['instrument']))
            if 'exit' in p:markers.append(dict(id=p['id']+'-exit',trade_id=p['id'],kind='Exit',at=p.get('exit_event_at',p['exit_available']-self.base),available=p['exit_available'],price=p['exit'],source=p['source'],side=p['side'],qty=p['qty'],instrument=p['instrument'],reason=p['reason']))
        if s.get('draft'):
            s={**s,'draft':{**s['draft'],'ml_prediction':self.predict(s,s['draft'])}}
        return dict(session=s,entry_block=entry_block(s),challenge_schedule=schedule(s,s['clock']) if challenge_v2(s) else None,bars=result,forming_bars=forming,chart_timeframe=minutes,unrealized=unrealized,known_prices=known,markers=markers,timeframes=([1] if self.base==60 else [])+[5,15,30,60,240])
    def review(self,s,symbol):
        end=bisect.bisect_right(self.times[symbol],s['clock']-self.base)
        return evidence(self.data[symbol][max(0,end-(60000 if self.base==60 else 12000)):end],s['clock'],self.base)
    def risk_budget(self,s):
        personal=min(s['risk'],s['balance']-s['floor']) if s.get('risk_enforced',True) else float('inf')
        return min(personal,s['balance']-s['challenge']['floor']) if s.get('challenge') else personal
    def risk_settings(self,s,enforced,risk,loss,max_micro):
        if not isinstance(enforced,bool):raise ValueError('Risk enforcement must be on or off')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 or v>1e9 for v in (risk,loss)):raise ValueError('Use positive finite dollar limits up to 1 billion')
        if isinstance(max_micro,bool) or not isinstance(max_micro,int) or not 1<=max_micro<=1000:raise ValueError('Contract limit must be 1–1000 micro equivalents')
        if s['pending'] or (s['position'] and s['position'].get('scale_pending')):raise ValueError('Cancel or execute the queued order before changing risk controls')
        before={k:s.get(k) for k in ('risk_enforced','risk','floor','max_micro')}
        s.update(risk_enforced=enforced,risk=float(risk),floor=s['initial']-float(loss),max_micro=max_micro)
        s.setdefault('risk_changes',[]).append({'at':s['clock'],'before':before,'after':{k:s[k] for k in before}})
        self.event(s,'Risk settings changed','Personal risk controls '+('enforced' if enforced else 'warning only')+'; challenge rules unchanged')
        self.save(s)
    def quantity_limit(self,s,instrument):
        c=s.get('challenge',{}).get('config',{})
        if c.get('micro_only') and not instrument.startswith('M'):return 0
        cap=min(int(c.get('max_micro',1000)),s.get('max_micro',int(c.get('max_micro',10))));ratio=int(c.get('micro_per_mini',10))
        return cap if instrument.startswith('M') else max(0,cap//ratio)
    def scale(self,s,delta,accumulate=False):
        p=s['position']
        if not p or p.get('flatten') or (p.get('scale_pending') and not accumulate):raise ValueError('An open position without a queued change is required')
        if isinstance(delta,bool) or not isinstance(delta,int) or delta==0:raise ValueError('Use a nonzero whole-contract change')
        delta+=p.get('scale_pending',{}).get('delta',0)
        if delta==0:
            p.pop('scale_pending',None);self.save(s);return
        if delta<0 and -delta>p['qty']:raise ValueError('Cannot reduce more than the open quantity')
        if delta>0 and entry_block(s):raise ValueError(entry_block(s))
        if delta>0 and s.get('challenge',{}).get('paused_day'):raise ValueError('Daily loss pause blocks adding exposure')
        if delta>0 and (p['qty']+delta>self.quantity_limit(s,p['instrument']) or s.get('challenge',{}).get('status')=='failed'):raise ValueError('Add exceeds contract cap or challenge has failed')
        p['scale_pending']={'delta':delta,'decision':s['clock']}
        p['management'].append({'at':s['clock'],'action':'scale queued','delta':delta,'note':'Original prediction applies to original bracket; size change has no new ML claim'})
        self.event(s,'Scale queued','Executes at next source-bar open',p);self.save(s)
    def execute_scale(self,s,p,b,t):
        change=p.pop('scale_pending',None)
        if not change:return
        delta=change['delta'];side=p['side'];unit=POINT[p['instrument']]
        if not self.inside_bracket(p,b['o']):
            self.event(s,'Scale rejected','Opening price outside bracket; exit rules take priority',p,at=t);return
        fill=b['o']+(side if delta>0 else -side)*s['slip']*.25
        p.setdefault('original_qty',p['qty']);p.setdefault('original_entry',p['entry']);p.setdefault('realized_gross',0);p.setdefault('fees_paid',s['fee']*p['qty'])
        if delta>0:
            if entry_block(s,t):
                self.event(s,'Scale rejected',entry_block(s,t),p,at=t);return
            qty=p['qty']+delta;entry=(p['entry']*p['qty']+fill*delta)/qty
            cost=s['fee']*delta;risk=(abs(entry-p['stop'])*unit*qty+p['fees_paid']+cost+s['fee']*qty+s['slip']*.25*unit*qty) if p['stop'] is not None else None
            stop_cash=(s['balance']-cost+(p['stop']-entry)*side*unit*qty-s['fee']*qty-s['slip']*.25*unit*qty) if p['stop'] is not None else -math.inf
            if qty>self.quantity_limit(s,p['instrument']) or (s.get('risk_enforced',True) and (risk is None or risk>s['risk'] or stop_cash<s['floor'])) or (s.get('challenge') and stop_cash<s['challenge']['floor']) or not self.inside_bracket(p,fill):
                self.event(s,'Scale rejected','Fill-time risk, bracket or contract cap exceeded',p,fill,t);return
            p['entry']=entry;p['qty']=qty;p['fees_paid']+=cost;s['balance']-=cost;s['cash_ledger'].append({'at':t,'amount':-cost,'kind':'scale entry fee'})
            p['current_bracket_risk']=risk
        else:
            q=-delta
            if q==p['qty']:self.close(s,fill,t+self.base,'scale to flat');return
            gross=(fill-p['entry'])*side*unit*q;fee=s['fee']*q
            s['balance']+=gross-fee;s['cash_ledger'].append({'at':t,'amount':gross-fee,'kind':'partial exit'});p['realized_gross']+=gross;p['fees_paid']+=fee;p['qty']-=q
        p['management'].append({'at':t,'action':'scale filled','delta':delta,'price':fill,'qty_after':p['qty']})
        self.event(s,'Scaled','Added contracts' if delta>0 else 'Partial close',p,fill,t)
    @staticmethod
    def inside_bracket(p,price):
        return (p.get('stop') is None or (price-p['stop'])*p['side']>0) and (p.get('target') is None or (p['target']-price)*p['side']>0)
    def quick_order(self,s,instrument,side,qty,stop=None,target=None):
        if instrument not in POINT or side not in (-1,1) or isinstance(qty,bool) or not isinstance(qty,int) or qty<1:raise ValueError('Invalid market order')
        held=s['position'] or s['pending']
        if held and held['instrument']!=instrument:raise ValueError('Flatten the current instrument before switching contracts')
        if s['position']:
            self.scale(s,qty*side*s['position']['side'],accumulate=True);return
        if s['pending']:
            old=s['pending'];net=old['qty']*old['side']+qty*side
            if net==0:self.cancel(s);return
            newside=1 if net>0 else -1
            # Preserve the existing bracket when accumulating; validate the combined exposure.
            if newside==old['side']:stop,target=old['stop'],old['target']
            s['pending']=None
            try:self.order(s,instrument,newside,abs(net),stop,target)
            except Exception:s['pending']=old;raise
            return
        self.order(s,instrument,side,qty,stop,target)
    def order(self,s,instrument,side,qty,stop,target):
        if s['initial']>1e9:raise ValueError('This saved account exceeds the supported $1 billion balance. Start a new attempt to trade.')
        if entry_block(s):raise ValueError(entry_block(s))
        if s.get('challenge',{}).get('paused_day'):raise ValueError('Daily loss pause; advance to the next session or start a new attempt')
        if s.get('challenge',{}).get('status')=='failed':raise ValueError('Custom training challenge failed; start a new attempt')
        if s['ended'] or s['position'] or s['pending']:raise ValueError('Finish the current order/position first')
        if instrument not in POINT or side not in (-1,1) or not isinstance(qty,int) or not 1<=qty<=self.quantity_limit(s,instrument):raise ValueError('Invalid instrument, direction or quantity (exceeds the attempt contract cap)')
        if stop is None and (s.get('risk_enforced',True) or s.get('challenge')):raise ValueError('No-stop orders require personal practice with Risk controls set to warning only. Risk cannot be bounded without a stop.')
        if not all(x is None or (math.isfinite(x) and x>0 and abs(x*4-round(x*4))<1e-7) for x in (stop,target)):raise ValueError('Stops/targets must be positive quarter-point prices')
        source='NQ' if instrument.endswith('NQ') else 'ES'
        last=self.maps[source].get(s['clock']-self.base)
        if not last:raise ValueError('No fresh completed bar for this instrument')
        price=last['c'];risk=(abs(price-stop)*POINT[instrument]+2*s['fee']+2*s['slip']*.25*POINT[instrument])*qty if stop is not None else None
        if not self.inside_bracket(dict(stop=stop,target=target,side=side),price):raise ValueError('Stop/target are on the wrong side')
        if risk is not None and risk>self.risk_budget(s):raise ValueError('Order exceeds planned risk or remaining loss budget')
        s['pending']=dict(id=(s.get('draft') or {}).get('id',uuid.uuid4().hex),instrument=instrument,source=source,side=side,qty=qty,stop=stop,target=target,decision=s['clock'],entry_review=self.review(s,source),requested_risk=risk)
        if last.get('contract'):s['pending']['source_contract']=last['contract']
        review=s['pending']['entry_review'];review['ml_prediction']=self.predict(s,s['pending']); expected='bullish' if side==1 else 'bearish'
        review['direction_context']={k:('aligned' if v==expected else 'opposed' if v in ('bullish','bearish') else 'unavailable or mixed') for k,v in review.get('higher_timeframe',{}).items()}
        review['risk_at_decision']={'contracts':qty,'estimated_dollars':risk,'limit':s['risk'],'remaining_loss_budget':s['balance']-s['floor'],'planned_RR_before_fill':abs(target-price)/abs(price-stop) if stop is not None and target is not None else None}
        s['draft']=None
        self.event(s,'Pending','Fills at the next base-bar open; waiting for Step or Play',s['pending'],price)
        self.save(s)
    def close(self,s,price,t,reason):
        p=s['position'];gross=(price-p['entry'])*p['side']*p['qty']*POINT[p['instrument']];fees=p.get('fees_paid',s['fee']*p['qty'])+s['fee']*p['qty'];net=p.get('realized_gross',0)+gross-fees
        s['balance']+=gross-s['fee']*p['qty'];s['cash_ledger'].append({'at':t,'amount':gross-s['fee']*p['qty'],'kind':'exit'})
        p.update(exit=price,exit_available=t,reason=reason,gross=p.get('realized_gross',0)+gross,fees=fees,net=net,realized_R=net/p['planned_risk'] if p['planned_risk'] else None,risk_overrun=net < -p['planned_risk']-1e-8 if p['planned_risk'] is not None else None,review={'entry':p['entry_review'],'management':p['management'],'outcome':{'net':net,'reason':reason,'assessment':'Outcome is not proof of entry quality or a profitable edge.'}})
        self.event(s,'Closed',reason,p,price,t)
        s['trades'].append(p);s['position']=None
    def step(self,s):
        if s['ended']:return
        t=s['clock']
        # Advance the risk day before any new-session execution, without future marks.
        if challenge_v2(s):
            last=s['position'];mark=s['balance']
            if last:
                prev=self.maps[last['source']].get(t-self.base)
                mark=None if not prev else mark+(prev['c']-last['entry'])*last['side']*last['qty']*POINT[last['instrument']]-s['fee']*last['qty']
            if s['challenge']['day']!=challenge_day(t):update_challenge(s,mark)
            a=s['challenge'];x=schedule(s,t);held=s['position']
            if held and (x.get('blocked_reason') or (x.get('market_close') and t>=x['market_close'])):
                unresolved(s,'Holiday exit cannot be verified; no fill invented during unknown firm hours or exchange closure')
                a['status']='failed' if a['status']=='failed' else 'unverified';s['ended']=True;self.save(s);return
            due=held and (a.get('liquidate_next_open') or x['closed'] or (x['close'] and t>=x['close']))
            straddle=held and x['close'] and t<x['close']<t+self.base
            if straddle or (due and x['close'] and t>x['close'] and not a.get('liquidate_next_open')):
                unresolved(s,'Required close has no exact executable base event; position and outcome unresolved')
                a['status']='failed' if a['status']=='failed' else 'unverified';s['ended']=True;self.save(s);return
            if due:
                b=self.maps[held['source']].get(t)
                if not b or (held.get('source_contract') and b.get('contract')!=held['source_contract']):
                    unresolved(s,'Required liquidation quote missing; position and outcome unresolved')
                    a['status']='failed' if a['status']=='failed' else 'unverified';s['ended']=True;self.save(s);return
                reason=a.pop('liquidate_next_open',None) or 'mandatory challenge session close'
                held.pop('scale_pending',None)
                self.close(s,b['o']-held['side']*s['slip']*.25,t,reason)
                s['trades'][-1]['exit_event_at']=t
            if entry_block(s,t) and s['pending']:
                self.event(s,'Rejected',entry_block(s,t),s['pending']);s['pending']=None
        p=s['position'];pending=s['pending'];bar_cash=s['balance']
        if pending:
            s['pending']=None;b=self.maps[pending['source']].get(t)
            if not b or (pending.get('source_contract') and b.get('contract')!=pending['source_contract']):
                s['events'].append('Pending entry cancelled: missing next bar or contract changed');self.event(s,'Rejected','Missing exact next bar or contract changed',pending)
            else:
                price=b['o']+pending['side']*s['slip']*.25
                risk=(abs(price-pending['stop'])*POINT[pending['instrument']]+2*s['fee']+s['slip']*.25*POINT[pending['instrument']])*pending['qty'] if pending['stop'] is not None else None
                valid=self.inside_bracket(pending,price) and (pending['stop'] is not None or (not s.get('risk_enforced',True) and not s.get('challenge')))
                if not valid or (risk is not None and risk>self.risk_budget(s)):
                    reason='Next open is outside the submitted bracket' if not valid else 'Actual fill-time risk exceeds the available budget'
                    s['events'].append('Pending entry rejected at actual next open: bracket or risk budget');self.event(s,'Rejected',reason,pending,price,t)
                else:
                    p=dict(pending,entry=price,entry_at=t,planned_risk=risk,planned_RR=abs(pending['target']-price)/abs(price-pending['stop']) if pending['target'] is not None and pending['stop'] is not None else None,management=[],flatten=False)
                    s['position']=p;s['balance']-=s['fee']*p['qty'];s['cash_ledger'].append({'at':t,'amount':-s['fee']*p['qty'],'kind':'entry fee'})
                    self.event(s,'Open','Entry filled at next base-bar open',p,price,t)
        if p:
            b=self.maps[p['source']].get(t)
            if not b or (p.get('source_contract') and b.get('contract')!=p['source_contract']):
                s['events'].append('Execution halted: missing held-instrument bar; outcome unresolved');s['ended']=True
            else:
                self.execute_scale(s,p,b,t)
                bar_cash=s['balance']
                if not s['position']:p=None
            if p and b and not s['ended']:
                side=p['side'];stop=p['stop'];target=p['target'];exit=None;reason=None
                if p.get('flatten'):exit=b['o']-side*s['slip']*.25;reason='manual next-open exit'
                elif stop is not None and (b['o']<=stop if side==1 else b['o']>=stop):exit=b['o']-side*s['slip']*.25;reason='gap through stop'
                elif target is not None and (b['o']>=target if side==1 else b['o']<=target):exit=target;reason='target (no favorable gap improvement)'
                else:
                    hitstop=stop is not None and (b['l']<=stop if side==1 else b['h']>=stop)
                    hittarget=target is not None and (b['h']>=target if side==1 else b['l']<=target)
                    if hitstop:exit=stop-side*s['slip']*.25;reason='ambiguous bar: stop first' if hittarget else 'stop'
                    elif hittarget:exit=target;reason='target'
                if exit is not None:self.close(s,exit,t+self.base,reason)
        uncertainty=bool(p and 'original_qty' in p and not challenge_v2(s))
        if p and s.get('challenge'):
            b=self.maps[p['source']].get(t);a=s['challenge'];c=a['config']
            if b:
                unit=p['qty']*POINT[p['instrument']]
                # Conservative possible equity bounds. Exit bars cannot reveal the path before exit.
                entry_cash=bar_cash if challenge_v2(s) else (s['balance'] if s['position'] else s['balance']-(s['trades'][-1]['gross']-s['fee']*p['qty']))
                lows=entry_cash+(b['l' if p['side']==1 else 'h']-p['entry'])*p['side']*unit-s['fee']*p['qty']
                highs=entry_cash+(b['h' if p['side']==1 else 'l']-p['entry'])*p['side']*unit-s['fee']*p['qty']
                possible_floor=a['floor']
                if c['mode']=='intraday':possible_floor=max(possible_floor,min(highs-c['drawdown'],s['initial']+c['lock_profit']))
                uncertainty=uncertainty or lows<=possible_floor or (c['daily_basis']=='equity' and c['daily_loss']>0 and a['day_start']-lows>=c['daily_loss'])
                if challenge_v2(s) and s['position']:
                    # Position survived the whole bar: its low equity was observed,
                    # although a broker's intrabar liquidation fill is unknowable.
                    if lows<=a['floor']:
                        a['status']='failed'
                        a['reasons']=list(dict.fromkeys(a['reasons']+['Maximum loss floor touched within completed bar']))
                        a['liquidate_next_open']='Maximum loss liquidation after completed-bar breach'
                    if c['daily_loss'] and c['daily_basis']=='equity' and a['day_start']-lows>=c['daily_loss']:
                        if c['daily_action']=='pause':a['paused_day']=a['day']
                        else:
                            a['status']='failed';a['reasons']=list(dict.fromkeys(a['reasons']+['Daily loss limit touched within completed bar']))
                        a['liquidate_next_open']='Daily loss liquidation after completed-bar breach'
                # A hidden peak can affect later trailing thresholds; do not certify a pass.
                if c['mode']=='intraday' and highs>a['highwater']:uncertainty=True
            else:uncertainty=True
        s['clock']=t+self.base
        i=bisect.bisect_left(self.timeline,s['clock'])
        if i==len(self.timeline):s['ended']=True
        # Never skip time: each step advances exactly self.base seconds, including gaps.
        if s.get('risk_enforced',True) and s['balance']<=s['floor'] and not s['position']:s['ended']=True;s['events'].append('Personal realized-equity floor reached; session stopped')
        equity=s['balance']
        if s['position']:
            p=s['position'];b=self.maps[p['source']].get(t)
            equity=None if not b else s['balance']+(b['c']-p['entry'])*p['side']*p['qty']*POINT[p['instrument']]-s['fee']*p['qty']
        if s['ended'] and s['position'] and challenge_v2(s):unresolved(s,'Recording ended with an open position; future mandatory close unresolved')
        update_challenge(s,equity,uncertainty)
        a=s.get('challenge',{})
        if a.get('status') in ('failed','passed','criteria_met_unverified') and not s['position']:
            s['ended']=True;s['pending']=None;s['draft']=None
            s['end_reason']='Challenge '+a['status'].replace('_',' ')
        self.save(s)
    def manage(self,s,stop=None,flatten=False):
        p=s['position']
        if not p:raise ValueError('No open position')
        if flatten:p.pop('scale_pending',None);p['flatten']=True;p['management'].append({'at':s['clock'],'action':'flatten next open'})
        else:
            if stop is None or not math.isfinite(stop) or stop<=0 or abs(stop*4-round(stop*4))>1e-7:raise ValueError('Invalid stop tick')
            last=self.maps[p['source']].get(s['clock']-self.base)
            if not last:raise ValueError('No fresh price')
            if (stop>=last['c'] or (p['stop'] is not None and stop<p['stop'])) if p['side']==1 else (stop<=last['c'] or (p['stop'] is not None and stop>p['stop'])):raise ValueError('Only tighten a stop, on the correct side of current close')
            p['management'].append({'at':s['clock'],'action':'tighten stop','old':p['stop'],'new':stop});p['stop']=stop
        self.event(s,'Exit queued' if flatten else 'Stop updated','Next-open close requested' if flatten else 'Stop tightened for subsequent bars',p,None if flatten else stop)
        self.save(s)

class ReviewModel:
    """Future extension point: causal features only; no unvalidated ML scores."""
    def predict(self, features):
        return {'available':False,'reason':'No independently validated model installed'}
