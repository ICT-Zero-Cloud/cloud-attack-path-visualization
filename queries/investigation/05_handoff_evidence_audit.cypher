// Q5: 집계 IP 플래그를 그대로 믿지 않고 같은 시간창의 실행·사용 근거를 대조.
// $key=''이면 선택 계정의 모든 후보를 보여준다.
WITH datetime($from) AS t0, datetime($to) AS t1
MATCH (a:Credential)-[g:CAN_OBTAIN]->(b:Credential)
WHERE ($key='' OR a.id=$key OR b.id=$key)
  AND ($account='' OR a.accountId=$account)
CALL {
  WITH a, b, g, t0, t1
  MATCH (b)-[binding:CONTEXT {rel:'RUNS_ON'}]->(w:Workload)
  WHERE w.id IN coalesce(g.viaWorkloads, [])
  MATCH (a)-[control:BASE_EVENT]->(w)
  WHERE control.outcome='SUCCESS'
    AND control.eventName IN $control_apis
    AND control.eventTime >= t0 AND control.eventTime <= t1
  OPTIONAL MATCH (b)-[use:BASE_EVENT]->(:Node)
  WHERE use.outcome='SUCCESS'
    AND use.eventTime >= control.eventTime AND use.eventTime <= t1
  WITH w, binding, control.eventID AS controlId, control.eventTime AS controlAt,
       control.eventName AS controlApi, control.sourceIP AS controlSource,
       collect(DISTINCT CASE WHEN use IS NOT NULL THEN
         {eventID:use.eventID, at:use.eventTime, api:use.eventName, source:use.sourceIP}
         END) AS laterUses
  RETURN collect(DISTINCT {
    workload:w.id, bindingFirstSeen:binding.firstSeen, bindingLastSeen:binding.lastSeen,
    controlEventID:controlId, controlAt:controlAt, controlApi:controlApi,
    controlSource:controlSource, laterUses:laterUses,
    sameSourceInWindow:coalesce(controlSource,'') <> ''
      AND NOT (coalesce(controlSource,'') ENDS WITH '.amazonaws.com')
      AND any(u IN laterUses WHERE u.source=controlSource)
  }) AS checks
}
RETURN a.id AS sourceKey, b.id AS candidateKey,
       g.at AS aggregateCandidateAt, coalesce(g.exercised,false) AS aggregateIpFlag,
       size(checks) AS controlEvidenceRows,
       CASE WHEN size(checks)=0 THEN 'no-selected-control-evidence-in-window'
            WHEN any(c IN checks WHERE c.sameSourceInWindow)
              THEN 'ordered-control-and-same-source-use'
            WHEN any(c IN checks WHERE size(c.laterUses)>0)
              THEN 'later-use-without-matching-control-source'
            ELSE 'no-later-successful-use-in-window' END AS evidenceStatus,
       checks
ORDER BY sourceKey, candidateKey
LIMIT $row_limit;

