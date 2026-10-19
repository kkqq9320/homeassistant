# IKEA E1744 MQTT 조명 제어 구현 계획

> **에이전트 실행자:** 필수 하위 스킬은 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`다. 선택한 실행 방식에 맞춰 작업별로 진행하고 체크박스로 추적한다.

**Goal:** E1744의 MQTT 동작으로 선택한 조명 기능을 조절하고, 꺼진 조명을 정해진 방향과 밝기 방식으로 켜는 블루프린트를 시험한 뒤 GitHub에 게시한다.

**Architecture:** 자동화 YAML 한 파일에서 MQTT 입력을 걸러 클릭과 회전을 분기한다. `restart` 실행 안의 반복이 목표값을 누적하고 시작·정지·시간 제한을 처리한다. 시험은 실제 HA 자동화와 MQTT 트리거를 실행하며, MQTT 전송부와 조명 서비스만 메모리 안의 대역으로 교체한다.

**Tech Stack:** Home Assistant Blueprint YAML, HA Jinja, Python 표준 라이브러리 `unittest`, 공식 HA Linux 컨테이너, Docker.

**Spec:** [IKEA E1744 조명 제어 설계](../specs/2026-10-19-z2m-ikea-e1744-light-control-design.md). 실행자는 이 계획과 설계를 함께 읽는다.

## Global Constraints

- 기능·입력 ID·기본값·경계 동작의 정본은 설계의 MQTT 계약, 입력과 기본값, 네 가지 회전 기능 절이다.
- 최소 지원 버전은 `2025.4.0`이다. 실제 실행에서 충족하지 못하면 게시 전에 구문을 고치거나 지원 하한 변경을 검토한다.
- 배포물은 `blueprints/automation/z2m_ikea_e1744_light_control.yaml` 한 파일이다. 센서·기기 ID·도우미·별도 Worker를 추가하지 않는다.
- 기존 Aqara 블루프린트와 테스트의 동작은 유지한다. 새 문서와 사용자에게 보이는 설명은 한국어로 쓴다.
- 시험은 로컬 임시 HA 환경에서 수행한다. 실제 HA 자동화의 교체, 센서 삭제, 장치 조작은 이 계획에 포함하지 않는다.
- 작업별로 실패 시험 → 구현 → 통과 확인 → 커밋 순서를 지킨다. 커밋 끝에 `Co-authored-by: Codex <noreply@openai.com>`을 넣는다.
- 작업 시작·결정·커밋·백그라운드 실행마다 작업 공간의 `HANDOFF.md`를 현재 브랜치·SHA·다음 작업으로 갱신한다.

## Review Focus

1. JSON이 `null`, 배열, 숫자이거나 `action`이 객체여도 실행 오류나 기존 회전 중단이 생기지 않아야 한다. 작업 1의 MQTT 입력 시험에서 다룬다.
2. 이전 명령의 상태 보고가 늦으면 같은 목표값을 반복해서 보내기 쉽다. 작업 2에서 보고값을 고정한 채 여러 목표값이 연속 증가하는지 시험한다.
3. 복원 밝기가 2초 안에 오지 않거나 대기 중 정지하면 추가 밝기·색상 명령을 보내지 않아야 한다. 작업 3에서 다룬다.
4. 서비스 호출 중 정지·클릭·반대 회전이 오면 취소된 실행이 다시 명령을 보내지 않아야 한다. 작업 4에서 호출을 막는 장벽과 실행별 context ID로 확인한다.
5. 로컬 시험 뒤 원격 `main`이 바뀌면 검증 결과와 게시 파일이 달라질 수 있다. 작업 5에서 원격 변경을 반영한 최종 후보를 시험하고 게시 후 SHA-256을 대조한다.

## 파일 구성

| 파일 | 책임 | 최초 작업 |
|---|---|---|
| `blueprints/automation/z2m_ikea_e1744_light_control.yaml` | 입력·MQTT·클릭·회전 실행 | 1 |
| `tests/ikea_runtime.py` | 실제 HA 자동화 로딩과 MQTT·서비스 시험 경계 | 1 |
| `tests/ikea_runtime_matrix.json` | 지원 하한과 개발 검증용 HA 이미지 태그 | 1 |
| `scripts/check_ikea.py` | Docker 실행·버전 선택·실패 종료 코드 전달 | 1 |
| `tests/test_ikea_contract.py` | 입력·스키마·MQTT·클릭·문서 연결 | 1, 5 |
| `tests/test_ikea_modes.py` | 네 기능의 계산·지원 여부·경계값 | 2 |
| `tests/test_ikea_startup.py` | 꺼진 조명의 시작 방향·복원·시간 초과 | 3 |
| `tests/test_ikea_lifecycle.py` | 중단·재시작·시간 제한·오류 | 4 |
| `blueprints/automation/z2m_ikea_e1744_light_control/README.md` | 가져오기·설정·동작·문제 확인 | 5 |
| `docs/reports/2026-10-19-ikea-e1744-local-validation.md` | 최종 후보의 실제 시험 결과와 적용 범위 | 5 |
| `README.md` | 새 블루프린트 소개와 전용 가이드·가져오기 링크 | 5 |

기존 `tests/__init__.py`를 사용한다. 제품 파일을 여러 YAML로 나누지 않는다.

## 실행 환경과 시험 인터페이스

2026-10-19 계획 기준 시험 행렬은 HA `2025.4.0`과 `2026.9.3`이다. 이 값을
`tests/ikea_runtime_matrix.json`의 `minimum`·`development` 키로 저장한다.
이미지는 `ghcr.io/home-assistant/home-assistant:<버전>`을 사용하고 실행 시
이미지 ID·digest와 실제 `homeassistant.const.__version__`를 출력한다.
새 테스트 패키지를 설치하지 않고 이미지에 포함된 HA와 Python 표준 라이브러리를 쓴다.

`scripts/check_ikea.py`의 명령 계약:

```text
python scripts/check_ikea.py --ha-version 2025.4.0 tests.test_ikea_contract
python scripts/check_ikea.py --ha-version 2026.9.3 tests.test_ikea_modes
python scripts/check_ikea.py --all
```

버전 한 개와 점으로 구분한 unittest 모듈·테스트 이름을 받을 수 있다. `--all`은
두 이미지에서 기존 Aqara 시험을 포함한 `unittest discover -s tests -p test_*.py`
전체를 실행한다. 이미지가 없으면 다운로드하고, 시험 컨테이너는 `--rm`,
`--network none`, `--entrypoint python`, 읽기 전용 저장소 마운트, `/workspace`
작업 폴더와 `-B`를 사용한다. HA의 설정·상태 파일은 컨테이너 임시 디렉터리에 둔다.
포트를 열거나 실제 HA 설정·토큰을 넘기지 않는다. 명령 실패는 0이 아닌 종료 코드로 전달한다.

시험 대역은 다음 인터페이스로 고정한다. 목표값 계산은 대역에 구현하지 않는다.

```python
@dataclass(frozen=True)
class RecordedCall:
    data: dict[str, Any]  # entity_id를 포함한 HA 서비스 입력
    at: float            # time.monotonic()
    context_id: str

class IkeaBlueprintCase(unittest.IsolatedAsyncioTestCase):
    hass: HomeAssistant
    light_calls: list[RecordedCall]
    click_calls: list[str]
    subscribed_topics: list[str]
    service_gate: asyncio.Event | None
    service_error: Exception | None
    async def load(self, inputs: dict[str, Any] | None = None) -> None: ...
    def set_light(self, state: str, **attributes: Any) -> None: ...
    async def publish(self, payload: dict[str, Any] | str | bytes,
                      *, topic: str | None = None) -> None: ...
    async def wait_calls(self, count: int, timeout: float = 3.0) -> None: ...
    async def wait_clicks(self, count: int, timeout: float = 3.0) -> None: ...
    async def reload_automations(self) -> None: ...
```

`load`는 필수 입력에 `knob="Test Knob"`, `target_light="light.ikea_test"`를
넣고 인자로 받은 입력만 덮어쓴다. 임시 설정 폴더에 배포 YAML을 복사하여 실제
HA `use_blueprint` 로딩·입력 확장·자동화 검증을 거친다. `automation` 구성요소와
MQTT 트리거의 템플릿·필터·콜백을 그대로 실행한다.

MQTT 대역은 `homeassistant.components.mqtt.trigger.async_subscribe_internal`의
전송 경계만 교체한다. 실제 구독 topic과 콜백을 저장하고 `publish`가 그 topic의
콜백에 HA `ReceiveMessage`를 전달한다. `publish`가 action을 미리 분류하거나
`automation.trigger`를 직접 호출하면 시험 범위를 우회하므로 그렇게 구현하지 않는다.

`light.turn_on` 대역은 입력·시각·context ID만 기록한다. 조명 상태는 시험이
`set_light`로 직접 보고한다. `service_gate`가 있으면 기록 후 그 장벽에서 기다리고,
`service_error`가 있으면 예외를 발생시킨다. 클릭 대역 서비스 `test.record_click`은
`label`을 `click_calls`에 추가한다. 각 시험 종료 때 자동화·HA·패치·임시 폴더를 정리한다.
진행 중인 반복을 모두 기다리는 전역 drain 대신 필요한 호출 수와 명시적 사건을 기다린다.

## Task 1: MQTT와 클릭이 실제 HA에서 실행되는 블루프린트

**Files:** 위 표의 최초 작업 1 파일을 생성한다.

**Interfaces:** 설계의 입력 ID 전체, 빈 클릭 기본값 세 개, 여섯 MQTT 동작과
`restart` 모드를 제공한다. 후속 작업은 위 시험 인터페이스를 사용한다.

- [ ] **실패 시험 작성:** `tests/test_ikea_contract.py`에서 HA 스키마, 입력 기본값,
  정확한 topic, 클릭 매핑, 잘못된 입력을 시험한다. 기본 클릭은 호출이 없고,
  지정한 action은 같은 클릭이 두 번 오면 두 번 실행되어야 한다.

```python
async def test_click_mapping_and_repeated_click(self):
    await self.load({
        "action_click_short": [{"action": "test.record_click", "data": {"label": "one"}}],
        "action_click_double": [{"action": "test.record_click", "data": {"label": "two"}}],
        "action_click_triple": [{"action": "test.record_click", "data": {"label": "three"}}],
    })
    for count, action in enumerate(
        ("toggle", "toggle", "brightness_step_up", "brightness_step_down"), start=1
    ):
        await self.publish({"action": action})
        await self.wait_clicks(count)
    self.assertEqual(self.click_calls, ["one", "one", "two", "three"])
    self.assertEqual(self.subscribed_topics, ["zigbee2mqtt/Test Knob"])
```

  `test_invalid_payloads_do_not_run`에 빈 문자열, 깨진 JSON, `null`, `[]`, `42`,
  `{}`, `{"battery": 90}`, `{"action": null}`, `{"action": {}}`, 알 수 없는 문자열을
  넣어 클릭·조명 호출이 모두 없는지 확인한다. 사용자 지정 base topic과 공백·대소문자를
  포함한 knob도 실제 구독 경로로 확인한다. 기본값·선택 범위는 설계의 입력 표와 대조한다.
- [ ] **실패 확인:** 시험 실행기와 HA 경계 코드를 먼저 준비하고
  `python scripts/check_ikea.py --ha-version 2025.4.0 tests.test_ikea_contract`를 실행한다.
  의도한 실패는 제품 YAML 부재 또는 클릭 계약 미충족이다. Docker·HA 초기화 오류는 먼저 해결한다.
- [ ] **구현:** YAML의 입력 섹션·`trigger_variables`·JSON 필터·`choose`를 작성한다.
  잘못된 JSON 객체 형태를 검사한 뒤 action 문자열을 판별한다. 클릭은 `!input`으로
  실행하고 stop은 추가 서비스 없이 종료한다. 회전 분기는 아직 명령 없이 종료한다.
- [ ] **검증:** 같은 명령을 두 행렬 버전에서 실행하여 계약 시험이 모두 통과하고
  YAML·블루프린트·확장 자동화 검증 오류가 없는지 확인한다.
- [ ] **커밋:** `feat: IKEA E1744 MQTT 입력과 클릭 동작 추가`.

## Task 2: 켜진 조명의 네 가지 반복 조절

**Files:** 제품 YAML을 수정하고 `tests/test_ikea_modes.py`를 생성한다.

**Interfaces:** 작업 1의 MQTT 경로를 통해 회전을 시작·중단한다. 실행 변수는
`direction`, `target_value`, `held_hue`, `held_saturation`, `deadline`으로 나눈다.
누적 목표값은 바깥 실행 범위에 초기화하고 반복 안에서 갱신한다.

- [ ] **실패 시험 작성:** 아래 시작값으로 한 반복의 결과를 고정한다. 양방향과
  다음 반복을 각각 확인하고 마지막에는 stop을 발행한다.

| 시험 | 시작값 | 오른쪽 첫 목표 | 왼쪽 첫 목표 |
|---|---|---|---|
| `test_brightness_steps` | brightness 102 = 40% | 42% | 38% |
| `test_kelvin_steps` | 4000 K, 범위 2200~6500 K | 4100 K | 3900 K |
| `test_hue_wraps` | HS [358, 70], 변화 2% | [5.2, 70] | [350.8, 70] |
| `test_saturation_steps` | HS [120, 50] | [120, 52] | [120, 48] |

```python
async def test_delayed_state_does_not_reset_targets(self):
    self.set_light("on", brightness=102, supported_color_modes=["brightness"])
    await self.load({"rotation_mode": "brightness"})
    await self.publish({"action": "brightness_move_up"})
    await self.wait_calls(3)
    await self.publish({"action": "brightness_stop"})
    self.assertEqual([c.data["brightness_pct"] for c in self.light_calls[:3]], [42, 44, 46])
```

  `test_limits_suppress_duplicate_calls`는 밝기 1·100%, 색온도 양 끝, 채도 0·100%에서
  값이 바뀌지 않는 명령이 반복되지 않는지 확인한다. `test_color_commands_preserve_brightness`
  는 색상 계열 호출에 밝기 필드가 없음을 확인한다. Hue 360 정규화, 채도 0 유지,
  비수치·누락 채도의 50 대체, 범위 밖 채도 거부도 시험한다.
- [ ] **실패 확인:** `python scripts/check_ikea.py --ha-version 2025.4.0 tests.test_ikea_modes`.
  아직 회전 명령이 없어 목표값 검증이 실패해야 한다.
- [ ] **구현:** 시작 상태·지원 기능·현재값을 검증하고 설계의 계산식을 적용한다.
  `brightness_pct`, `color_temp_kelvin`, `hs_color` 중 해당 필드만 보낸다.
  유한 수치·boolean 제외, 지원 범위·색상 성분 보존을 명시적으로 처리한다.
  첫 명령은 즉시, 후속 반복은 서비스 반환 뒤 설정 간격을 기다린다.
  이 단계에서 `deadline`과 on 상태 조건을 넣어 시험 실행이 스스로 종료되게 한다.
- [ ] **검증:** 두 HA 버전에서 작업 1·2 시험을 실행한다. 실제 반복 내부의 변수
  갱신으로 42→44→46이 나오는지 확인하며, 별도 Python 계산 모델로 대체하지 않는다.
- [ ] **커밋:** `feat: IKEA 노브의 밝기 색온도 색상 채도 조절 추가`.

## Task 3: 꺼진 조명의 시작 방향과 밝기 선택

**Files:** 제품 YAML을 수정하고 `tests/test_ikea_startup.py`를 생성한다.

**Interfaces:** `restore_brightness`는 밝기 기능에만 적용한다. 시작 시 off였는지
별도 변수로 기록하고, 시작 절차가 끝난 실행은 이후 off를 종료 조건으로 취급한다.

- [ ] **실패 시험 작성:** `test_off_brightness_left_does_nothing`을 복원 설정
  false·true에서 실행하여 명령 0개를 확인한다. 아래 시험은 첫 명령과 후속 값을 확인한다.

```python
async def test_zero_start_has_no_bare_turn_on(self):
    self.set_light("off", supported_color_modes=["brightness"])
    await self.load({"restore_brightness": False})
    await self.publish({"action": "brightness_move_up"})
    await self.wait_calls(1)
    self.assertEqual(self.light_calls[0].data["brightness_pct"], 2)
    self.set_light("on", brightness=5, supported_color_modes=["brightness"])
    await self.wait_calls(2)
    self.assertEqual(self.light_calls[1].data["brightness_pct"], 4)
```

  `test_restore_uses_reported_brightness`는 첫 호출에 밝기 필드가 없고, 40%로 켜짐을
  보고한 뒤 다음 목표가 42%인지 확인한다. `test_color_startup_both_directions`는
  세 기능×양방향에서 첫 호출이 켜기만 수행하고 다음 호출이 선택한 값만 변경하는지 확인한다.
  `test_startup_timeout_and_stop`은 속성 미보고·invalid 보고·대기 중 stop에서
  두 번째 명령이 없음을 검증한다. `test_short_deadline_bounds_startup_wait`는
  최대 실행 1초에서 2초 전체를 기다리지 않고 종료하는지 확인한다.
- [ ] **실패 확인:** `python scripts/check_ikea.py --ha-version 2025.4.0 tests.test_ikea_startup`.
  기존 on 전용 처리로 켜기 시험이 실패해야 한다.
- [ ] **구현:** 회전 기능·방향·지원 여부를 확인한 뒤 설계의 켜기 절차를 추가한다.
  0% 기준은 목표 밝기를 지정한 단일 명령으로 시작한다. 복원·색상 계열은 밝기 없는
  단일 명령과 상태 대기를 사용한다. 대기 성공 후에만 기준값을 읽고 반복을 이어간다.
  대기 제한은 `min(2초, deadline까지 남은 시간)`이며, 이미 제한에 도달했으면 종료한다.
- [ ] **검증:** 두 HA 버전에서 작업 1~3 시험을 실행한다. 시작 중 정지가 첫 켜기
  명령을 되돌리지는 않지만 추가 조절을 막는지 확인한다.
- [ ] **커밋:** `feat: IKEA 회전으로 조명 켜기와 시작 밝기 선택 추가`.

## Task 4: 반복 수명과 오류 경계

**Files:** 제품 YAML을 수정하고 `tests/test_ikea_lifecycle.py`를 생성한다.

**Interfaces:** 실제 HA `restart`가 중단을 담당한다. 입력 필터는 작업 1에서,
목표값과 deadline은 작업 2에서, off 시작 상태는 작업 3에서 제공한다.

- [ ] **실패 시험 작성:** 아래 각각을 독립 시험으로 작성한다.

```python
async def test_stop_during_service_prevents_later_calls(self):
    self.set_light("on", brightness=102, supported_color_modes=["brightness"])
    self.service_gate = asyncio.Event()
    await self.load()
    await self.publish({"action": "brightness_move_up"})
    await self.wait_calls(1)
    old_context = self.light_calls[0].context_id
    await self.publish({"action": "brightness_stop"})
    self.service_gate.set()
    await asyncio.sleep(0.45)
    self.assertEqual(sum(c.context_id == old_context for c in self.light_calls), 1)
```

  `test_new_gesture_cancels_old_context`는 장벽 중 반대 방향·클릭·동일 방향을
  각각 발행한다. 새 context는 새 상태를 기준으로 실행하고 이전 context에는 추가 호출이 없어야 한다.
  `test_empty_click_stops_rotation`은 클릭 동작이 비어 있어도 중단되는지 확인한다.
  `test_new_event_cancels_slow_click_sequence`는 클릭에 기록→1초 대기→기록을 넣고,
  첫 기록 뒤 stop을 보내면 두 번째 기록이 실행되지 않는지 확인한다.
  `test_non_action_report_does_not_interrupt`는 회전 도중 작업 1의 잘못된 입력을
  보내도 동일 context의 다음 목표값이 이어지는지 확인한다.

  `test_repeat_spacing_and_deadline`은 명령 사이 최소 간격과 시작 후 최대 시간에
  도달한 뒤 새 반복이 없음을 확인한다. `test_same_direction_restarts_deadline`은
  같은 방향 재수신이 새 실행·새 기준·새 제한 시간을 갖는지 확인한다.
  `test_off_unknown_unavailable_stop`은 진행 중 해당 상태로 바꾸면 새 켜기나 조절이
  없음을 확인한다. `test_reload_and_shutdown_cancel_rotation`은 실제 reload와 종료를
  각각 확인한다. `test_service_error_ends_run`은 서비스 예외 뒤 재시도가 없음을 확인한다.

  `test_invalid_attributes_fail_closed`는 지원하지 않는 모드, 누락값, boolean,
  NaN·무한대, 뒤집힌 Kelvin 범위, 범위 밖 Hue·채도에서 명령 0개와 종료 이유를 확인한다.
  채도 누락·비수치의 50 대체 규칙은 작업 2의 예외로 유지한다.
- [ ] **실패 확인:** `python scripts/check_ikea.py --ha-version 2025.4.0 tests.test_ikea_lifecycle`.
  이미 통과하는 계약은 회귀 시험으로 남기고, 드러난 실패를 해당 조건 수정 전에 기록한다.
- [ ] **구현:** 실패한 경계만 고친다. 수치·상태 검증 종료에는 구분되는 `stop` 사유를
  남기고, 서비스 오류를 `continue_on_error`로 숨기지 않는다. 실제 완료 시각이 늦어져도
  새 반복을 시작하지 않도록 서비스 이후와 대기 이후의 제한 시간을 확인한다.
- [ ] **검증:** `python scripts/check_ikea.py --all`. 두 버전에서 누락·skip 없이
  전체가 통과해야 한다. 시간 시험은 사건 장벽과 충분한 관측 구간을 사용하고,
  정확한 밀리초 단위 실행 시각을 요구하지 않는다.
- [ ] **커밋:** `fix: IKEA 회전 중단과 상태 오류 경계 검증`.

## Task 5: 사용 가이드·최종 검증·GitHub 게시

**Files:** 전용 가이드와 시험 보고서를 생성하고 루트 README 및 계약 시험을 수정한다.

**Interfaces:** 최종 YAML의 `source_url`은 설계의 공개 원본 주소다. 전용 가이드는
설치와 사용법을, 시험 보고서는 실제 검증 결과를 맡는다.

- [ ] **실패 시험 작성:** `test_document_links_and_source_url`에서 루트 README의
  전용 가이드 링크, 전용 가이드의 가져오기 URL, YAML `source_url`이 같은 공개 파일을
  가리키고 로컬 문서 링크가 존재하는지 확인한다. 아직 가이드가 없어 실패해야 한다.
- [ ] **문서 작성:** 가이드에는 E1744 식별, 정확한 Z2M 이름, 대상 조명/그룹,
  네 기능의 선택, 지원 색상 확인, 시작 밝기, 빈 클릭 설정, 반복 조절량, stop·시간 제한을
  담는다. 기존 자동화와 함께 켜면 이중 제어될 수 있으므로 사용자가 전환할 절차를 쓴다.
  센서 삭제나 기존 클릭 행동을 자동 수행하는 절차는 넣지 않는다.
- [ ] **최종 후보 검증:** `git fetch origin` 뒤 `origin/main` 변경을 확인한다.
  원격이 진전했으면 변경을 보존하여 통합하고 영향받는 시험 및 전체 행렬을 다시 실행한다.
  `python scripts/check_ikea.py --all`, `git diff --check`, 문서 링크 검사를 수행한다.
  오류·skip·설명되지 않은 경고가 남으면 게시하지 않는다.
- [ ] **독립 검토:** 선택한 실행 방식의 검토 절차로 최종 변경을 검토한다. 수정이
  생기면 해당 시험과 필요한 전체 시험을 다시 실행하고 검토 결과를 정리한다.
- [ ] **시험 보고서와 커밋:** 실제 HA/Python 버전, 이미지 digest, 명령·결과·시험 수,
  YAML SHA-256, 검증한 Git 후보, 합성 MQTT 입력임을 보고서에 기록한다. 실기기 MQTT와
  물리 반응을 시험한 것으로 표시하지 않는다. `docs: IKEA 블루프린트 사용법과 검증 결과 추가`로 커밋한다.
- [ ] **게시:** `git merge-base --is-ancestor origin/main HEAD`가 성공하는 최종 후보를
  기능 브랜치에 push하고 `git push origin HEAD:main`으로 일반 fast-forward 게시한다.
  직전 원격 변화로 push가 거절되면 fetch·통합·재검증하고, 강제 push는 사용하지 않는다.
  실행 시 보호 규칙이 바뀌어 PR이 필요하면 규칙에 따라 PR을 만들고 채팅에 연결한다.
- [ ] **게시 결과 확인:** 원격 `main`에서 YAML을 다시 받아 로컬 최종 파일과
  SHA-256을 비교하고 `source_url` 및 가져오기 링크가 게시된 파일을 가리키는지 확인한다.
  브랜치 push나 PR 생성만으로 완료 처리하지 않는다. 최종 응답에는 가져오기 링크,
  게시 SHA, 로컬 시험 결과와 사용자가 설정할 클릭 입력을 안내한다.

## 완료 기준

다섯 작업이 커밋되어 있고 두 HA 버전의 실제 자동화 실행 시험과 기존 회귀 시험이
통과해야 한다. 원격 기본 브랜치의 YAML이 검증된 산출물과 같아야 한다.
사용자의 실제 HA 설치·클릭 지정과 실기기 조작 확인은 게시 이후 설치 단계다.

## 실행 방식

이 계획은 같은 YAML을 순서대로 확장하므로 이 대화에서 순차 구현하고 마지막에
별도 검토자가 전체를 검토하는 방식을 권장한다. 작업마다 새 구현 에이전트와
검토 에이전트를 두는 방식도 가능하며, 단계별 독립 검토가 늘어나는 대신 비용이 더 든다.
계획 검토와 실행 방식 선택 뒤에 구현을 시작한다.

## 확인한 HA 실행 경계

2026-10-19 확인한
[HA 2025.4.0 MQTT 트리거](https://github.com/home-assistant/core/blob/2025.4.0/homeassistant/components/mqtt/trigger.py)와
[HA 2026.9.3 MQTT 트리거](https://github.com/home-assistant/core/blob/2026.9.3/homeassistant/components/mqtt/trigger.py)는
모두 `async_subscribe_internal`을 통해 실제 MQTT 콜백을 연결한다.
[Blueprint 입력 확장](https://github.com/home-assistant/core/blob/2025.4.0/homeassistant/components/blueprint/models.py)과
[자동화 구성 검증](https://github.com/home-assistant/core/blob/2025.4.0/homeassistant/components/automation/config.py)은
대역으로 교체하지 않고 HA 구현을 사용한다.
