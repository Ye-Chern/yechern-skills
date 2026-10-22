"""BoundForge v2 local demonstration CLI. Run python -m boundforge.cli --help."""
import argparse
import json
from pathlib import Path
from .ledger import Ledger
from .controller import assess
from .registry import load, row, calibrate, sync
from .candidates import assess_candidates


def main(argv=None):
    p=argparse.ArgumentParser(description='BoundForge v2.1: local research history and dual-loop planning')
    p.add_argument('--db',default='research.db',help='SQLite ledger path')
    s=p.add_subparsers(dest='cmd',required=True)
    x=s.add_parser('init')
    x.add_argument('--registry')
    x.add_argument('--model-index',type=int,default=1)
    x.add_argument('--model-id',default='unspecified')
    x.add_argument('--model-version',default='unspecified')
    x.add_argument('--problem',required=True)
    x.add_argument('--inner',type=float,required=True)
    x.add_argument('--outer',type=float,required=True)
    x.add_argument('--max-work-minutes',type=float)
    x.add_argument('--scale',type=float)
    x=s.add_parser('direction'); x.add_argument('--name',required=True); x.add_argument('--why',required=True)
    x=s.add_parser('episode-start'); x.add_argument('--direction',required=True); x.add_argument('--role',default='researcher'); x.add_argument('--why',required=True)
    x=s.add_parser('episode-end'); x.add_argument('--episode',required=True); x.add_argument('--why',required=True)
    x=s.add_parser('role'); x.add_argument('--episode',required=True); x.add_argument('--new-role',required=True); x.add_argument('--why',required=True)
    x=s.add_parser('work-start'); x.add_argument('--episode',required=True); x.add_argument('--action',required=True); x.add_argument('--actor',required=True)
    x=s.add_parser('work-end'); x.add_argument('--work',required=True); x.add_argument('--outcome',required=True); x.add_argument('--actor',required=True)
    x=s.add_parser('submit'); x.add_argument('--episode',required=True); x.add_argument('--kind',required=True,
                              choices=['lower','upper','lemma','counterexample','limiting','literature','attained','nonattained',
                                       'observation','obstruction','method','negative'])
    x.add_argument('--value',type=float); x.add_argument('--statement',required=True); x.add_argument('--artifact')
    x.add_argument('--depends',nargs='*',default=[]); x.add_argument('--actor',required=True)
    x=s.add_parser('conjecture'); x.add_argument('--episode',required=True); x.add_argument('--value',type=float,required=True)
    x.add_argument('--statement',required=True); x.add_argument('--confidence',type=float,required=True); x.add_argument('--actor',required=True)
    x=s.add_parser('evidence'); x.add_argument('--conjecture',required=True); x.add_argument('--family',required=True)
    x.add_argument('--kind',required=True,choices=['witness','limiting','structure','literature','numerical','critique'])
    x.add_argument('--support',required=True,choices=['yes','no']); x.add_argument('--note',required=True)
    x.add_argument('--claim'); x.add_argument('--actor',required=True)
    x=s.add_parser('candidates'); x.add_argument('--registry')
    x=s.add_parser('review'); x.add_argument('--claim',required=True); x.add_argument('--verifier',required=True)
    x.add_argument('--decision',choices=['accept','reject'],required=True)
    x.add_argument('--level',choices=['self_check','peer_model','human','formal','reproducible_computation'],required=True)
    x=s.add_parser('retract'); x.add_argument('--claim',required=True); x.add_argument('--actor',required=True); x.add_argument('--why',required=True)
    x=s.add_parser('forecast'); x.add_argument('--claim',required=True); x.add_argument('--role',required=True)
    x.add_argument('--p',type=float,required=True); x.add_argument('--evidence-group',required=True)
    x=s.add_parser('resolve'); x.add_argument('--forecast',required=True); x.add_argument('--truth',required=True,choices=['true','false'])
    x.add_argument('--verifier',required=True); x.add_argument('--level',required=True,choices=['self_check','peer_model','human','formal']); x.add_argument('--why',required=True)
    x=s.add_parser('freeze-scale'); x.add_argument('--basis',choices=['pilot','gap'],required=True)
    s.add_parser('state'); s.add_parser('decide'); s.add_parser('verify-ledger');s.add_parser('finalize')
    x=s.add_parser('sync');x.add_argument('--registry',required=True)
    x=s.add_parser('omega');x.add_argument('--registry',required=True);x.add_argument('--role')
    a=p.parse_args(argv)
    db=Ledger(a.db)
    try:
        if a.cmd=='init':
            r=row(load(a.registry),a.model_index) if a.registry else {'model_id':a.model_id,'version':a.model_version}
            result=db.init(problem=a.problem,model_index=a.model_index,model_id=r['model_id'],
                  model_version=r['version'],inner_effort=a.inner,outer_effort=a.outer,
                  max_work_minutes=a.max_work_minutes,target_scale=a.scale)
        elif a.cmd=='direction':result=db.add_direction(a.name,a.why)
        elif a.cmd=='episode-start':result=db.start_episode(a.direction,a.role,a.why)
        elif a.cmd=='episode-end':result=db.end_episode(a.episode,a.why)
        elif a.cmd=='role':result=db.shift_role(a.episode,a.new_role,a.why)
        elif a.cmd=='work-start':result=db.start_work(a.episode,a.action,a.actor)
        elif a.cmd=='work-end':result=db.end_work(a.work,a.outcome,a.actor)
        elif a.cmd=='submit':result=db.submit(episode_id=a.episode,kind=a.kind,value=a.value,
             statement=a.statement,artifact=a.artifact,depends=a.depends,actor=a.actor)
        elif a.cmd=='conjecture':result=db.conjecture(episode_id=a.episode,value=a.value,
                statement=a.statement,self_confidence=a.confidence,actor=a.actor)
        elif a.cmd=='evidence':result=db.add_evidence(conjecture_id=a.conjecture,
                family=a.family,kind=a.kind,support=a.support=='yes',note=a.note,actor=a.actor,claim_id=a.claim)
        elif a.cmd=='candidates':
            cfg=db.state()['config']
            omega=calibrate(row(load(a.registry),cfg['model_index']))['omega'] if a.registry else .2
            result=assess_candidates(db.state(),omega)
        elif a.cmd=='review':result=db.review(a.claim,a.verifier,a.decision,a.level)
        elif a.cmd=='retract':result=db.retract(a.claim,a.actor,a.why)
        elif a.cmd=='forecast':
            cfg=db.state()['config'];result=db.forecast(claim_id=a.claim,model_id=cfg['model_id'],role=a.role,
                      probability=a.p,evidence_group=a.evidence_group)
        elif a.cmd=='resolve':result=db.resolve_forecast(a.forecast,a.truth=='true',a.verifier,a.level,a.why)
        elif a.cmd=='freeze-scale':result=db.freeze_scale(a.basis)
        elif a.cmd=='state':result=db.state()
        elif a.cmd=='decide':result=assess(db.state())
        elif a.cmd=='verify-ledger':result={'hash_chain_ok':db.verify_chain()}
        elif a.cmd=='finalize':result=db.finalize()
        elif a.cmd=='sync':result=sync(a.registry,db)
        elif a.cmd=='omega':
            cfg=db.state()['config']
            if cfg is None:raise ValueError('Run init first')
            reg=load(a.registry);r=row(reg,cfg['model_index']);result=calibrate(r,a.role)
        else:raise RuntimeError('unreachable')
        print(json.dumps({'result':result},ensure_ascii=False,indent=2))
    except Exception as exc:
        p.exit(2,f'Error: {exc}\n')
    finally:
        db.close()

if __name__=='__main__': main()
