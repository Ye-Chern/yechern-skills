"""Candidate relations to recorded bounds, plus heuristic research priorities."""

# Numbers are illustrative priority signals, NOT likelihood ratios or probabilities.
EVIDENCE_STRENGTH={'witness':.8,'limiting':.8,'structure':.55,
                   'literature':.5,'numerical':.2,'critique':.35}


def assess_candidates(state, omega=.2):
    if not 0<=omega<=.4:raise ValueError('Only 0<=omega<=0.4 is supported')
    L,U=state['best_lower'],state['best_upper']
    result=[]
    for cid,c in state['conjectures'].items():
        C=c['value']
        if L is not None and U is not None and L>U:
            status='INCONSISTENT_BOUNDS'
        elif L is not None and L>C:
            status='EXCLUDED_BY_RECORDED_LOWER'
        elif U is not None and U<C:
            status='EXCLUDED_BY_RECORDED_UPPER'
        elif L is not None and U is not None and L==U==C:
            status='MATCHES_RECORDED_BOUNDS'
        else:
            status='OPEN'
        # One source/family contributes at most once; independent linked artifacts
        # contribute only while currently valid. Unreviewed text can provide a weak
        # heuristic hint, never a mathematical certificate.
        fam={}
        for ev in state['evidence'].values():
            if ev['conjecture_id']!=cid:continue
            link=ev['claim_id']
            if link is not None and state['claims'][link].get('status') in ('retracted','rejected','dependency_blocked'):
                continue
            reviewed=link is not None and state['claims'][link]['valid']
            strength=EVIDENCE_STRENGTH[ev['kind']]
            if not reviewed:strength=min(strength,.18)
            sign=1 if ev['support'] else -1
            v=sign*strength
            # Preserve the strongest absolute signal in a correlated evidence family.
            if ev['family'] not in fam or abs(v)>abs(fam[ev['family']]):
                fam[ev['family']]=v
        # Convert signed evidence to a bounded 0-1 *priority* signal (not posterior!).
        from math import tanh
        external=.5+.5*tanh(sum(fam.values()))
        score=omega*c['self_confidence']+(1-omega)*external
        result.append({'id':cid,'candidate':C,'status':status,
              'self_confidence':c['self_confidence'],'omega':omega,
              'external_evidence_groups':fam,'heuristic_priority':round(score,4),
              'attainment':state['attainment']})
    return result
