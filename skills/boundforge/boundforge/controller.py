"""Dual-loop planning suggestions from useful findings per active work minute."""
import math
import random

PRIOR_SHAPE = 1.2
PRIOR_EXPOSURE_MIN = 30.0


def posterior(events, minutes):
    return PRIOR_SHAPE + int(events), PRIOR_EXPOSURE_MIN + max(0.0,float(minutes))


def sample_rates(stats, rng, n=1600):
    a,b=posterior(stats['events'],stats['minutes'])
    return [rng.gammavariate(a,1/b) for _ in range(n)]


def summary(samples):
    v=sorted(samples)
    def q(p): return round(v[int((len(v)-1)*p)],6)
    return {'events_per_work_minute':{'p10':q(.1),'median':q(.5),'p90':q(.9)},
            'samples':len(samples)}


def assess(state, *, seed=11, planning_horizon_min=60.0, switch_cost_min=5.0):
    """Return advisor verdict; never autonomously changes research state.

    e_in affects confidence needed to abandon a *current episode*.
    e_out affects tolerance for expected low global discovery yield.
    Neither parameter is a count of calls, steps or episodes.
    """
    cfg=state['config']
    if cfg is None: return {'decision':'NOT_INITIALIZED'}
    rng=random.Random(seed)
    ei,eo = cfg['inner_effort']/100, cfg['outer_effort']/100
    L,U=state['best_lower'],state['best_upper']
    if L is not None and U is not None:
        if L>U:
            return {'decision':'INCONSISTENT_BOUNDS','reason':'Recorded bounds L>U; revisit the underlying arguments and assumptions.'}
        if L==U:
            return {'decision':'MATCHING_RECORDED_BOUNDS','reason':'Recorded numeric bounds match. Determine the mathematical conclusion from the arguments and exact endpoints.'}
    if cfg['max_work_minutes'] is not None and state['total_work_minutes']>=cfg['max_work_minutes']:
            return {'decision':'SUSPEND_BUDGET','reason':'Configured maximum recorded work time reached.'}
    dirs = state['direction_metrics']
    if not dirs:
        return {'decision':'PROPOSE_DIRECTIONS','reason':'No research directions registered.'}
    est={}
    draws={}
    for did,stats in dirs.items():
        vals=sample_rates(stats,rng)
        draws[did]=vals
        est[did]={**summary(vals),'minutes':round(stats['minutes'],3),'progress_events':stats['events'],
                  'episodes':stats['episodes']}
    active=state['active_episode']
    # Global value threshold, measured as events per *active* research minute,
    # not wall-clock minutes and not number of messages.
    min_rate=0.045 - 0.035*eo
    p_global=sum(max(vals[k] for vals in draws.values()) > min_rate for k in range(len(next(iter(draws.values()))))) / len(next(iter(draws.values())))
    global_threshold=0.91 - 0.38*eo
    result={'inner_effort':cfg['inner_effort'],'outer_effort':cfg['outer_effort'],
            'interpretation':'Bayesian-heuristic forecasts, not calibrated probabilities or proof',
            'min_viable_event_rate':round(min_rate,5), 'p_global_viable':round(p_global,3),
            'global_viability_threshold':round(global_threshold,3), 'directions':est,
            'total_active_work_minutes':state['total_work_minutes']}
    if active is None:
        if state['total_work_minutes']>=5 and p_global<global_threshold:
            result.update(decision='SUSPEND_LOW_VALUE',reason='Recorded progress suggests a pause; weigh any concrete new research opportunity.')
        else:
            result.update(decision='START_EPISODE',reason='Select a new direction; effort parameters do not specify an episode count.')
        return result
    episode=state['episodes'][active]
    did=episode['direction_id']
    # Current episode may differ materially from same direction's historic yield.
    recent_obs={'events':episode['recent_events'], 'minutes':episode['recent_window_minutes']}
    current_draws=sample_rates(recent_obs,rng)
    alt=[d for d in dirs if d!=did]
    p_switch=0
    if alt:
        # Discount switching by expected time needed to regain context.
        discount=planning_horizon_min/(planning_horizon_min+switch_cost_min)
        p_switch=sum(max(draws[x][k] * discount for x in alt) > current_draws[k]*1.08
                       for k in range(len(current_draws)))/len(current_draws)
    # P(live direction is below the user-dependent viability hurdle)
    p_stalled=sum(v < min_rate for v in current_draws)/len(current_draws)
    switch_threshold=0.58+0.36*ei
    result.update(active_episode=active,current_direction=did,
                  recent_episode_observation=recent_obs,
                  active_minutes_since_last_progress=episode['active_minutes_since_last_progress'],
                  current_episode=summary(current_draws), p_better_direction=round(p_switch,3),
                  p_current_below_viability_rate=round(p_stalled,3),
                  inner_switch_threshold=round(switch_threshold,3))
    if state['total_work_minutes']>=5 and p_global<global_threshold:
        result.update(decision='SUSPEND_LOW_VALUE',reason='Observed progress is low across directions; consider pausing and record where to resume.')
    elif episode['minutes']<5.0:
        result.update(decision='COLLECT_BASELINE',reason='Little episode history yet; continue the initial investigation.')
    elif p_switch>switch_threshold:
        ranked=[(sum(vals)/len(vals),d) for d,vals in draws.items() if d!=did]
        next_did=max(ranked)[1]
        result.update(decision='DIAGNOSE_AND_PIVOT',suggested_direction=next_did,
                      reason='Alternative direction likely outperforms episode after switching overhead. Diagnose first.')
    elif p_stalled > 0.68 and episode['events']==0:
        result.update(decision='ROTATE_ROLE_OR_METHOD',reason='Progress has slowed; revisit assumptions, literature or method.')
    else:
        result.update(decision='CONTINUE',reason='Marginal evidence does not justify switching or global suspension.')
    return result
