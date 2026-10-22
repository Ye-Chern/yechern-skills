"""Local research history, useful findings, and explicitly checked claims."""
import hashlib
import json
import math
import statistics
import sqlite3
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPLORATORY_KINDS = ('observation', 'obstruction', 'method', 'negative')
PROOF_REVIEW_LEVELS = ('self_check', 'peer_model', 'human', 'formal')


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def fingerprint(path):
    p = Path(path).resolve()
    if not p.is_file():
        raise ValueError(f"Proof/artifact file not found: {p}")
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()


class Ledger:
    def __init__(self, path, clock=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or (lambda: time.time_ns() / 1e9)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA busy_timeout=3000')
        self.db.execute('''CREATE TABLE IF NOT EXISTS events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          event_id TEXT NOT NULL UNIQUE,
          at_utc TEXT NOT NULL,
          at_epoch REAL NOT NULL,
          type TEXT NOT NULL,
          actor TEXT NOT NULL,
          payload TEXT NOT NULL,
          prev_hash TEXT NOT NULL,
          event_hash TEXT NOT NULL UNIQUE
        )''')
        self.db.commit()

    def close(self):
        self.db.close()

    def events(self):
        return [{**dict(r), 'payload': json.loads(r['payload'])} for r in
                self.db.execute('SELECT * FROM events ORDER BY seq ASC')]

    def append(self, typ, actor, payload):
        if not actor:
            raise ValueError('An actor identity is required')
        now = float(self._clock())  # host-supplied, never from agent's event payload
        dt = datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec='microseconds')
        eid = uuid.uuid4().hex
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        with self.db:
            prev = self.db.execute('SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            previous = prev[0] if prev else 'GENESIS'
            raw = json.dumps([eid, dt, now, typ, actor, body, previous], ensure_ascii=False)
            digest = hashlib.sha256(raw.encode()).hexdigest()
            self.db.execute('INSERT INTO events(event_id,at_utc,at_epoch,type,actor,payload,prev_hash,event_hash) VALUES (?,?,?,?,?,?,?,?)',
                            (eid, dt, now, typ, actor, body, previous, digest))
        return eid

    def verify_chain(self):
        prev = 'GENESIS'
        for e in self.events():
            if e['prev_hash'] != prev:
                return False
            raw = json.dumps([e['event_id'],e['at_utc'],e['at_epoch'],e['type'],e['actor'],
                              json.dumps(e['payload'],ensure_ascii=False,sort_keys=True,separators=(',',':')),prev], ensure_ascii=False)
            if hashlib.sha256(raw.encode()).hexdigest() != e['event_hash']:
                return False
            prev = e['event_hash']
        return True

    def _snapshot(self):
        dirs, episodes, works, claims, reviews, retractions, forecasts, resolutions = {}, {}, {}, {}, {}, {}, {}, {}
        conjectures, evidence = {}, {}
        config, finalized, scale_freezes = None, False, []
        transitions = []
        for e in self.events():
            p, t = e['payload'], e['type']
            if t == 'INIT':
                config = p
            elif t == 'DIRECTION':
                dirs[p['id']] = {**p, 'created_at':e['at_epoch']}
            elif t == 'EPISODE_START':
                episodes[p['id']] = {**p, 'at_start':e['at_epoch'], 'at_end':None, 'reason':None}
            elif t == 'EPISODE_END':
                episodes[p['id']]['at_end'] = e['at_epoch']
                episodes[p['id']]['reason'] = p['reason']
            elif t == 'ROLE_SHIFT':
                episodes[p['episode_id']]['role'] = p['role']
                transitions.append({'episode_id':p['episode_id'], 'role':p['role'], 'why':p['why'], 'at':e['at_epoch']})
            elif t == 'WORK_START':
                works[p['id']] = {**p, 'at_start':e['at_epoch'], 'at_end':None, 'outcome':None}
            elif t == 'WORK_END':
                works[p['id']]['at_end'] = e['at_epoch']
                works[p['id']]['outcome'] = p['outcome']
            elif t == 'CLAIM':
                claims[p['id']] = {**p, 'author':e['actor'], 'at':e['at_epoch']}
            elif t == 'REVIEW':
                reviews[p['claim_id']] = {'decision':p['decision'], 'level':p['level'], 'reviewer':e['actor'], 'at':e['at_epoch']}
            elif t == 'RETRACT':
                retractions[p['claim_id']] = {**p, 'at':e['at_epoch']}
            elif t == 'CONJECTURE':
                conjectures[p['id']] = {**p,'at':e['at_epoch'],'author':e['actor']}
            elif t == 'EVIDENCE':
                evidence[p['id']] = {**p,'at':e['at_epoch'],'author':e['actor']}
            elif t == 'FORECAST':
                forecasts[p['id']] = {**p, 'at':e['at_epoch']}
            elif t == 'FORECAST_RESOLUTION':
                resolutions[p['forecast_id']] = {**p, 'at':e['at_epoch'], 'reviewer':e['actor']}
            elif t == 'SCALE_FREEZE':
                scale_freezes.append({**p, 'at':e['at_epoch']})
            elif t == 'FINALIZE':
                finalized = True
        valid = {}
        for cid, c in claims.items():
            r = reviews.get(cid)
            valid[cid] = bool(r and r['decision']=='accept' and r['level'] in PROOF_REVIEW_LEVELS and cid not in retractions)
        # Dependencies are conjunctive. Invalidate descendants of invalid/retracted claims.
        for _ in range(len(claims)+1):
            changed = False
            for cid,c in claims.items():
                if valid[cid] and any(not valid.get(d,False) for d in c['depends']):
                    valid[cid] = False
                    changed = True
            if not changed: break
        # Useful exploration can guide planning before it becomes a checked claim.
        usable = {cid: (valid[cid] or c['kind'] in EXPLORATORY_KINDS
                       or (reviews.get(cid, {}).get('decision') == 'accept'
                           and reviews[cid]['level'] == 'reproducible_computation'))
                  and cid not in retractions
                  and reviews.get(cid, {}).get('decision') != 'reject'
                  for cid, c in claims.items()}
        for _ in range(len(claims)+1):
            changed = False
            for cid, c in claims.items():
                if usable[cid] and any(not usable.get(d, False) for d in c['depends']):
                    usable[cid] = False
                    changed = True
            if not changed: break
        return {'config':config,'directions':dirs,'episodes':episodes,'works':works,'claims':claims,
                'reviews':reviews,'retractions':retractions,'forecasts':forecasts,'resolutions':resolutions,
                'valid':valid,'usable':usable,'conjectures':conjectures,'evidence':evidence,
                'role_transitions':transitions,'scale_freezes':scale_freezes,'finalized':finalized}

    def state(self, now=None):
        s = self._snapshot()
        now = float(self._clock()) if now is None else now
        exposures = defaultdict(float)
        event_counts = defaultdict(int)
        bound_deltas = defaultdict(float)
        progress = []
        for wid,w in s['works'].items():
            end = min(now,w['at_end']) if w['at_end'] is not None else now
            exposures[w['episode_id']] += max(0,(end-w['at_start'])/60)
        # Replay current useful findings; checked numeric bounds remain separate.
        best_lower,best_upper = None,None
        for cid,c in sorted(s['claims'].items(), key=lambda x:x[1]['at']):
            if not s['usable'][cid]: continue
            kind, value, eid = c['kind'], c['value'], c['episode_id']
            novel = False
            delta = 0.0
            if not s['valid'][cid] and kind not in EXPLORATORY_KINDS:
                novel = True  # Computed evidence informs planning, not proof bounds.
            elif kind == 'lower' and (best_lower is None or value > best_lower):
                delta = value-best_lower if best_lower is not None else 0.0
                best_lower = value
                novel = True
            elif kind == 'upper' and (best_upper is None or value < best_upper):
                delta = best_upper-value if best_upper is not None else 0.0
                best_upper = value
                novel = True
            elif kind in ('lemma','counterexample','limiting','literature') + EXPLORATORY_KINDS:
                novel = True
            if novel:
                event_counts[eid] += 1
                bound_deltas[eid] += max(0.0,delta)
                progress.append({'claim_id':cid,'episode_id':eid,'kind':kind,'at':c['at'],
                                 'bound_delta':delta,
                                 'status':'checked' if s['valid'][cid] else
                                          'computed' if s['reviews'].get(cid,{}).get('level')=='reproducible_computation'
                                          else 'exploratory'})
        total = sum(exposures.values())
        scale={'value':None,'status':'UNKNOWN','basis':None}
        if s['config'] is not None and s['config'].get('target_scale') is not None:
            scale={'value':s['config']['target_scale'],'status':'USER_FIXED','basis':'user supplied natural scale'}
        elif s['scale_freezes']:
            last=s['scale_freezes'][-1]
            stale=any(not s['valid'].get(x,False) for x in last['claim_ids'])
            scale={'value':None if stale else last['value'],
                   'status':'STALE' if stale else 'FROZEN', 'basis':last['basis']}
        if scale['status']=='UNKNOWN':
            increments=[x['bound_delta'] for x in progress if x['bound_delta']>0]
            if len(increments)>=3:
                scale={'value':statistics.median(increments), 'status':'PILOT_ESTIMATE',
                       'basis':'median of checked positive bound improvements; not frozen'}
            elif best_lower is not None and best_upper is not None and best_upper>best_lower:
                scale={'value':best_upper-best_lower,'status':'RECORDED_GAP_PROPOSAL',
                       'basis':'recorded U-L; not frozen'}

        # Build active-time coordinates for each accepted novelty, not just total
        # counts. This makes an early discovery followed by a long dry spell
        # distinguishable from a recently discovered lemma.
        def exposed_until(epid, at):
            total_min=0.0
            for w in s['works'].values():
                if w['episode_id'] != epid:continue
                end=min(now,w['at_end']) if w['at_end'] is not None else now
                total_min += max(0.0, min(at,end)-w['at_start'])/60.0
            return total_min
        for q in progress:
            q['active_elapsed_at_submission']=round(exposed_until(q['episode_id'],q['at']),6)
        episode_metrics = {}
        direction_metrics = {d:{'minutes':0.,'events':0,'delta':0.,'episodes':0} for d in s['directions']}
        for eid,ep in s['episodes'].items():
            dr = direction_metrics[ep['direction_id']]
            dr['minutes'] += exposures[eid]
            dr['events'] += event_counts[eid]
            dr['delta'] += bound_deltas[eid]
            dr['episodes'] += 1
            recent_window=60.0
            recent_minutes=min(recent_window,exposures[eid])
            recent_start=max(0.,exposures[eid]-recent_minutes)
            marks=[q['active_elapsed_at_submission'] for q in progress if q['episode_id']==eid]
            recent_events=sum((mark>recent_start or mark==recent_start==0)
                              and mark<=exposures[eid] for mark in marks)
            ordered_marks=sorted(marks)
            completed_intervals=[round(v-(ordered_marks[k-1] if k else 0.),6)
                 for k,v in enumerate(ordered_marks)]
            last_age=round(exposures[eid]-max(marks),6) if marks else None
            episode_metrics[eid] = {'direction_id':ep['direction_id'], 'minutes':round(exposures[eid],6),
                                    'events':event_counts[eid], 'delta':round(bound_deltas[eid],9),
                                    'recent_window_minutes':round(recent_minutes,6),
                                    'recent_events':recent_events,'active_minutes_since_last_progress':last_age,
                                    'completed_discovery_intervals_active_minutes':completed_intervals,
                                    'active':ep['at_end'] is None, 'role':ep['role'], 'reason':ep['reason']}
        att_yes = [cid for cid,c in s['claims'].items() if c['kind']=='attained' and s['valid'][cid]]
        att_no = [cid for cid,c in s['claims'].items() if c['kind']=='nonattained' and s['valid'][cid]]
        attainment = ('CONFLICT' if att_yes and att_no else 'RECORDED_ATTAINED' if att_yes else
                      'RECORDED_NONATTAINED' if att_no else 'UNKNOWN')
        active = [eid for eid,ep in s['episodes'].items() if ep['at_end'] is None]
        open_works = [wid for wid,w in s['works'].items() if w['at_end'] is None]

        def claim_status(cid):
            review = s['reviews'].get(cid, {})
            if cid in s['retractions']: return 'retracted'
            if review.get('decision') == 'reject': return 'rejected'
            if s['valid'][cid]: return 'checked'
            if not s['usable'][cid] and (review.get('decision') == 'accept'
                                         or s['claims'][cid]['kind'] in EXPLORATORY_KINDS):
                return 'dependency_blocked'
            if review.get('level') == 'reproducible_computation': return 'computed'
            return 'exploratory' if s['claims'][cid]['kind'] in EXPLORATORY_KINDS else 'submitted'

        return {'config':s['config'], 'directions':s['directions'], 'episodes':episode_metrics,
                'direction_metrics':direction_metrics, 'active_episode':active[0] if active else None,
                'open_works':open_works, 'best_lower':best_lower, 'best_upper':best_upper,
                'gap':(best_upper-best_lower if best_upper is not None and best_lower is not None else None),
                'scale':scale,
                'progress':progress,'attainment':attainment,'total_work_minutes':round(total,6),
                'conjectures':s['conjectures'],'evidence':s['evidence'],
                'claims':{k:{**v,'review':s['reviews'].get(k), 'valid':s['valid'][k],
                               'usable':s['usable'][k],
                               'status':claim_status(k),
                               'retracted':k in s['retractions']} for k,v in s['claims'].items()},
                'forecasts':s['forecasts'],'resolutions':s['resolutions'],
                'role_transitions':s['role_transitions'], 'finalized':s['finalized']}

    def _need_initialized(self, allow_finalized=False):
        s = self._snapshot()
        if s['config'] is None: raise ValueError('Run init first')
        if s['finalized'] and not allow_finalized: raise ValueError('The task was finalized')
        return s

    def init(self, *, problem, model_index, model_id, model_version, inner_effort, outer_effort,
             max_work_minutes=None, target_scale=None):
        if self._snapshot()['config'] is not None: raise ValueError('Already initialized')
        if not (0 <= inner_effort <= 100 and 0 <= outer_effort <= 100):
            raise ValueError('Effort parameters must be in [0,100]')
        if max_work_minutes is not None and (not math.isfinite(max_work_minutes) or max_work_minutes <= 0):
            raise ValueError('Budget must be finite and positive')
        if target_scale is not None and (not math.isfinite(target_scale) or target_scale <= 0):
            raise ValueError('Scale must be finite and positive')
        return self.append('INIT','harness',{'problem':problem,'model_index':model_index,'model_id':model_id,
                             'model_version':model_version,'inner_effort':float(inner_effort),
                             'outer_effort':float(outer_effort),'max_work_minutes':max_work_minutes,
                             'target_scale':target_scale,'scope':'A=inf f(x); improve L<=A'})

    def add_direction(self, name, reason):
        self._need_initialized()
        if not reason.strip(): raise ValueError('Direction requires a rationale')
        uid = uuid.uuid4().hex[:12]
        self.append('DIRECTION','planner',{'id':uid,'name':name,'reason':reason})
        return uid

    def start_episode(self, direction_id, role, reason):
        s = self._need_initialized()
        if direction_id not in s['directions']: raise ValueError('Unknown direction')
        if any(x['at_end'] is None for x in s['episodes'].values()):
            raise ValueError('End active episode before starting another')
        uid = uuid.uuid4().hex[:12]
        self.append('EPISODE_START','planner',{'id':uid,'direction_id':direction_id,'role':role,'reason':reason})
        return uid

    def shift_role(self, episode_id, role, why):
        s = self._need_initialized()
        if episode_id not in s['episodes'] or s['episodes'][episode_id]['at_end'] is not None:
            raise ValueError('Role shift needs active episode')
        self.append('ROLE_SHIFT','planner',{'episode_id':episode_id,'role':role,'why':why})

    def start_work(self, episode_id, action, actor):
        s = self._need_initialized()
        if episode_id not in s['episodes'] or s['episodes'][episode_id]['at_end'] is not None:
            raise ValueError('Work needs active episode')
        if any(w['at_end'] is None for w in s['works'].values()):
            raise ValueError('A work slice is already open')
        uid = uuid.uuid4().hex[:12]
        self.append('WORK_START',actor,{'id':uid,'episode_id':episode_id,'action':action})
        return uid

    def end_work(self, work_id, outcome, actor):
        s = self._need_initialized()
        if work_id not in s['works'] or s['works'][work_id]['at_end'] is not None:
            raise ValueError('Unknown or already closed work slice')
        self.append('WORK_END',actor,{'id':work_id,'outcome':outcome})

    def end_episode(self, episode_id, reason):
        s = self._need_initialized()
        if episode_id not in s['episodes'] or s['episodes'][episode_id]['at_end'] is not None:
            raise ValueError('Unknown or closed episode')
        if any(w['episode_id']==episode_id and w['at_end'] is None for w in s['works'].values()):
            raise ValueError('Close its work slice before ending episode')
        self.append('EPISODE_END','planner',{'id':episode_id,'reason':reason})

    def submit(self, *, episode_id, kind, statement, actor, value=None, artifact=None, depends=()):
        s = self._need_initialized()
        if episode_id not in s['episodes']: raise ValueError('Unknown episode')
        if s['episodes'][episode_id]['at_end'] is not None: raise ValueError('Episode already closed')
        if kind not in ('lower','upper','lemma','counterexample','limiting','literature','attained','nonattained') + EXPLORATORY_KINDS:
            raise ValueError('Unsupported claim type')
        if not statement.strip(): raise ValueError('Finding requires a statement')
        if artifact is None and kind not in EXPLORATORY_KINDS:
            raise ValueError('This claim type requires an artifact')
        if kind in ('lower','upper') and (value is None or not isinstance(value,(int,float))):
            raise ValueError('Bound requires finite numeric value')
        if kind in ('lower','upper') and (value != value or abs(value) == float('inf')):
            raise ValueError('Bound must be finite')
        if any(d not in s['claims'] for d in depends): raise ValueError('Unknown dependency')
        content_hash = fingerprint(artifact) if artifact is not None else None
        if any(c['hash']==content_hash and c['statement']==statement
               and (content_hash is not None or (c['episode_id']==episode_id and c['kind']==kind))
               for c in s['claims'].values()):
            raise ValueError('Identical evidence already submitted')
        uid = uuid.uuid4().hex[:12]
        self.append('CLAIM',actor,{'id':uid,'episode_id':episode_id,'kind':kind,'value':value,
                    'statement':statement,'artifact_path':str(Path(artifact).resolve()) if artifact is not None else None,
                    'hash':content_hash,'depends':list(depends)})
        return uid

    def freeze_scale(self, basis):
        s=self._need_initialized()
        if s['config'].get('target_scale') is not None:
            raise ValueError('User supplied the fixed natural scale')
        if s['scale_freezes']:
            raise ValueError('Scale already frozen; declare a new task/config revision instead')
        st=self.state()
        if basis=='pilot':
            marks=[p for p in st['progress'] if p['bound_delta']>0]
            if len(marks)<3: raise ValueError('Need at least 3 positive checked bound improvements')
            value=statistics.median(p['bound_delta'] for p in marks)
            claim_ids=[p['claim_id'] for p in marks]
        elif basis=='gap':
            if st['gap'] is None or st['gap']<=0:
                raise ValueError('Need a nonzero checked interval')
            value=st['gap']
            claim_ids=[cid for cid,c in st['claims'].items() if c['valid'] and c['kind'] in ('upper','lower')]
        else:
            raise ValueError('Basis must be pilot or gap')
        return self.append('SCALE_FREEZE','harness',{'value':value,'basis':basis,
                                       'claim_ids':claim_ids})

    def conjecture(self, *, episode_id, value, statement, self_confidence, actor):
        s = self._need_initialized()
        if episode_id not in s['episodes'] or s['episodes'][episode_id]['at_end'] is not None:
            raise ValueError('Conjecture requires active episode')
        if not 0 <= self_confidence <= 1 or not math.isfinite(self_confidence): raise ValueError('Confidence must lie in [0,1]')
        if not math.isfinite(float(value)): raise ValueError('Numeric candidate must be finite')
        if not statement.strip(): raise ValueError('Conjecture requires a statement')
        uid=uuid.uuid4().hex[:12]
        self.append('CONJECTURE',actor,{'id':uid,'episode_id':episode_id,'value':float(value),
            'statement':statement,'self_confidence':float(self_confidence)})
        return uid

    def add_evidence(self, *, conjecture_id, family, kind, support, note, actor, claim_id=None):
        s=self._need_initialized()
        if not isinstance(support, bool): raise ValueError('Support must be a boolean')
        if conjecture_id not in s['conjectures']: raise ValueError('Unknown conjecture')
        if kind not in ('witness','limiting','structure','literature','numerical','critique'):
            raise ValueError('Unknown evidence kind')
        if not family.strip(): raise ValueError('Evidence must identify its origin family')
        if claim_id is not None and claim_id not in s['claims']: raise ValueError('Unknown linked claim')
        uid=uuid.uuid4().hex[:12]
        self.append('EVIDENCE',actor,{'id':uid,'conjecture_id':conjecture_id,'family':family,
                'kind':kind,'support':bool(support),'note':note,'claim_id':claim_id})
        return uid

    def review(self, claim_id, verifier, decision, level):
        s = self._need_initialized(allow_finalized=True)
        if claim_id not in s['claims']: raise ValueError('Unknown claim')
        if decision not in ('accept','reject'): raise ValueError('Choose accept/reject')
        if level not in PROOF_REVIEW_LEVELS + ('reproducible_computation',):
            raise ValueError('Unknown review level')
        if verifier == s['claims'][claim_id]['author'] and level != 'self_check':
            raise ValueError('Use self_check when checking your own work')
        # Validate artifact still exists and matches the originally registered bytes.
        c = s['claims'][claim_id]
        if c['artifact_path'] is not None and fingerprint(c['artifact_path']) != c['hash']:
            raise ValueError('Artifact changed since submission')
        self.append('REVIEW',verifier,{'claim_id':claim_id,'decision':decision,'level':level})

    def retract(self, claim_id, actor, reason):
        s = self._need_initialized(allow_finalized=True)
        if claim_id not in s['claims']: raise ValueError('Unknown claim')
        if claim_id in s['retractions']: raise ValueError('Already retracted')
        self.append('RETRACT',actor,{'claim_id':claim_id,'reason':reason})

    def forecast(self, *, claim_id, model_id, role, probability, evidence_group):
        s = self._need_initialized()
        if claim_id not in s['claims']: raise ValueError('Unknown claim')
        if not 0 < probability < 1: raise ValueError('Probability strictly between 0 and 1')
        if model_id != s['config']['model_id']: raise ValueError('Model identity not bound to task')
        if any(f['claim_id']==claim_id and f['model_id']==model_id and f['evidence_group']==evidence_group
               for f in s['forecasts'].values()):
            raise ValueError('Duplicate correlated forecast')
        uid = uuid.uuid4().hex[:12]
        self.append('FORECAST',model_id,{'id':uid,'claim_id':claim_id,'model_id':model_id,
                    'role':role,'probability':probability,'evidence_group':evidence_group})
        return uid

    def resolve_forecast(self, forecast_id, truth, verifier, level, reason):
        s = self._need_initialized(allow_finalized=True)
        if not isinstance(truth, bool): raise ValueError('Truth must be a boolean')
        if forecast_id not in s['forecasts']: raise ValueError('Unknown forecast')
        if level not in PROOF_REVIEW_LEVELS:
            raise ValueError('Unknown resolution level')
        if verifier == s['forecasts'][forecast_id]['model_id'] and level != 'self_check':
            raise ValueError('Use self_check for your own assessment')
        self.append('FORECAST_RESOLUTION',verifier,{'forecast_id':forecast_id,'truth':bool(truth),
                    'level':level,'reason':reason})

    def finalize(self):
        s = self._need_initialized()
        if any(w['at_end'] is None for w in s['works'].values()):
            raise ValueError('Cannot finalize with work still running')
        self.append('FINALIZE','harness',{'reason':'task completed or suspended; update registry separately'})
