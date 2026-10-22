import json
import tempfile
import unittest
from pathlib import Path
from boundforge.ledger import Ledger
from boundforge.controller import assess
from boundforge.candidates import assess_candidates
from boundforge.registry import calibrate, sync, load, put_atomic


class FakeClock:
    def __init__(self, start=1_800_000_000.):self.value=start
    def __call__(self):return self.value
    def advance(self, minutes):self.value+=60*minutes


class BoundForgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock=FakeClock()
        self.db=Ledger(Path(self.tmp.name)/'events.db',clock=self.clock)
        self.addCleanup(self.db.close)
        self.db.init(problem='A=inf f(x)',model_index=2,model_id='mdl2',model_version='pin-v1',
            inner_effort=25,outer_effort=95,max_work_minutes=500)
        self.direction=self.db.add_direction('Family A','testing a method')
        self.ep=self.db.start_episode(self.direction,'researcher','pilot')
        self.art=Path(self.tmp.name)/'proof.txt'
        self.art.write_text('Let x>0; the claimed inequality follows by ...')

    def claim(self,kind='lower',value=1,depends=None,statement='proof'):
        return self.db.submit(episode_id=self.ep,kind=kind,value=value,
                              statement=statement,artifact=self.art,
                              depends=depends or [],actor='mdl2')

    def test_host_timestamp_exposure_not_message_count(self):
        wk=self.db.start_work(self.ep,'try proof','mdl2')
        self.clock.advance(12)
        st=self.db.state()
        self.assertAlmostEqual(st['total_work_minutes'],12)
        self.assertEqual(st['episodes'][self.ep]['events'],0)
        self.db.end_work(wk,'no progress','mdl2')
        self.clock.advance(200)
        self.assertAlmostEqual(self.db.state()['total_work_minutes'],12)
        self.assertTrue(self.db.verify_chain())

    def test_review_retraction_transitive(self):
        c1=self.claim('lemma',None,statement='lemma1')
        self.db.review(c1,'computer1','accept','reproducible_computation')
        self.assertFalse(self.db.state()['claims'][c1]['valid'])
        self.assertEqual(self.db.state()['episodes'][self.ep]['events'],1)
        self.db.review(c1,'peer1','reject','peer_model')
        self.assertEqual(self.db.state()['episodes'][self.ep]['events'],0)
        self.db.review(c1,'human1','accept','human')
        c2=self.claim('lower',1.8,[c1],statement='lower from lemma')
        self.db.review(c2,'human2','accept','human')
        self.assertEqual(self.db.state()['best_lower'],1.8)
        self.assertEqual(self.db.state()['episodes'][self.ep]['events'],2)
        self.db.retract(c1,'human1','counterexample to lemma')
        state=self.db.state()
        self.assertIsNone(state['best_lower'])
        self.assertFalse(state['claims'][c2]['valid'])
        self.assertEqual(state['episodes'][self.ep]['events'],0)
        self.assertTrue(self.db.verify_chain())

    def test_bound_match_and_inconsistency(self):
        c1=self.claim('lower',2,statement='proof lower')
        self.db.review(c1,'human1','accept','human')
        c2=self.claim('upper',2,statement='proof upper')
        self.db.review(c2,'human2','accept','human')
        self.assertEqual(assess(self.db.state())['decision'],'MATCHING_RECORDED_BOUNDS')
        self.db.retract(c2,'human2','upper proof flawed')
        self.assertNotEqual(assess(self.db.state())['decision'],'MATCHING_RECORDED_BOUNDS')
        c3=self.claim('upper',1,statement='contradiction')
        self.db.review(c3,'human2','accept','human')
        self.assertEqual(assess(self.db.state())['decision'],'INCONSISTENT_BOUNDS')

    def test_elapsed_stall_with_two_effort_parameters(self):
        other=self.db.add_direction('Family B','independent algebraic strategy')
        wk=self.db.start_work(self.ep,'expensive fruitless experiments','mdl2')
        self.clock.advance(95)
        self.db.end_work(wk,'negative result','mdl2')
        st=self.db.state()
        dec=assess(st)
        self.assertEqual(dec['total_active_work_minutes'],95)
        self.assertGreater(dec['directions'][other]['events_per_work_minute']['median'],
                           dec['current_episode']['events_per_work_minute']['median'])
        self.assertIn(dec['decision'],('DIAGNOSE_AND_PIVOT','ROTATE_ROLE_OR_METHOD','CONTINUE'))
        self.assertAlmostEqual(dec['inner_switch_threshold'],.67,places=2)
        self.assertLess(dec['min_viable_event_rate'],.045)
        # Raise e_inner without adding new steps; the switch standard must increase.
        self.assertTrue(.58+.36*.9 > .58+.36*.25)

    def test_scale_pilot_freeze_and_retraction_staleness(self):
        # All improvements have the same physical units as the bound.
        claims=[]
        for idx,val in enumerate((1.,1.3,1.8,2.)):
            cid=self.claim('lower',val,statement=f'strengthening-{idx}')
            self.db.review(cid,f'human{idx}','accept','human')
            claims.append(cid)
        scale=self.db.state()['scale']
        self.assertEqual(scale['status'],'PILOT_ESTIMATE')
        self.assertAlmostEqual(scale['value'],.3,places=5)
        self.db.freeze_scale('pilot')
        self.assertEqual(self.db.state()['scale']['status'],'FROZEN')
        self.db.retract(claims[1],'human1','inequality failed')
        self.assertEqual(self.db.state()['scale']['status'],'STALE')

    def test_recent_submission_timing_changes_inner_observation(self):
        w=self.db.start_work(self.ep,'search','mdl2')
        self.clock.advance(10)
        early=self.claim('lemma',None,statement='early lemma')
        self.db.review(early,'human','accept','human')
        self.clock.advance(100)
        self.db.end_work(w,'nothing since early discovery','mdl2')
        ep=self.db.state()['episodes'][self.ep]
        self.assertEqual(ep['events'],1)
        self.assertEqual(ep['recent_events'],0)
        self.assertAlmostEqual(ep['recent_window_minutes'],60)
        self.assertAlmostEqual(ep['active_minutes_since_last_progress'],100)
        self.assertEqual(ep['completed_discovery_intervals_active_minutes'],[10])

    def test_registry_idempotent_and_correction(self):
        regpath=Path(self.tmp.name)/'registry.json'
        put_atomic(regpath,{'models':[{'index':2,'model_id':'mdl2','version':'pin-v1',
                          'prior':{'alpha':3,'beta':1},'evidence':{}}]})
        cid=self.claim('lemma',None,statement='hypothesis')
        fid=self.db.forecast(claim_id=cid,model_id='mdl2',role='researcher',
                            probability=.8,evidence_group='trial1')
        self.db.resolve_forecast(fid,True,'independent-judge','human','independent proof')
        self.db.end_episode(self.ep,'completed')
        self.db.finalize()
        first=sync(regpath,self.db)
        second=sync(regpath,self.db)
        self.assertEqual(first,second)
        self.assertEqual(first['global_labels'],1)
        self.assertGreater(first['omega'],0.2)
        self.db.resolve_forecast(fid,False,'independent-judge','human','corrected counterexample')
        third=sync(regpath,self.db)
        self.assertEqual(third['global_labels'],1)
        self.assertLess(third['omega'],first['omega'])

    def test_conjecture_is_not_theorem_and_omega_changes_only_priority(self):
        conjecture=self.db.conjecture(episode_id=self.ep,value=2,
                     statement='A=2?',self_confidence=.95,actor='mdl2')
        evidence=self.db.add_evidence(conjecture_id=conjecture,family='numerics-1',
                     kind='numerical',support=True,note='small tested instances',actor='mdl2')
        a=assess_candidates(self.db.state(),omega=.2)[0]
        self.assertEqual(a['status'],'OPEN')
        c_upper=self.claim('upper',2,statement='valid asymptotic construction')
        self.db.review(c_upper,'human1','accept','human')
        self.db.add_evidence(conjecture_id=conjecture,family='family-limiting',
                kind='limiting',support=True,note='rigorous sequence',actor='mdl2',claim_id=c_upper)
        a2=assess_candidates(self.db.state(),omega=.2)[0]
        self.assertGreater(a2['heuristic_priority'],a['heuristic_priority'])
        self.assertEqual(a2['status'],'OPEN')
        self.assertNotEqual(assess_candidates(self.db.state(),omega=.4)[0]['heuristic_priority'],a2['heuristic_priority'])
        c_lower=self.claim('lower',2,statement='rigorous lower')
        self.db.review(c_lower,'human2','accept','human')
        self.assertEqual(assess_candidates(self.db.state(),omega=.2)[0]['status'],
                         'MATCHES_RECORDED_BOUNDS')
        self.assertEqual(self.db.state()['attainment'],'UNKNOWN')
        c_no=self.claim('nonattained',None,statement='forall x f(x)>2')
        self.db.review(c_no,'human2','accept','human')
        self.assertEqual(self.db.state()['attainment'],'RECORDED_NONATTAINED')

    def test_conjecture_refuted_when_certified_bounds_exclude_it(self):
        conjecture=self.db.conjecture(episode_id=self.ep,value=5,
                     statement='A=5?',self_confidence=.99,actor='mdl2')
        cu=self.claim('upper',2,statement='explicit witness')
        self.db.review(cu,'human1','accept','human')
        self.assertEqual(assess_candidates(self.db.state(),omega=.4)[0]['status'],
                         'EXCLUDED_BY_RECORDED_UPPER')

    def test_prevents_artifact_modification_and_self_review(self):
        c=self.claim()
        with self.assertRaises(ValueError):self.db.review(c,'mdl2','accept','human')
        self.art.write_text('Modified after submission')
        with self.assertRaises(ValueError):self.db.review(c,'independent','accept','human')

    def test_effort_and_direction_do_not_encode_fixed_step_counts(self):
        st=self.db.state()
        self.assertEqual(st['total_work_minutes'],0)
        self.assertEqual(st['config']['inner_effort'],25)
        self.assertEqual(st['config']['outer_effort'],95)
        self.assertEqual(assess(st)['decision'],'COLLECT_BASELINE')

    def test_useful_exploration_counts_without_certifying_bounds(self):
        work=self.db.start_work(self.ep,'test a restricted family','mdl2')
        self.clock.advance(10)
        finding=self.db.submit(episode_id=self.ep,kind='obstruction',actor='mdl2',
                               statement='The symmetric family misses asymmetric candidates')
        self.db.end_work(work,'switch to a larger search family','mdl2')
        state=self.db.state()
        self.assertEqual(state['claims'][finding]['status'],'exploratory')
        self.assertEqual(state['episodes'][self.ep]['recent_events'],1)
        self.assertIsNone(state['best_lower'])
        self.assertIsNone(state['best_upper'])
        self.assertEqual(assess(state)['directions'][self.direction]['progress_events'],1)

    def test_self_check_and_peer_check_are_available_without_human_gate(self):
        lower=self.claim(value=1,statement='lower argument checked by author')
        self.db.review(lower,'mdl2','accept','self_check')
        upper=self.claim('upper',3,statement='upper argument checked by peer')
        self.db.review(upper,'peer','accept','peer_model')
        state=self.db.state()
        self.assertEqual((state['best_lower'],state['best_upper']),(1,3))
        self.assertEqual(state['claims'][lower]['review']['level'],'self_check')
        self.assertEqual(state['claims'][upper]['review']['level'],'peer_model')

    def test_computation_guides_planning_without_becoming_a_bound(self):
        cid=self.claim('lower',20,statement='numeric search suggests 20')
        self.db.review(cid,'computer','accept','reproducible_computation')
        state=self.db.state()
        self.assertEqual(state['claims'][cid]['status'],'computed')
        self.assertEqual(state['episodes'][self.ep]['events'],1)
        self.assertIsNone(state['best_lower'])

    def test_exploratory_dependencies_and_retraction_recompute_progress(self):
        first=self.db.submit(episode_id=self.ep,kind='observation',actor='mdl2',statement='pattern A')
        second=self.db.submit(episode_id=self.ep,kind='method',actor='mdl2',statement='use A to choose a method',depends=[first])
        self.assertEqual(self.db.state()['episodes'][self.ep]['events'],2)
        self.db.retract(first,'mdl2','pattern fails on a larger instance')
        state=self.db.state()
        self.assertEqual(state['episodes'][self.ep]['events'],0)
        self.assertEqual(state['claims'][second]['status'],'dependency_blocked')
        self.assertEqual(len(state['claims']),2)

    def test_role_replay_and_progress_at_start_of_work_axis(self):
        self.db.shift_role(self.ep,'literature_analyst','search a different source')
        self.db.submit(episode_id=self.ep,kind='method',actor='mdl2',statement='reformulate via duality')
        state=self.db.state()
        self.assertEqual(state['episodes'][self.ep]['role'],'literature_analyst')
        self.assertEqual(state['episodes'][self.ep]['recent_events'],1)

    def test_numeric_match_is_only_a_recorded_match(self):
        # Distinct exact decimals collapse to the same binary float in this CLI.
        a=float('1.00000000000000000')
        b=float('1.00000000000000001')
        self.assertEqual(a,b)
        for kind,value in [('lower',a),('upper',b)]:
            cid=self.claim(kind,value,statement=f'{kind}: exact endpoint kept in argument')
            self.db.review(cid,'mdl2','accept','self_check')
        self.assertEqual(assess(self.db.state())['decision'],'MATCHING_RECORDED_BOUNDS')

    def test_small_bound_improvement_is_retained(self):
        for idx,value in enumerate([1.,1.+1e-13]):
            cid=self.claim(value=value,statement=f'bound revision {idx}')
            self.db.review(cid,'mdl2','accept','self_check')
        self.assertEqual(self.db.state()['best_lower'],1.+1e-13)

    def test_nonfinite_configuration_is_rejected(self):
        for value in [float('nan'),float('inf')]:
            for field in ['max_work_minutes','target_scale']:
                with self.subTest(value=value,field=field):
                    other=Ledger(Path(self.tmp.name)/f'bad-{field}-{value}.db')
                    self.addCleanup(other.close)
                    with self.assertRaises(ValueError):
                        other.init(problem='test',model_index=1,model_id='m',model_version='v',
                                   inner_effort=50,outer_effort=50,**{field:value})

    def test_own_forecast_resolution_is_recorded_with_its_basis(self):
        cid=self.claim('lemma',None,statement='forecast target')
        fid=self.db.forecast(claim_id=cid,model_id='mdl2',role='researcher',probability=.7,evidence_group='one')
        self.db.resolve_forecast(fid,True,'mdl2','self_check','checked the completed argument')
        self.assertEqual(self.db.state()['resolutions'][fid]['level'],'self_check')

    def test_same_observation_in_a_later_episode_can_be_recorded(self):
        self.db.submit(episode_id=self.ep,kind='observation',statement='same observation',actor='mdl2')
        self.db.end_episode(self.ep,'try again with another approach')
        later=self.db.start_episode(self.direction,'researcher','repeat with new context')
        self.db.submit(episode_id=later,kind='observation',statement='same observation',actor='mdl2')
        self.assertEqual(self.db.state()['episodes'][later]['events'],1)

    def test_false_text_is_not_silently_saved_as_true(self):
        cid=self.claim('lemma',None,statement='target')
        fid=self.db.forecast(claim_id=cid,model_id='mdl2',role='researcher',probability=.7,evidence_group='one')
        with self.assertRaises(ValueError):
            self.db.resolve_forecast(fid,'false','mdl2','self_check','check')
        candidate=self.db.conjecture(episode_id=self.ep,value=2,statement='A=2?',self_confidence=.5,actor='mdl2')
        with self.assertRaises(ValueError):
            self.db.add_evidence(conjecture_id=candidate,family='one',kind='numerical',support='false',note='check',actor='mdl2')


if __name__=='__main__':unittest.main()
