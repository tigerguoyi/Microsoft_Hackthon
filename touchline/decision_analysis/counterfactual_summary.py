"""Bound, compact Agent evidence. Full playback frames never enter a model prompt."""
import copy
from contracts.model import digest

VERSION = 'counterfactual-tool-1'
LIMITATIONS = [
    'Deterministic movement hypotheses, not observed future match events.',
    'Scenario frequencies are not success probabilities, confidence intervals or a Q2 validation.',
    'Simplified short movement; no aerial physics, rebounds, contact skill or fatigue.',
    'Complete synthetic observations only; video revisions and partial assumptions are not implemented in Phase 1–3.',
]


def full_observation_context(document):
    """Reject future modes rather than dropping their provenance fields."""
    source = document.get('source') or {}
    snapshot = document.get('snapshot') or {}
    for value in (document, source, snapshot):
        if (any(k in value for k in ('video_id', 'revision_id', 'assumption_set_id'))
                or value.get('observation_mode', 'full_observation') != 'full_observation'
                or value.get('visibility_scope_id', 'full_snapshot') != 'full_snapshot'):
            raise ValueError('Video/partial context requires a future versioned adapter; not available in Phase 1–3')
    if source.get('dataset', 'league') != 'league':
        raise ValueError('Only the registered synthetic league is supported by this Agent tool')
    return dict(source_type='synthetic_match', observation_mode='full_observation', visibility_scope_id='full_snapshot')


def summarize(result, candidate):
    binding = {k: result[k] for k in ('snapshot_id', 'data_version', 'candidate_set_id', 'action_id', 'action_type')}
    evidence_id = 'counterfactual:' + digest([VERSION, binding])
    assumptions = list(result['assumptions'])
    cases = []
    for scenario in result['scenarios']:
        cases.append(dict(**binding, scenario_id=scenario['id'], outcome=scenario['outcome'],
            main_risk=candidate['main_risk'], assumptions=assumptions,
            limitations=LIMITATIONS, evidence_id=evidence_id + ':' + scenario['id'],
            source_type='counterfactual_hypothesis', reaction_s=scenario['reaction_s'],
            duration_s=scenario['duration_s'], controller_id=scenario.get('controller_id')))
    return copy.deepcopy(dict(**binding, schema_version=VERSION, evidence_id=evidence_id,
        source_type='counterfactual_hypothesis', input_source_type='synthetic_match',
        observation_mode='full_observation', visibility_scope_id='full_snapshot',
        rollout_supported=True, counterfactual_supported=True, cases=cases,
        main_risk=candidate['main_risk'], assumptions=assumptions, limitations=LIMITATIONS,
        public_evidence_ids=candidate['evidence_ids'], summary=result['summary'],
        ranking_unchanged=True, not_observed_future=True))
