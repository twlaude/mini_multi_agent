"""Human Approval을 적용하기 전에 Tool 행동을 위험도로 분류합니다.

이 파일은 실제 AI Agent를 실행하는 예제가 아닙니다. 향후 AI Agent가 Tool이나 행동을
제안했을 때 Backend가 그 제안을 그대로 실행하지 않고, 위험도에 따라 다음 세 경로 중
하나를 선택하는 정책의 출발점입니다.

``AI Agent 행동 제안 → Backend 위험도 분류 → 자동 실행·승인 대기·차단``

* ``read``·``draft``: 외부 상태를 변경하지 않으므로 승인 없이 실행할 수 있습니다.
* ``change``: 메시지 전송처럼 외부 상태를 변경하므로 구체적인 사용자 승인 후 실행합니다.
* ``forbidden``: 현재 Agent에 허용할 수 없는 행동이므로 사용자 승인과 관계없이 차단합니다.
* 등록되지 않은 Action: 안전을 위해 기본 차단하는 fail-closed 정책을 적용합니다.

여행 AI Agent의 행동으로 표현하면 다음과 같습니다.

``날씨 조회 → read → 승인 없이 자동 실행``

``여행 일정 초안 작성 → draft → 외부 상태를 바꾸지 않으므로 자동 실행``

``캘린더에 일정 저장 → change → 사용자 승인 이후 실행``

``현재 Agent에 허용하지 않은 결제 실행 → forbidden → 사용자가 승인해도 실행 차단``

``change``는 올바른 사용자·권한·실행 대상이 확인되고 구체적인 승인을 받으면 실행할 수
있지만, ``forbidden``은 현재 Agent의 허용 범위 밖이므로 승인으로 허용 상태가 되지 않습니다.

Agent는 필요한 행동을 제안할 뿐이며 실제 실행 권한은 갖지 않습니다. 자동 실행,
승인 요청 또는 거부를 결정하는 주체는 Prompt나 LLM이 아니라 Backend 정책입니다.

이번 파일에서 하는 일
----------------------
1. Action별 위험도를 read, draft, change와 forbidden으로 선언합니다.
2. 위험도에 따라 자동 허용, 승인 요청 또는 차단 중 다음 통제를 결정합니다.
3. 정책에 등록되지 않은 Action을 기본 차단하는 fail-closed 원칙을 확인합니다.
"""

from dataclasses import dataclass
from typing import Literal


Risk = Literal["read", "draft", "change", "forbidden"]


@dataclass(frozen=True)
class ActionPolicy:
    """Action 이름, 위험도와 사용자에게 보여줄 설명을 묶은 불변 정책입니다."""

    name: str
    risk: Risk
    description: str


POLICIES = {
    "search_policy": ActionPolicy("search_policy", "read", "정책 문서를 조회합니다."),
    "create_draft": ActionPolicy("create_draft", "draft", "전송하지 않는 초안을 만듭니다."),
    "send_message": ActionPolicy("send_message", "change", "외부 사용자에게 메시지를 전송합니다."),
    "make_payment": ActionPolicy("make_payment", "forbidden", "교육 과정에서 결제를 금지합니다."),
}


def classify_action(action_name: str) -> dict:
    """Action 이름을 Backend 정책으로 분류해 다음 통제 단계를 반환합니다.

    Args:
        action_name: Model이나 Workflow가 실행하려고 제안한 Action 이름입니다.

    Returns:
        Action, 위험도와 ``allow``·``request_approval``·``block`` 중 다음 단계를
        담은 dict입니다. 등록되지 않은 Action은 ``unknown``으로 분류하고 차단합니다.
    """
    policy = POLICIES.get(action_name)
    if policy is None:
        return {"action": action_name, "risk": "unknown", "next": "block"}
    next_step = {
        "read": "allow",
        "draft": "allow",
        "change": "request_approval",
        "forbidden": "block",
    }[policy.risk]
    return {"action": policy.name, "risk": policy.risk, "next": next_step}


if __name__ == "__main__":
    for name in ("search_policy", "create_draft", "send_message", "make_payment", "unknown_tool"):
        print(classify_action(name))
