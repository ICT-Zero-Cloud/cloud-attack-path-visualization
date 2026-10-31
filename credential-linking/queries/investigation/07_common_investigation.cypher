// Common investigation: $include_inferred toggles workload candidates.
// Read-only. No attack sequence or resource name is fixed.
// Each hop has a start (control/issuance) and arrival (use/issuance).
WITH datetime($from) AS t0, datetime($to) AS t1
MATCH (anchor:Credential)-[seed:BASE_EVENT]->(:Node)
WHERE seed.eventID=$event_id AND seed.outcome='SUCCESS' AND seed.dstAs<>'Service'
  AND seed.eventTime>=t0 AND seed.eventTime<=t1
  AND ($account='' OR anchor.accountId=$account)
WITH DISTINCT anchor, seed.eventID AS anchorId, seed.eventTime AS anchorTime, t0, t1
CALL {
  WITH anchor
  MATCH p=(origin:Credential)-[:BASE_EVENT|CAN_OBTAIN*0..6]->(anchor)
  RETURN p, 'upstream' AS direction
  UNION ALL
  WITH anchor
  MATCH p=(anchor)-[:BASE_EVENT|CAN_OBTAIN*0..6]->(actor:Credential)
  RETURN p, 'downstream' AS direction
}
WITH *, relationships(p) AS links
WHERE all(n IN nodes(p) WHERE n:Credential AND single(m IN nodes(p) WHERE m=n))
  AND all(r IN links WHERE
    (type(r)='BASE_EVENT' AND r.rel='OBTAINS' AND r.outcome='SUCCESS')
    OR (type(r)='CAN_OBTAIN' AND $include_inferred))
CALL {
  WITH links, t0, t1
  // Sentinel keeps zero-hop paths alive.
  UNWIND CASE WHEN size(links)=0 THEN [-1] ELSE range(0,size(links)-1) END AS idx
  WITH idx, CASE WHEN idx<0 THEN null ELSE links[idx] END AS r, t0, t1
  CALL {
    WITH r, t0, t1
    WITH r, t0, t1 WHERE type(r)='BASE_EVENT'
      AND r.eventTime>=t0 AND r.eventTime<=t1
    RETURN {begin:r.eventTime, arrival:r.eventTime, kind:'observed-issuance',
      source:startNode(r).id, target:endNode(r).id,
      eventIDs:[r.eventID], workload:null} AS option
    UNION ALL
    WITH r, t0, t1
    WITH r, t0, t1 WHERE type(r)='CAN_OBTAIN'
    MATCH (a:Credential)-[control:BASE_EVENT]->(w:Workload)<-[:CONTEXT {rel:'RUNS_ON'}]-(b:Credential)
    WHERE a=startNode(r) AND b=endNode(r) AND w.id IN coalesce(r.viaWorkloads,[])
      AND control.outcome='SUCCESS' AND control.dstAs<>'Service'
      AND control.eventName IN $control_apis
      AND control.eventTime>=t0 AND control.eventTime<=t1
    MATCH (b)-[use:BASE_EVENT]->(target:Node)
    WHERE use.outcome='SUCCESS' AND use.dstAs<>'Service' AND b<>target
      AND use.eventTime>=control.eventTime AND use.eventTime<=t1
      AND (NOT $require_same_source OR
        (coalesce(control.sourceIP,'')<>'' AND NOT control.sourceIP ENDS WITH '.amazonaws.com'
         AND use.sourceIP=control.sourceIP))
    RETURN {begin:control.eventTime, arrival:use.eventTime, kind:'candidate-handoff',
      source:a.id, target:b.id, eventIDs:[control.eventID,use.eventID], workload:w.id} AS option
    UNION ALL
    WITH r, t0, t1
    WITH r WHERE r IS NULL
    RETURN null AS option
  }
  WITH idx, collect(DISTINCT option) AS options ORDER BY idx
  RETURN collect({idx:idx,options:options}) AS steps
}
// Require an option for EVERY hop; a failed hop must not disappear.
WITH *, CASE WHEN size(links)=0 THEN [] ELSE steps END AS actualSteps
WHERE size(links)=0 OR size(steps)=size(links)
WITH *, reduce(states=[{arrival:CASE WHEN direction='upstream' THEN t0 ELSE anchorTime END, evidence:[]}],
  step IN actualSteps |
  reduce(nextStates=[], state IN states |
    nextStates+[o IN step.options WHERE o.begin>=state.arrival |
      {arrival:o.arrival,evidence:state.evidence+[o]}])) AS validStates
UNWIND validStates AS state
WITH * WHERE direction='downstream' OR state.arrival<=anchorTime
WITH *, last(nodes(p)) AS actor
OPTIONAL MATCH (actor)-[effect:BASE_EVENT]->(target:Node)
WHERE direction='downstream' AND effect.outcome='SUCCESS' AND effect.dstAs<>'Service'
  AND actor<>target AND effect.eventID<>anchorId
  AND effect.eventTime>=state.arrival AND effect.eventTime<=t1
  AND (size($effect_apis)=0 OR effect.eventName IN $effect_apis)
  AND ($target_resource='' OR target.id=$target_resource)
WITH *, [e IN state.evidence | e.eventIDs] AS evidenceIds
RETURN DISTINCT anchorId, direction, [n IN nodes(p)|n.id] AS credentialSequence,
  state.evidence AS connectingEvidence,
  size([e IN state.evidence WHERE e.kind='candidate-handoff']) AS inferredHops,
  effect.eventID AS effectId, effect.eventTime AS effectAt,
  effect.eventName AS effectApi, target.id AS effectTarget,
  size(links)=6 AS touchesHopLimit
ORDER BY direction, credentialSequence, effectAt;
