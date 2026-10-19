"""Versioned local challenge simulation. Saved v1 attempts retain v1 semantics."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from copy import deepcopy
import challenge_v1 as legacy

day=legacy.day
ZONE=ZoneInfo('America/Chicago')
TERMINAL=('passed','criteria_met_unverified','failed')

def v2(s):return s.get('challenge',{}).get('version')=='custom-v2'

def unresolved(s,message):
    a=s.get('challenge')
    if a and message not in a['uncertainties']:a['uncertainties'].append(message)

def configure(s,c):
    if not c:return
    c=deepcopy(c)
    legacy.configure(s,c)  # validation of common numeric fields
    a=s['challenge'];a['version']='custom-v2';a['uncertainties']=[]
    # Reference is a frozen snapshot, never reread from a later catalog.
    ref=c.get('reference') or {};a['limitations']=list(ref.get('limitations',[]))
    if ref and any(c.get(k)!=val for k,val in ref.get('config',{}).items()):
        a['limitations'].append('Edited custom rules differ from the selected official reference.')
    a['daily_locked']={};a['eod_dates']=[];a['terminal_at']=None
    a['status']='active';a['config']=deepcopy(s['challenge']['config'])
    for key in ('flatten_time','entry_cutoff','eod_time'):
        if a['config'].get(key):
            datetime.strptime(a['config'][key],'%H:%M:%S')
    for d,t in a['config'].get('session_overrides',{}).items():
        datetime.strptime(d,'%Y-%m-%d')
        if t is not None:datetime.strptime(t,'%H:%M:%S')
    calendar=a['config'].get('dated_calendar')
    if calendar:
        for k in ('start','end'):datetime.strptime(calendar[k],'%Y-%m-%d')
        for d,row in calendar['dates'].items():
            datetime.strptime(d,'%Y-%m-%d')
            for k in ('market_close','flatten','entry','cash_capture'):
                if row.get(k):datetime.strptime(row[k],'%H:%M:%S')
            if row.get('flatten') and row['flatten']>=row['market_close']:
                raise ValueError('Firm flatten must precede the exchange no-matching boundary')
    update(s,s['balance'])

def schedule(s,t):
    c=s['challenge']['config'];dt=datetime.fromtimestamp(t,ZONE)
    # Session is named for its closing calendar date.
    date=(dt+timedelta(days=dt.hour>=17)).date()
    key=date.isoformat();override=c.get('session_overrides',{})
    close=override.get(key,c.get('flatten_time'))
    def stamp(text):return int(datetime.fromisoformat(key+'T'+text).replace(tzinfo=ZONE).timestamp())
    result=dict(date=key,close=stamp(close) if close else None,
                entry=stamp(min(close,c.get('entry_cutoff',close))) if close else None,
                eod=stamp(c.get('eod_time',close)) if close else None,
                closed=(date.weekday()>=5 or (key in override and close is None)))
    # Opt-in frozen snapshots only; existing attempts keep their original schedule.
    calendar=c.get('dated_calendar')
    if calendar:
        row=calendar['dates'].get(key)
        result.update(calendar_version=calendar['version'],holiday=None,market_close=None,
                      verification='covered' if calendar['start']<=key<=calendar['end'] else 'outside audited dates')
        if row:
            result.update(holiday=row['name'],market_close=stamp(row['market_close']),
                          close=stamp(row['flatten']) if row.get('flatten') else None,
                          entry=stamp(row['entry']) if row.get('entry') else None,
                          eod=stamp(row['cash_capture']) if row.get('cash_capture') else None,
                          verification=row['status'],note=row['note'],sources=row['sources'],
                          blocked_reason=None if row.get('flatten') else 'Holiday firm exit time unverified; new exposure blocked for this session')
    return result

def entry_block(s,t=None):
    a=s.get('challenge')
    if not a:return None
    if not v2(s):return None  # Existing engine retains v1 entry checks.
    if a['status'] in TERMINAL:return 'Challenge attempt is terminal; start a fresh attempt'
    if a.get('paused_day'):return 'Daily loss pause until the next session'
    if not v2(s):return None
    x=schedule(s,s['clock'] if t is None else t)
    if x.get('blocked_reason'):return x['blocked_reason']
    if x['closed'] or (x['entry'] and (s['clock'] if t is None else t)>=x['entry']):return 'Outside this challenge entry window'
    return None

def update(s,equity,uncertain=False):
    a=s.get('challenge')
    if not a:return
    if not v2(s):return legacy.update(s,equity,uncertain)
    if a.get('terminal_at') is not None:return  # no retrospective pass repaint
    c=a['config'];cash=s['balance'];d=day(s['clock'])
    if d!=a['day']:
        a.pop('paused_day',None)
        if 'next_floor' in a:a['floor']=max(a['floor'],a.pop('next_floor'))
        # Custom untimed accounts retain rollover EOD semantics.
        if c['mode']=='eod' and not c.get('eod_time'):
            a['highwater']=max(a['highwater'],a['last_cash'])
            a['floor']=max(a['floor'],min(a['highwater']-c['drawdown'],s['initial']+c['lock_profit']))
        a['day_start']=a['last_cash'];a['day']=d
    a['daily'][d]=cash-a['day_start'];a['last_cash']=cash;a['checked_at']=s['clock']
    if equity is None or uncertain:unresolved(s,'Intrabar path or missing mark cannot verify all rule touches')
    if c['mode']=='intraday' and equity is not None:
        a['highwater']=max(a['highwater'],equity)
        a['floor']=max(a['floor'],min(a['highwater']-c['drawdown'],s['initial']+c['lock_profit']))
    reasons=[]
    if equity is not None and equity<=a['floor']:reasons.append('Maximum loss floor touched')
    value=cash if c['daily_basis']=='realized' else equity
    if c['daily_loss'] and value is not None and a['day_start']-value>=c['daily_loss']:
        if c['daily_action']=='fail':reasons.append('Daily loss limit touched')
        else:a['paused_day']=d
        if s['position']:a['liquidate_next_open']='Daily loss liquidation after observed breach'
    if reasons:
        a['reasons']=list(dict.fromkeys(a['reasons']+reasons));a['status']='failed'
        if s['position']:a['liquidate_next_open']='Maximum loss liquidation after observed breach'
    x=schedule(s,s['clock'])
    if x.get('blocked_reason'):unresolved(s,x['blocked_reason'])
    if x['eod'] and s['clock']>=x['eod'] and x['date'] not in a['eod_dates'] and not (s['position'] and s['clock']==x['close']):
        if s['position']:unresolved(s,'Position unresolved at required end-of-day calculation')
        else:
            a['eod_dates'].append(x['date']);a['daily_locked'][d]=a['daily'][d]
            if c['mode']=='eod':
                a['highwater']=max(a['highwater'],cash)
                a['next_floor']=max(a['floor'],min(a['highwater']-c['drawdown'],s['initial']+c['lock_profit']))
    profit=cash-s['initial'];values={**a['daily'],**a['daily_locked']}.values()
    biggest=max([0]+list(values));den=profit if c['denominator']=='net' else sum(max(0,v) for v in values)
    a['profit']=profit;a['consistency_pct']=100*biggest/den if den>0 else None
    # Compare currency products, not rounded percentages.
    consistent=not c['consistency'] or (den>0 and biggest*100<=den*c['consistency'])
    a['consistency_met']=consistent
    a['best_day_profit']=biggest;a['consistency_denominator']=den
    a['consistency_remaining']=max(0,biggest*100/c['consistency']-den) if c['consistency'] else 0
    required=max(c['target'],biggest*100/c['consistency'] if c['consistency'] else 0)
    a['effective_target']=required;a['remaining_target']=max(0,required-profit)
    a['trading_days']=len({day(t['entry_at']) for t in s['trades']}|({day(s['position']['entry_at'])} if s['position'] else set()))
    ready=c['phase']=='evaluation' and c['target']>0 and profit>=c['target'] and consistent and a['trading_days']>=c.get('min_days',0) and not s['position'] and not s['pending']
    if c.get('pass_at_eod'):ready=ready and x['date'] in a['eod_dates']
    a['modeled_criteria_met']=bool(ready)
    if a['status']=='failed':
        # Keep updating only until any required liquidation is resolved.
        if not s['position']:a['terminal_at']=s['clock']
    elif ready:
        a['status']='criteria_met_unverified' if a['uncertainties'] or a['limitations'] else 'passed';a['terminal_at']=s['clock']
    else:a['status']='unverified' if a['uncertainties'] else 'active'
