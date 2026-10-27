"""Rank sensitivity, not confidence intervals, probabilities or scenario averages."""
import itertools

RULES = dict(stable_max_rank_range=0, moderate_max_rank_range=2)


def compare(results, reference='moderate_pressure_v1'):
    available={k:v for k,v in results.items() if v.get('level') in (2,3) and k!='observed_only'}
    ids=sorted({r['action_id'] for v in available.values() for r in v['candidate_actions']})
    maps={k:{r['action_id']:r for r in v['ranking']} for k,v in available.items()};ref=maps.get(reference,{})
    ranges=[]
    for aid in ids:
        ranks={k:m[aid]['rank'] if aid in m else None for k,m in maps.items()};known=[v for v in ranks.values() if v is not None]
        if not known:continue
        spread=max(known)-min(known)
        ranges.append(dict(action_id=aid,best_rank=min(known),worst_rank=max(known),ranks=ranks,
            rank_change={k:v-ref[aid]['rank'] if v is not None else None for k,v in ranks.items()} if aid in ref else {},
            robustness='Unsupported under some tested assumptions' if len(known)<len(maps) else 'Stable across tested assumptions' if spread==0 else 'Moderately sensitive' if spread<=RULES['moderate_max_rank_range'] else 'Highly sensitive'))
    pairwise=[]
    for a,b in itertools.combinations(ids,2):
        if any(a not in m or b not in m for m in maps.values()):continue
        signs={k:(m[a]['q']>m[b]['q'])-(m[a]['q']<m[b]['q']) for k,m in maps.items()}
        pairwise.append(dict(actions=[a,b],ordering=signs,stable=len(set(signs.values()))==1))
    tops={k:next((r['action_id'] for r in v['ranking'] if r['rank']==1),None) for k,v in available.items()}
    return dict(rank_ranges=ranges,top_choice_stability=dict(stable=len(set(tops.values()))==1 if tops else None,top_by_scenario=tops),
        pairwise_ordering=pairwise,ordering_changes=[x for x in pairwise if not x['stable']],rules=RULES,
        limitation='Only tested assumption sensitivity; no scenario-frequency probabilities or average expected Q2.')
