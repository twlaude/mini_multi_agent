import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
import httpx

logger = logging.getLogger("parking.agent")
from app.config import settings
from app.core.db import get_conn
from app.domains.parking_agent.schemas import AgentGateDecision, AgentGateRequest
from app.domains.parking_agent.tools import OPENAI_TOOLS, TOOL_FUNCTIONS
KST = ZoneInfo("Asia/Seoul")
SYSTEM_PROMPT = """너는 주차장 관제 에이전트다. 반드시 툴로 조사한 뒤 판단한다.
입차는 등록 차량이면 '등록 차량', 미등록이면 '외부인 입차 — 방문 기록'으로 open한다.
출차 이력이 5건 미만이면 open한다. 그 외에는 평소 시각의 ±2시간 밖이거나
현재 KST가 00~05시면 이상 출차다. 이상 출차는 request_sobriety_check를 호출한다.
최근 1시간 check가 pass면 open, fail이면 deny하고 drunk_suspect alert를 만들며,
pending이면 hold한다. 툴 결과에 error가 있으면 인자를 고쳐 다시 호출한다.
최종 답은 설명 없이
{"decision":"open|deny|hold","reason":"근거(반드시 한국어)","check_id":숫자 또는 null} JSON만 쓴다."""
VISITOR_SQL = """with last_gate as (
 select distinct on (plate) plate,direction,decision,created_at from gate_events
 order by plate,created_at desc,id desc)
select g.plate,g.created_at entered_at,
 case when s.event='occupied' then s.spot_id end spot_id from last_gate g
left join lateral (select spot_id,event from spot_events where plate=g.plate
 order by created_at desc,id desc limit 1) s on true
where g.direction='enter' and g.decision='open' and not exists
 (select 1 from vehicles v where v.plate=g.plate) order by g.created_at desc"""
TAILGATING_SQL = """select plate,spot_id,observed_at from (
 select distinct on (s.plate) s.plate,s.spot_id,s.created_at observed_at
 from spot_events s where s.event='occupied' and (not exists (
  select 1 from gate_events g where g.plate=s.plate and g.direction='enter'
  and g.decision='open' and g.created_at between
  s.created_at-interval '24 hours' and s.created_at) or exists (
  select 1 from alerts a where a.plate=s.plate and a.alert_type='tailgating'
  and a.resolved=false)) order by s.plate,s.created_at desc,s.id desc
) candidates order by observed_at desc"""
def _kst(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(KST)
    return value.replace(tzinfo=KST) if value.tzinfo is None else value.astimezone(KST)
def _completion(
    messages: list[dict[str, Any]], transport: httpx.BaseTransport | None,
    use_tools: bool = True, timeout: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.ollama_model, "messages": messages, "stream": False,
    }
    if use_tools:
        payload.update({"tools": OPENAI_TOOLS, "tool_choice": "auto"})
    timeout = settings.request_timeout_seconds if timeout is None else timeout
    with httpx.Client(transport=transport, timeout=timeout) as client:
        response = client.post(
            f"{settings.ollama_base_url}/v1/chat/completions", json=payload
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
    if not isinstance(message, dict):
        raise ValueError("Ollama message 형식이 올바르지 않습니다.")
    return message
def _tool_loop(
    messages: list[dict[str, Any]], when: datetime,
    transport: httpx.BaseTransport | None, gate_plate: str | None = None,
    structured: bool = False,
) -> tuple[str, list[str], int | None]:
    names: list[str] = []
    check_id = None
    for _ in range(5):
        message = _completion(messages, transport)
        messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Ollama 최종 답변이 비어 있습니다.")
            return content, names, check_id
        for call in calls:
            function = call["function"]
            name = function["name"]
            raw_args = function.get("arguments") or "{}"
            args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)
            if gate_plate and name in TOOL_FUNCTIONS:
                args["plate"] = gate_plate
            if gate_plate and name in {
                "get_exit_history", "get_gate_entry", "request_sobriety_check",
                "create_alert",
            }:
                args["at"] = when
            # 소형 모델은 툴 이름/인자를 틀리기도 한다 → 예외로 죽이지 말고
            # error를 툴 결과로 돌려줘서 다음 턴에 스스로 고치게 한다
            try:
                if name not in TOOL_FUNCTIONS:
                    raise ValueError(f"없는 툴: {name}")
                result = TOOL_FUNCTIONS[name](**args)
            except Exception as error:
                logger.warning("tool %s(%s) 실패: %s", name, args, error)
                result = {"error": str(error), "hint": "인자를 고쳐 다시 호출하라"}
            names.append(name)
            if name == "request_sobriety_check":
                check_id = result.get("check_id")
            context = {"request_at_kst": when.isoformat(), "result": result}
            messages.append({
                "role": "tool", "tool_call_id": call.get("id", ""), "name": name,
                "content": json.dumps(context, ensure_ascii=False, default=str),
            })
    content = (
        '{"decision":"deny","reason":"tool 호출 한도 초과","check_id":null}'
        if structured else "tool 호출 한도를 초과해 답변하지 못했습니다."
    )
    return content, names, check_id
def _agent_gate(
    payload: AgentGateRequest, when: datetime,
    transport: httpx.BaseTransport | None,
) -> AgentGateDecision:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"차량={payload.plate}, 방향={payload.direction}, "
            f"요청시각(KST)={when.isoformat()}"
        )},
    ]
    content, _, check_id = _tool_loop(
        messages, when, transport, payload.plate, structured=True
    )
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("최종 JSON 객체를 찾지 못했습니다.")
    data = json.loads(content[start:end + 1])
    data["mode"] = "agent"
    if data.get("decision") == "hold" and not data.get("check_id"):
        if check_id is None:
            raise ValueError("hold 판단 전에 음주측정 요청 툴을 호출해야 합니다.")
        data["check_id"] = check_id
    decision = AgentGateDecision.model_validate(data)
    return _guard_sobriety_consistency(decision, check_id)


def _guard_sobriety_consistency(
    decision: AgentGateDecision, check_id: int | None,
) -> AgentGateDecision:
    """소형 모델 안전장치: 라마가 음주측정을 요청해 놓고 결과와 모순되는 결정을 내면
    측정 상태(pending→hold, fail→deny)에 맞춘다. 라마의 reason 문장은 그대로 둔다."""
    if check_id is None:
        return decision
    with get_conn() as conn:
        row = conn.execute(
            "select status from sobriety_checks where id = %s", (check_id,)
        ).fetchone()
    status = row["status"] if row else None
    fixed = {"pending": "hold", "fail": "deny"}.get(status)
    if fixed and decision.decision != fixed:
        logger.warning("agent 결정 %s ↔ 측정 %s 모순 → %s로 보정", decision.decision, status, fixed)
        return decision.model_copy(update={
            "decision": fixed, "check_id": check_id,
            "reason": f"{decision.reason} (음주측정 {status} → {fixed} 보정)",
        })
    return decision.model_copy(update={"check_id": check_id})
def _record_gate(
    payload: AgentGateRequest, decision: AgentGateDecision, when: datetime,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """insert into gate_events
               (plate, direction, decision, reason, mode, created_at)
               values (%s, %s, %s, %s, 'agent', %s)""",
            (payload.plate, payload.direction, decision.decision, decision.reason, when),
        )
def _workflow_fallback(payload: AgentGateRequest, when: datetime) -> AgentGateDecision:
    from app.domains.parking_workflow.service import evaluate_gate

    result = evaluate_gate(payload.plate, payload.direction, when)
    return AgentGateDecision(
        decision=result["decision"], check_id=result.get("check_id"),
        reason="agent 실패 → workflow 폴백: " + result["reason"],
    )
def run_agent(
    payload: AgentGateRequest, transport: httpx.BaseTransport | None = None,
) -> AgentGateDecision:
    when = _kst(payload.at)
    for attempt in range(2):
        try:
            decision = _agent_gate(payload, when, transport)
            break
        except Exception as error:
            logger.warning("agent gate %d회차 실패: %s", attempt + 1, error)
            decision = None
    if decision is None:
        decision = _workflow_fallback(payload, when)
    _record_gate(payload, decision, when)
    return decision
def _list_rows(sql: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        return [dict(row) for row in conn.execute(sql).fetchall()]
def list_visitors() -> list[dict[str, Any]]:
    return _list_rows(VISITOR_SQL)
def list_tailgating() -> list[dict[str, Any]]:
    return _list_rows(TAILGATING_SQL)
def agent_note(
    kind: str, rows: list[dict[str, Any]],
    transport: httpx.BaseTransport | None = None,
) -> str:
    """조회 결과를 라마가 관제 담당자 관점에서 해석한 한 줄 코멘트 (추론 단계)."""
    messages = [{"role": "system", "content": (
        "너는 주차장 관제 에이전트다. 아래 조회 결과를 보고 관제 담당자에게 "
        "한국어 한두 문장으로 판단을 말하라: 몇 대인지, 가장 주의할 차량과 그 이유, "
        "권장 조치. 표나 목록 없이 문장으로만."
    )}, {
        "role": "user", "content": f"현재 KST={_kst().isoformat()}\n{kind} 조회 결과: " +
        json.dumps(rows, ensure_ascii=False, default=str),
    }]
    try:
        # 화면 목록 조회가 Ollama 장애로 오래 매달리지 않게 1회·짧은 타임아웃
        content = _completion(messages, transport, use_tools=False, timeout=20.0)
        content = (content.get("content") or "").strip()
        if content:
            return " ".join(content.splitlines())[:300]
    except Exception as error:
        logger.warning("agent_note(%s) 실패: %s", kind, error)
    return f"(에이전트 응답 없음) {kind} 차량 {len(rows)}대를 확인했습니다."
def ask_agent(
    question: str, transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    when = _kst()
    visitors = list_visitors()
    tailgating = list_tailgating()
    # 소형 모델이 JSON 덤프는 잘 못 읽어서 한국어 문장으로 정리해 준다
    visitor_text = ", ".join(
        f"{v['plate']}({v.get('spot_id') or '자리 미상'}, {str(v['entered_at'])[:16]} 입차)"
        for v in visitors
    ) or "없음"
    tail_text = ", ".join(
        f"{t['plate']}({t.get('spot_id') or '자리 미상'})" for t in tailgating
    ) or "없음"
    messages = [
        {"role": "system", "content": (
            "너는 주차장 관제 에이전트다. 반드시 한국어로 답한다. "
            "외부인/꼬리물기 현황은 아래 '현재 상황'에 이미 있으니 그걸로 바로 답하고, "
            "특정 차량의 등록 여부·출차 이력·입차 기록이 필요할 때만 툴을 쓴다. "
            "툴 결과에 error가 있으면 인자를 고쳐 다시 호출한다."
        )},
        {"role": "user", "content": (
            f"현재 KST={when.isoformat()}\n"
            f"[현재 상황] 주차 중인 외부인 {len(visitors)}대: {visitor_text}\n"
            f"[현재 상황] 꼬리물기 의심 {len(tailgating)}대: {tail_text}\n"
            f"질문: {question}"
        )},
    ]
    for attempt in range(2):
        try:
            answer, names, _ = _tool_loop(messages.copy(), when, transport)
            return {"answer": answer, "tool_calls": names}
        except Exception as error:
            logger.warning("ask_agent %d회차 실패: %s", attempt + 1, error)
    return {"answer": "Ollama 연결 실패로 답변하지 못했습니다.", "tool_calls": []}
