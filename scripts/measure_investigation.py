#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
measure_investigation.py — 조사 질의 실험 A/B (CSV 위에서 질의 전략을 Python으로 재현).

실험 A: 제안 질의(앵커 기준 상류 발급계보 + 하류 자격증명 연쇄 + 종단 사용)가 구성한
        이벤트/연결의 정확성 (이벤트 P/R/F1, 연결 P/R/F1, 설명완성, 문맥포함량).
실험 B: 같은 그래프·시작사건·시간창에서 세 전략(시간창 / k-홉 이웃 / 제안)의
        출력 규모·필수근거 보존(이벤트·연결 recall 및 시간순)·무관 개수 비교. (축소는 설명 완성일 때 성과)

주의: 측정 대상은 'Python으로 구현한 질의 전략'. Cypher 동등성은 별도 대조로 확인.
사용: python measure_investigation.py --gt groundtruth_json/aws.5_chain_n4.investigation.json --csv csv/aws.5_chain_n4
"""
import argparse, csv, json, re, sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

def load_edges(d):
    with (Path(d)/'edges.csv').open(encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))

def is_cred(nid): return bool(re.match(r'^(AKIA|ASIA)', nid or ''))
def timestamp(t): return datetime.fromisoformat(t.replace('Z', '+00:00'))
def within(t, f, to): return timestamp(f) <= timestamp(t) <= timestamp(to)
def succ(r): return r.get('outcome')=='SUCCESS' and r.get('dstAs')!='Service' and r['src']!=r['dst']
def is_obtains(r): return r.get('rel')=='OBTAINS' and r.get('outcome')=='SUCCESS'

def rel_cat(r):
    if r.get('rel') in ('OBTAINS','CAN_OBTAIN'): return r['rel']
    if r.get('eventName')=='UpdateAssumeRolePolicy': return 'CHANGE'
    return 'USE'

def load_table(directory, name):
    with (Path(directory)/name).open(encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))


def candidate_handoffs(edges, context, candidates, f, to, require_same_source=True,
                       control_apis=('SendCommand','SendSSHPublicKey')):
    """Each candidate retains actual control/use witnesses and two timestamps."""
    bindings={(c['src'],c['dst']) for c in context if c['rel']=='RUNS_ON'}
    result={}
    window=[r for r in edges if within(r['eventTime'],f,to)]
    for g in candidates:
        for workload in g['viaWorkloads'].split('|'):
            if (g['dst'],workload) not in bindings: continue
            controls=[r for r in window if r['src']==g['src'] and r['dst']==workload
                      and succ(r) and r['eventName'] in control_apis]
            uses=[r for r in window if r['src']==g['dst'] and succ(r)]
            for control in controls:
                for use in uses:
                    if timestamp(use['eventTime']) < timestamp(control['eventTime']): continue
                    source=control.get('sourceIP','')
                    same=bool(source and not source.endswith('.amazonaws.com') and source==use.get('sourceIP'))
                    if require_same_source and not same: continue
                    key=(g['src'],g['dst'],workload,control['eventID'],use['eventID'])
                    result[key]=dict(src=g['src'],dst=g['dst'],rel='CAN_OBTAIN',
                        eventID='',eventTime=control['eventTime'],arrivalTime=use['eventTime'],
                        workload=workload,controlEventID=control['eventID'],useEventID=use['eventID'],
                        sameSource=same,evidenceClass='candidate-handoff',witnesses=[control,use])
    return list(result.values())


def proposed(edges, anchor_id, f, to, handoffs=None, include_inferred=False, inferred_out=None, target_resource="", effect_apis=()):
    """상류 발급 근거 + 하류 발급/행위. 반환: 이벤트, 연결, 선택 행, 앵커."""
    anchors=[r for r in edges if r.get('eventID')==anchor_id and succ(r) and within(r['eventTime'],f,to)]
    if not anchors: raise ValueError('Successful anchor not found in time window')
    a=anchors[0]; actor=a['src']; atime=a['eventTime']
    # OBTAINS 인접
    obt_in=defaultdict(list)   # dst <- (src,edge)
    obt_out=defaultdict(list)  # src -> (dst,edge)
    for r in edges:
        if is_obtains(r) and within(r['eventTime'],f,to):
            obt_in[r['dst']].append(r); obt_out[r['src']].append(r)
    if include_inferred:
        for r in handoffs or []:
            obt_in[r['dst']].append(r); obt_out[r['src']].append(r)
    ret_edges={}   # connection tuple -> edge
    conns=set()
    def addedge(r):
        if r.get('rel') == 'CAN_OBTAIN':
            if inferred_out is not None and r not in inferred_out: inferred_out.append(r)
            for witness in r['witnesses']: addedge(witness)
            return
        c=(rel_cat(r), r['src'], r['dst'], r['eventID'])
        ret_edges[c]=r
        conns.add(c)
    # 앵커(변경) 간선
    for r in anchors: addedge(r)
    arrivals={actor: timestamp(atime)}
    issue_events=set()
    # 상류: actor 로 들어오는 OBTAINS 를 시간 비증가로 역추적 (<= atime)
    frontier=[(actor, timestamp(atime), (actor,))]
    while frontier:
        node,tmax,path=frontier.pop()
        if len(path)-1 >= 6: continue
        for r in obt_in.get(node,[]):
            if timestamp(r.get('arrivalTime',r['eventTime']))<=tmax and r['src'] not in path and is_cred(r['src']) and is_cred(r['dst']):
                addedge(r); issue_events.add(r.get('eventID',''))
                frontier.append((r['src'], timestamp(r['eventTime']), path+(r['src'],)))
    # 하류: actor 에서 나가는 OBTAINS 연쇄 (>= atime)
    frontier=[(actor, timestamp(atime), (actor,))]
    while frontier:
        node,tmin,path=frontier.pop()
        if len(path)-1 >= 6: continue
        for r in obt_out.get(node,[]):
            if timestamp(r['eventTime'])>=tmin and r['dst'] not in path and is_cred(r['src']) and is_cred(r['dst']):
                addedge(r); issue_events.add(r.get('eventID',''))
                at=timestamp(r.get('arrivalTime',r['eventTime']))
                arrivals[r['dst']]=min(arrivals.get(r['dst'],at),at)
                frontier.append((r['dst'], at, path+(r['dst'],)))
    # 발급 이벤트의 역할/사용자 대상 근거 + 도달 시각 이후의 후속 행위.
    for r in edges:
        companion=r['eventID'] in issue_events
        effect=(r['src'] in arrivals and not is_obtains(r)
                and (not target_resource or r['dst']==target_resource)
                and (not effect_apis or r['eventName'] in effect_apis)
                and timestamp(r['eventTime']) >= arrivals[r['src']])
        if (companion or effect) and succ(r) and within(r['eventTime'],f,to):
            addedge(r)
    events={r['eventID'] for r in ret_edges.values()}
    return events, conns, list(ret_edges.values()), a

def khop(edges, actor, k, f, to):
    adj=defaultdict(list)
    for r in edges:
        if within(r['eventTime'],f,to) and r['src']!=r['dst']:
            adj[r['src']].append(r); adj[r['dst']].append(r)
    frontier={actor}; visited={actor}; selected={}
    for _ in range(k):
        nxt=set()
        for node in frontier:
            for r in adj.get(node,[]):
                selected[(rel_cat(r),r['src'],r['dst'],r['eventID'],r.get('controlEventID',''),r.get('useEventID',''))]=r
                other=r['dst'] if r['src']==node else r['src']
                if other not in visited: visited.add(other); nxt.add(other)
        frontier=nxt
    rows={}
    for r in selected.values():
        for item in r.get('witnesses',[r]):
            rows[(rel_cat(item),item['src'],item['dst'],item['eventID'])]=item
    return list(rows.values())

def prf(hit, returned_non_ctx, required_n):
    # returned_non_ctx = 필수적중 + 무관ретturned (문맥 제외)
    prec = hit/returned_non_ctx if returned_non_ctx else 0.0
    rec  = hit/required_n if required_n else 1.0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    return prec, rec, f1

def evaluate(rows, gt):
    events={r['eventID'] for r in rows}
    conns={(rel_cat(r),r['src'],r['dst'],r['eventID']) for r in rows}
    req_ev=set(gt['required_events'])
    ctx_ev=set(gt['context_events'])
    boundary=set(gt.get('entry_unlinkable',{}))
    req_conn={tuple(c) for c in gt['required_connections']}
    ctx_conn={tuple(c) for c in gt['context_connections']}
    def score(returned, required, allowed):
        hit=len(returned & required)
        false=len(returned-required-allowed)
        p,r,f=prf(hit,hit+false,len(required))
        return dict(precision=p,recall=r,f1=f,hits=hit,required=len(required),false=false,context=len(returned & allowed))
    ep=score(events,req_ev,ctx_ev|boundary)
    cp=score(conns,req_conn,ctx_conn)
    times=defaultdict(set)
    for row in rows: times[row['eventID']].add(timestamp(row['eventTime']))
    checks={}
    for before,after in gt['temporal_constraints']:
        checks[before+' <= '+after]=(len(times[before])==len(times[after])==1 and max(times[before])<=min(times[after]))
    for i,pair in enumerate(gt.get('same_role_checks',[])):
        change,assume=map(tuple,pair)
        checks['same_role_'+str(i+1)]=(change in conns and assume in conns and change[1:3]==assume[1:3])
    return dict(returned_events=len(events),returned_connections=len(conns),events=ep,connections=cp,
                context_events=len(events & ctx_ev),boundary_events=len(events & boundary),
                checks=checks,complete=ep['recall']==cp['recall']==1 and all(checks.values()),
                event_ids=sorted(events),connection_tuples=sorted(conns))


def main():
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    ap=argparse.ArgumentParser()
    ap.add_argument('--gt',required=True,type=Path)
    ap.add_argument('--csv',required=True,type=Path)
    ap.add_argument('--output',type=Path)
    ap.add_argument('--mode',choices=['observed','inferred','both'],default='observed')
    ap.add_argument('--allow-different-source',action='store_true')
    ap.add_argument('--account',default='',help='Anchor account; intermediate accounts remain traversable')
    ap.add_argument('--target-resource',default='',help='Filter terminal effects; preserve connecting evidence')
    ap.add_argument('--effect-api',action='append',default=[])
    args=ap.parse_args()
    gt=json.loads(args.gt.read_text(encoding='utf-8'))
    edges=load_edges(args.csv)
    universe={r['eventID'] for r in edges if r.get('eventID')}
    if not set(gt['required_events']) <= universe: raise ValueError('GT events missing from CSV; use full event IDs')
    f,to=gt['window']['from'],gt['window']['to']
    _,_,selected,anchor=proposed(edges,gt['anchor_event'],f,to,target_resource=args.target_resource,effect_apis=args.effect_api)
    if args.account:
        nodes={r['id']:r for r in load_table(args.csv,'nodes.csv')}
        if nodes.get(anchor['src'],{}).get('accountId')!=args.account:
            raise ValueError('Anchor account does not match --account')
    window=[r for r in edges if r.get('eventID') and within(r['eventTime'],f,to)]
    strategies={'time_window':window}
    strategies.update({f'k{k}':khop(edges,anchor['src'],k,f,to) for k in (1,2,3)})
    if args.mode in ('observed','both'): strategies['proposed']=selected
    inferred=[]
    if args.mode in ('inferred','both'):
        # Use a view directory explicitly: missing candidate input is an error.
        handoffs=candidate_handoffs(edges,load_table(args.csv,'context.csv'),
            load_table(args.csv,'canobtain.csv'),f,to,not args.allow_different_source)
        _,_,expanded,_=proposed(edges,gt['anchor_event'],f,to,handoffs,True,inferred,args.target_resource,args.effect_api)
        strategies['proposed_inferred']=expanded
        for k in (1,2,3):
            strategies[f'k{k}_inferred']=khop(edges+handoffs,anchor['src'],k,f,to)
    result=dict(anchor=gt['anchor_event'],window=gt['window'],dataset_events=len(universe),
                window_events=len({r['eventID'] for r in window}),
                strategies={name:evaluate(rows,gt) for name,rows in strategies.items()})
    result['scope']=dict(account=args.account,target_resource=args.target_resource,effect_apis=args.effect_api)
    result['mode']=args.mode
    result['inferred_handoffs']=[{k:v for k,v in r.items() if k!='witnesses'} for r in inferred]
    result['inferred_handoff_pairs']=len({(r['src'],r['dst']) for r in inferred})
    result['require_same_source']=not args.allow_different_source
    baseline=result['strategies']['time_window']
    for name,m in result['strategies'].items():
        m['reduction_vs_window']=(1-m['returned_events']/baseline['returned_events'] if m['complete'] and baseline['complete'] else None)
        e,c=m['events'],m['connections']
        print(f"{name}: events={m['returned_events']} required={e['hits']}/{e['required']} links={c['hits']}/{c['required']} irrelevant={e['false']} complete={m['complete']}")
    p=result['strategies'].get('proposed',result['strategies'].get('proposed_inferred')); k3=result['strategies']['k3']
    result['proposed_reduction_vs_k3']=(1-p['returned_events']/k3['returned_events'] if p['complete'] and k3['complete'] else None)
    print('Proposed event metrics:',p['events'])
    print('Proposed connection metrics:',p['connections'])
    print('Reduction vs window:',p['reduction_vs_window'])
    print('Reduction vs k3:',result['proposed_reduction_vs_k3'])
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
