import json
import logging
import re
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
GATE_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["open", "deny", "hold"]},
        "reason": {"type": "string"},
    },
    "required": ["decision", "reason"],
}
NOTE_SCHEMA = {
    "type": "object",
    "properties": {"note": {"type": "string"}},
    "required": ["note"],
}


def _completion(
    messages: list[dict[str, Any]], transport: httpx.BaseTransport | None,
    use_tools: bool = True, timeout: float | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.ollama_model, "messages": messages, "stream": False,
        "temperature": 0,
    }
    if use_tools:
        payload.update({"tools": OPENAI_TOOLS, "tool_choice": "auto"})
    if schema is not None:
        # Ollama OpenAI 호환 structured output — 소형 모델 JSON 삑사리를 구조적으로 막는다
        payload["response_format"] = {
            "type": "json_schema", "json_schema": {"name": "answer", "schema": schema},
        }
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
    """조회는 코드(_facts_for), 판단은 라마(스키마 강제 1콜), 실행(측정 요청·정합성)은 코드."""
    facts, recent_check = _facts_for(payload.plate, when)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"차량={payload.plate}, 방향={payload.direction}, "
            f"요청시각(KST)={when.isoformat()}\n"
            f"[사전 조사 결과]\n{facts}\n"
            "위 사실을 근거로 판단하라. 출차인데 '평소보다 2시간 넘게 어긋남' 또는 '심야 여부: 예'면 "
            "이상 출차 → 음주측정이 pending이거나 없으면 hold, pass면 open, fail이면 deny. "
            "입차이거나 이상이 없으면 open. reason은 한국어 한 문장으로 근거를 쓴다."
        )},
    ]
    message = _completion(messages, transport, use_tools=False, schema=GATE_SCHEMA)
    content = message.get("content") or ""
    try:
        data = _normalize_decision(_extract_decision_json(content))
    except Exception as error:
        raise ValueError(f"최종 답 파싱 실패 ({error}): {content[:200]!r}") from error
    data["mode"] = "agent"
    check_id = recent_check["id"] if recent_check else None
    if data["decision"] == "hold" and check_id is None:
        # 라마가 hold로 판단 → 측정 요청 생성은 코드가 (판단은 라마 몫)
        check_id = TOOL_FUNCTIONS["request_sobriety_check"](payload.plate, when)["check_id"]
    data["check_id"] = check_id
    decision = AgentGateDecision.model_validate(data)
    return _guard_sobriety_consistency(decision, check_id)


def _extract_decision_json(content: str) -> dict[str, Any]:
    """소형 모델은 JSON을 여러 개 뱉거나 뒤에 설명을 붙인다.
    → 첫 번째로 온전히 닫히는 JSON 객체를 쓰고, 그것도 깨졌으면 정규식으로 건진다."""
    decoder = json.JSONDecoder()
    index = content.find("{")
    while index >= 0:
        try:
            obj, _ = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            index = content.find("{", index + 1)
            continue
        if isinstance(obj, dict):
            if "decision" not in obj and "note" not in obj and "name" in obj:  # 툴 호출 흉내
                obj = {"decision": obj["name"], "reason": str(obj.get("parameters") or "")}
            return obj
        index = content.find("{", index + 1)
    match = re.search(r'"decision"\s*:\s*"([^"]+)"', content)
    if not match:
        raise ValueError("JSON도 decision 필드도 없음")
    reason = re.search(r'"reason"\s*:\s*"([^"]*)"', content)
    check = re.search(r'"check_id"\s*:\s*(\d+)', content)
    return {
        "decision": match.group(1),
        "reason": reason.group(1) if reason else "",
        "check_id": int(check.group(1)) if check else None,
    }


DECISION_ALIASES = {
    "open": "open", "allow": "open", "approve": "open", "pass": "open",
    "열림": "open", "허용": "open", "통과": "open", "개방": "open",
    "deny": "deny", "reject": "deny", "block": "deny", "close": "deny",
    "거부": "deny", "차단": "deny", "닫힘": "deny", "불가": "deny",
    "hold": "hold", "wait": "hold", "pending": "hold",
    "대기": "hold", "보류": "hold", "측정대기": "hold",
}


def _normalize_decision(data: dict[str, Any]) -> dict[str, Any]:
    """소형 모델이 'OPEN', '허용', reason을 dict로 주는 등 형식을 흔드는 걸 받아준다."""
    raw = str(data.get("decision", "")).strip().lower().replace(" ", "")
    decision = DECISION_ALIASES.get(raw)
    if decision is None:
        for key, value in DECISION_ALIASES.items():
            if key in raw:
                decision = value
                break
    if decision is None:
        raise ValueError(f"decision 해석 불가: {data.get('decision')!r}")
    reason = data.get("reason")
    if not isinstance(reason, str):
        reason = json.dumps(reason, ensure_ascii=False, default=str) if reason else ""
    check_id = data.get("check_id")
    if isinstance(check_id, str):
        check_id = int(check_id) if check_id.strip().isdigit() else None
    elif not isinstance(check_id, int):
        check_id = None
    return {"decision": decision, "reason": reason.strip() or "(사유 없음)", "check_id": check_id}


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
def _facts_for(plate: str, when: datetime) -> tuple[str, dict[str, Any] | None]:
    """라마가 툴을 여러 번 돌지 않아도 되게 핵심 사실을 미리 한국어로 정리한다.
    (조회는 코드가 하고, 판단은 라마가 한다). 최근 1시간 음주측정 row도 같이 돌려준다."""
    vehicle = TOOL_FUNCTIONS["lookup_vehicle"](plate)
    history = TOOL_FUNCTIONS["get_exit_history"](plate, when)
    hours = [e["hour_kst"] for e in history["exits"]]
    if vehicle["registered"]:
        reg = f"등록 차량 (소유주 {vehicle['owner_name']}, {vehicle['vehicle_type']})"
    else:
        reg = "미등록 차량 (외부인)"
    now_hour = when.hour + when.minute / 60
    late_night = "예" if when.hour <= 5 else "아니오"
    if hours:
        avg = sum(hours) / len(hours)
        diff = abs(now_hour - avg)
        hist = (
            f"최근 30일 출차 {len(hours)}건, 평소 출차 시각 평균 {avg:.1f}시 (예: {hours[:5]}시)\n"
            f"- 지금은 평소보다 {diff:.1f}시간 어긋남 (2시간 넘으면 이상), 심야(00~05시) 여부: {late_night}"
            + (" → 이력 5건 미만이라 판단 근거 부족" if len(hours) < 5 else "")
        )
    else:
        hist = f"최근 30일 출차 이력 없음 (판단 근거 부족), 심야(00~05시) 여부: {late_night}"
    with get_conn() as conn:
        check = conn.execute(
            """select id, status from sobriety_checks
               where plate = %s and requested_at between %s - interval '1 hour' and %s
               order by requested_at desc, id desc limit 1""",
            (plate, when, when),
        ).fetchone()
    check_text = (
        f"최근 1시간 음주측정: id={check['id']} 상태={check['status']}"
        if check else "최근 1시간 음주측정 요청 없음"
    )
    facts = f"- {reg}\n- {hist}\n- 현재 KST {when.hour:02d}시 {when.minute:02d}분\n- {check_text}"
    return facts, (dict(check) if check else None)


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
    if kind == "외부인":
        guide = "외부인은 등록되지 않은 방문 차량이다. 몇 대가 어느 자리에 언제부터 있는지 말하고, 오래 머문 차량이 있으면 짚어라."
    else:
        guide = "꼬리물기 의심은 게이트 입차 기록 없이 주차면에 나타난 차량이다. 어느 자리의 어떤 차량인지 말하고 현장 확인을 권하라."
    facts = "; ".join(
        ", ".join(f"{k}={v}" for k, v in row.items() if v is not None) for row in rows
    ) or "해당 차량 없음"
    messages = [{"role": "system", "content": (
        "너는 주차장 관제 에이전트다. 한국어로만, 아래 사실에 있는 내용만 써서 두 문장 이내로 답하라. "
        "사실에 없는 내용(운전 실력, 차종, 성향 등)은 절대 지어내지 마라. " + guide
    )}, {
        "role": "user", "content": f"현재 KST={_kst().strftime('%Y-%m-%d %H:%M')}\n{kind} {len(rows)}대: {facts}",
    }]
    try:
        # 화면 목록 조회가 Ollama 장애로 오래 매달리지 않게 1회·짧은 타임아웃
        message = _completion(messages, transport, use_tools=False, timeout=30.0, schema=NOTE_SCHEMA)
        content = (message.get("content") or "").strip()
        note = str(_extract_decision_json(content).get("note", "")).strip() if content else ""
        if note:
            return " ".join(note.splitlines())[:300]
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
