"""Optional model evidence table updated from explicitly resolved forecasts."""
import json
import os
import tempfile
from pathlib import Path


def load(path):
    with open(path,encoding='utf-8') as f: return json.load(f)


def put_atomic(path, data):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.registry-',suffix='.tmp',dir=p.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2,sort_keys=True)
            f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def row(registry,index):
    rows=[r for r in registry['models'] if r['index']==index]
    if len(rows)!=1: raise ValueError(f'Model row {index} missing or ambiguous')
    return rows[0]


def calibrate(modelrow,role=None):
    prior=modelrow.get('prior',{'alpha':3,'beta':1})
    labels=list(modelrow.get('evidence',{}).values())
    all_hits=sum(int((v['probability']>=0.5)==v['truth']) for v in labels)
    all_n=len(labels)
    global_mean=(prior['alpha']+all_hits)/(prior['alpha']+prior['beta']+all_n)
    if role is None:
        avg=global_mean
        total=all_n
    else:
        relevant=[v for v in labels if v['role']==role]
        n=len(relevant)
        hits=sum(int((v['probability']>=.5)==v['truth']) for v in relevant)
        # Empirical-Bayes partial pooling (heuristic, not full hierarchical posterior).
        shrink=6.0
        avg=(shrink*global_mean + hits)/(shrink+n)
        total=n
    # 0.40 cap, default 0.20 under Beta(3,1) prior and zero evidence.
    omega=0.4*max(0.,min(1.,2*avg-1))
    brier=sum((v['probability']-int(v['truth']))**2 for v in labels)/all_n if all_n else None
    return {'omega':round(omega,4),'directional_accuracy_posterior_mean':round(avg,4),
            'effective_sample_size':total,'global_labels':all_n,
            'global_brier':round(brier,4) if brier is not None else None}


def sync(registry_path, ledger, *, allow_before_finalize=False):
    snap=ledger._snapshot()
    if not snap['finalized'] and not allow_before_finalize:
        raise ValueError('Task must be finalized before shared registry sync')
    reg=load(registry_path)
    config=snap['config']
    r=row(reg,config['model_index'])
    if r['model_id']!=config['model_id'] or r['version']!=config['model_version']:
        raise ValueError('Model row/version changed since task started')
    evidence=r.setdefault('evidence',{})
    task_id=str(ledger.path.resolve())
    for fid,f in snap['forecasts'].items():
        resolve=snap['resolutions'].get(fid)
        if resolve is None: continue
        evidence[task_id+':'+fid]={'probability':f['probability'],'truth':resolve['truth'],
               'role':f['role'],'claim_id':f['claim_id'], 'evidence_group':f['evidence_group'],
               'adjudication':resolve['level']}
    put_atomic(registry_path,reg)
    return calibrate(r)
