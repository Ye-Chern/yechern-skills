"""Run a small real research record with Python's standard library."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from boundforge.ledger import Ledger
from boundforge.controller import assess


def run(folder):
    folder.mkdir(parents=True, exist_ok=True)
    db = Ledger(folder / 'research.db')
    try:
        db.init(problem='A=inf_{x>0}(2+1/x)', model_index=1,
                model_id='example-researcher', model_version='example',
                inner_effort=75, outer_effort=85)
        direction = db.add_direction('Direct argument', 'Positivity and a limiting sequence')
        episode = db.start_episode(direction, 'researcher', 'Check the elementary case')
        work = db.start_work(episode, 'Investigate the endpoint and attainment', 'example-researcher')
        db.submit(episode_id=episode, kind='observation', actor='example-researcher',
                  statement='For x=1,10,100 the values are 3,2.1,2.01, suggesting the endpoint 2.')
        proofs = {
            'lower': 'For x>0, 1/x>0, hence 2+1/x>2. Thus A>=2.',
            'upper': 'For x_n=n>0, f(x_n)=2+1/n tends to 2. Hence A<=2.',
            'nonattained': 'Every finite x>0 has f(x)>2, so the infimum 2 is not attained.'
        }
        for kind, proof in proofs.items():
            artifact = folder / f'{kind}.txt'
            artifact.write_text(proof + '\n', encoding='utf-8')
            claim = db.submit(episode_id=episode, kind=kind, statement=proof,
                              value=2 if kind in ('lower', 'upper') else None,
                              artifact=artifact, actor='example-researcher')
            db.review(claim, 'example-researcher', 'accept', 'self_check')
        db.end_work(work, 'Direct proof gives infimum 2, not attained', 'example-researcher')
        db.end_episode(episode, 'Elementary argument complete')
        db.finalize()
        state = db.state()
        result = {'problem': state['config']['problem'], 'best_lower': state['best_lower'],
                  'best_upper': state['best_upper'], 'attainment': state['attainment'],
                  'decision': assess(state)['decision'],
                  'progress_events': state['episodes'][episode]['events'],
                  'hash_chain_ok': db.verify_chain()}
        assert result['best_lower'] == result['best_upper'] == 2
        assert result['attainment'] == 'RECORDED_NONATTAINED'
        assert result['progress_events'] == 3
        assert result['hash_chain_ok']
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='A new folder to keep the example record')
    args = parser.parse_args()
    if args.output is not None:
        run(args.output)
        print(f'Record saved in {args.output.resolve()}')
    else:
        with tempfile.TemporaryDirectory(prefix='boundforge-example-') as temporary:
            run(Path(temporary))
