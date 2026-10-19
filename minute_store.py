"""Read-only disk-backed minute bars; bounded candle windows, compact time indexes."""
import sqlite3, json, bisect, heapq
from array import array
from pathlib import Path
from engine import Replay

class Bars:
    def __init__(self,db,symbol):
        self.db=db;self.symbol=symbol
        self.times=array('q',(r[0] for r in db.execute('SELECT t FROM bars WHERE symbol=? ORDER BY t',(symbol,))))
    def __len__(self): return len(self.times)
    def __getitem__(self,index):
        if isinstance(index,slice):
            start,end,step=index.indices(len(self))
            if step!=1:raise ValueError('Only contiguous windows supported')
            if end<=start:return []
            return [dict(zip(('t','o','h','l','c','v','contract'),r)) for r in self.db.execute('SELECT t,o,h,l,c,v,contract FROM bars WHERE symbol=? AND t>=? AND t<=? ORDER BY t',(self.symbol,self.times[start],self.times[end-1]))]
        return self.get(self.times[index])
    def get(self,t):
        row=self.db.execute('SELECT t,o,h,l,c,v,contract FROM bars WHERE symbol=? AND t=?',(self.symbol,t)).fetchone()
        return dict(zip(('t','o','h','l','c','v','contract'),row)) if row else None

class MinuteReplay(Replay):
    def __init__(self,path,store):
        self.base=60;self.dataset=Path(path).parent.name
        self.db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True,check_same_thread=False)
        self.data={s:Bars(self.db,s) for s in ('NQ','ES')};self.maps=self.data
        self.times={s:b.times for s,b in self.data.items()}
        self.timeline=array('q');previous=None
        for t in heapq.merge(*self.times.values()):
            if t!=previous:self.timeline.append(t);previous=t
        self.store=Path(store);self.store.mkdir(parents=True,exist_ok=True)

    def predict(self,s,order):return super().predict(s,order)

    def flow_review(self,s,symbol):
        flow=getattr(self,'flow',None)
        if flow is None:return {'available':False,'reason':'No validated TBBO matched to this dataset','ml_available':False}
        key=(s['clock'],symbol)
        if not hasattr(self,'flow_cache'):self.flow_cache={}
        if key not in self.flow_cache:
            end=bisect.bisect_right(self.times[symbol],s['clock']-60)
            self.flow_cache[key]=flow.review(symbol,self.data[symbol][max(0,end-5):end],s['clock'])
            if len(self.flow_cache)>32:self.flow_cache.pop(next(iter(self.flow_cache)))
        return self.flow_cache[key]
    def visible(self,s,tf=5):
        result=super().visible(s,tf)
        result['order_flow']={k:self.flow_review(s,k) for k in ('NQ','ES')}
        return result
    def review(self,s,symbol):
        result=super().review(s,symbol);flow=self.flow_review(s,symbol)
        result['flow_evidence']=flow
        result['order_flow']=('Received TBBO trades and pre-trade BBO, descriptive only' if flow['available'] else 'Unavailable — '+flow['reason'])
        return result
