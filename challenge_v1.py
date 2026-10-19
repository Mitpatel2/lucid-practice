"""Custom training rules v1. Never a certification of real firm compliance."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import math

def day(t):
    # Futures trading day rolls at 17:00 Chicago, DST-aware.
    return (datetime.fromtimestamp(t,ZoneInfo('America/Chicago'))-timedelta(hours=17)).date().isoformat()

def configure(s,c):
    if not c:return
    if s['trades'] or s['position'] or s['pending']:raise ValueError('Configure a challenge only on a fresh attempt')
    c=dict(c)
    for k in ('target','drawdown','daily_loss','consistency','lock_profit'):
        c[k]=float(c.get(k,0))
        if not math.isfinite(c[k]) or c[k]<0:raise ValueError('Challenge values must be finite and nonnegative')
    if c['drawdown']<=0 or c['consistency']>100:raise ValueError('Invalid drawdown or consistency')
    if c.get('mode') not in ('static','eod','intraday'):raise ValueError('Invalid drawdown mode')
    if c.get('daily_basis') not in ('realized','equity'):raise ValueError('Invalid daily loss basis')
    if c.get('denominator') not in ('net','winning_days'):raise ValueError('Invalid consistency denominator')
    if c.get('phase') not in ('evaluation','funded'):raise ValueError('Invalid challenge phase')
    for k,default in [('max_micro',10),('micro_per_mini',10)]:
        c[k]=c.get(k,default)
        if isinstance(c[k],bool) or not isinstance(c[k],int) or not 1<=c[k]<=1000:raise ValueError('Contract limits must be whole numbers from 1 to 1000')
    c.setdefault('daily_action','fail');c.setdefault('min_days',0)
    if c['daily_action'] not in ('fail','pause') or not isinstance(c['min_days'],int) or not 0<=c['min_days']<=365:raise ValueError('Invalid daily action or minimum days')
    s['challenge']={'version':'custom-v1','config':c,'status':'active','reasons':[], 'uncertainties':(['Official reference has unmodeled rules; no firm pass certification'] if c.get('reference') else []), 'day':day(s['clock']), 'day_start':s['balance'],'last_cash':s['balance'],'highwater':s['balance'],'floor':s['balance']-c['drawdown'],'daily':{},'checked_at':s['clock']}
    update(s,s['balance'])

def update(s,equity,uncertain=False):
    a=s.get('challenge')
    if not a:return
    c=a['config'];d=day(s['clock']);cash=s['balance']
    if d!=a['day']:
        a.pop('paused_day',None)
        if c['mode']=='eod':a['highwater']=max(a['highwater'],a['last_cash'])
        a['day_start']=a['last_cash'];a['day']=d
    if c['mode']=='intraday' and equity is not None:a['highwater']=max(a['highwater'],equity)
    if c['mode']!='static':a['floor']=max(a['floor'],min(a['highwater']-c['drawdown'],s['initial']+c['lock_profit']))
    a['daily'][d]=cash-a['day_start'];a['last_cash']=cash;a['checked_at']=s['clock']
    # Cash includes entry commission; equity includes remaining exit commission.
    if equity is None:uncertain=True
    if uncertain and 'Intrabar path or missing mark cannot verify all rule touches' not in a['uncertainties']:a['uncertainties'].append('Intrabar path or missing mark cannot verify all rule touches')
    reasons=[]
    if equity is not None and equity<=a['floor']:reasons.append('Maximum loss floor touched')
    daily_value=cash if c['daily_basis']=='realized' else equity
    if c['daily_loss'] and daily_value is not None and a['day_start']-daily_value>=c['daily_loss']:
        if c.get('daily_action','fail')=='fail':reasons.append('Daily loss limit touched')
        else:a['paused_day']=d
    if reasons:a['status']='failed';a['reasons']=list(dict.fromkeys(a['reasons']+reasons))
    profit=cash-s['initial'];den=profit if c['denominator']=='net' else sum(max(0,v) for v in a['daily'].values());biggest=max([0]+list(a['daily'].values()))
    a['profit']=profit;a['consistency_pct']=100*biggest/den if den>0 else None
    a['remaining_target']=max(0,c['target']-profit)
    consistent=not c['consistency'] or (a['consistency_pct'] is not None and a['consistency_pct']<=c['consistency'])
    a['consistency_met']=consistent
    a['trading_days']=len({day(t['entry_at']) for t in s['trades']}|({day(s['position']['entry_at'])} if s['position'] else set()))
    if a['status']!='failed':
        a['status']='unverified' if a['uncertainties'] else 'passed' if c['phase']=='evaluation' and c['target']>0 and profit>=c['target'] and consistent and a['trading_days']>=c.get('min_days',0) and not s['position'] and not s['pending'] else 'active'
