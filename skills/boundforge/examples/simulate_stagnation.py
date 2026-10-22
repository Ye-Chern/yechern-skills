"""Synthetic host-clock study: equal message count not assumed; no real model ran."""
import json
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from boundforge.ledger import Ledger
from boundforge.controller import assess

class Clock:
    def __init__(self):self.t=1_800_000_000.0
    def __call__(self):return self.t
    def advance(self,minutes):self.t+=60*minutes

clock=Clock()
with tempfile.TemporaryDirectory() as d:
    db=Ledger(Path(d)/'research.db',clock=clock)
    db.init(problem='synthetic unknown-bound research',model_index=1,
            model_id='synthetic-model',model_version='demo-1',
            inner_effort=15,outer_effort=95,max_work_minutes=200)
    d1=db.add_direction('Restricted trial family','search lower bound in simple functions')
    d2=db.add_direction('Dual certificate','different algebraic family')
    e1=db.start_episode(d1,'researcher','initial approach')
    w1=db.start_work(e1,'search and optimize','synthetic-model')
    clock.advance(90)
    db.end_work(w1,'90 min of failed search','synthetic-model')
    result1=assess(db.state())
    print(json.dumps({'phase':'after 90 unsuccessful active minutes','decision':result1['decision'],
                     'switch_probability_heuristic':result1.get('p_better_direction'),
                     'total_active_minutes':result1['total_active_work_minutes'],
                     'inner_effort':result1['inner_effort'],'outer_effort':result1['outer_effort']},ensure_ascii=False))
    db.end_episode(e1,'stagnation: restricted ansatz')
    e2=db.start_episode(d2,'literature_analyst','new structural direction')
    w2=db.start_work(e2,'analyze dual formulation','synthetic-model')
    clock.advance(18)
    cid=db.submit(episode_id=e2,kind='method',
                  statement='A dual reformulation exposes a useful constraint',actor='synthetic-model')
    db.end_work(w2,'one useful exploratory finding in this synthetic scenario','synthetic-model')
    result2=assess(db.state())
    print(json.dumps({'phase':'after switching to alternate direction','decision':result2['decision'],
           'event_counts':{k:v['events'] for k,v in db.state()['episodes'].items()},
           'total_active_minutes':result2['total_active_work_minutes']},ensure_ascii=False))
    print(json.dumps({'hash_chain_ok':db.verify_chain()},ensure_ascii=False))
    db.close()
