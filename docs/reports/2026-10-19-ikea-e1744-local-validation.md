# IKEA E1744 로컬 자동화 시험

2026-10-19, 제품 코드 기준 커밋 `a73c0810498a618fbcd780f8d8fe6e20a05d44c9`.

[블루프린트](../../blueprints/automation/z2m_ikea_e1744_light_control.yaml)의
SHA-256은 `2ed532abf16675322693771e10908cfbba52b1e982d679217861fe032f949ab2`다.

## 실행 환경과 결과

공식 `ghcr.io/home-assistant/home-assistant` 이미지를 Docker Linux 엔진에서
네트워크 없이 실행했다. 저장소는 읽기 전용으로 연결하고 HA 설정은 임시 폴더에 생성했다.

| HA 이미지 태그 | Python | unittest 결과 |
|---|---|---|
| `2025.4.0` | `3.13.2` | 83개 통과, 실패·오류·skip 0 |
| `2026.9.3` | `3.14.6` | 83개 통과, 실패·오류·skip 0 |

확인한 이미지 digest:

- `2025.4.0`: `sha256:97d21a71f4807d9903e1db119daebd80951ac7d5736894036638ea6ebc6f6730`
- `2026.9.3`: `sha256:d8922685169707fd91e8b9729902d975f06157d005e422874d201e0261dda196`

실행 명령:

```console
python scripts/check_ikea.py --all
```

호스트에는 Python과 Docker Linux 엔진이 필요하다. 시험 버전은
[실행 행렬](../../tests/ikea_runtime_matrix.json)에 정의되어 있다.
[실행기](../../scripts/check_ikea.py)는 이미지가 없으면 내려받고, 시험 실패 시
0이 아닌 종료 코드를 반환한다. 특정 시험은 `--ha-version`과 unittest 경로로 선택한다.

`2026.9.3` 이미지에서는 HA 초기화 모듈을 불러올 때 포함된 `rich/segment.py:547`이
Python 3.14의 `SyntaxWarning: 'return' in a 'finally' block`을 출력했다.
제품 YAML이나 시험 실패에서 발생한 경고가 아니며, 경고를 숨기는 설정은 적용하지 않았다.

## 검증 범위

[실행 환경](../../tests/ikea_runtime.py)은 HA의 `use_blueprint` 로딩, 입력 확장,
자동화 스키마, MQTT 트리거 필터와 콜백, 템플릿, 실제 자동화 실행기를 사용한다.
MQTT 구독 전송 경계와 조명·클릭 서비스만 대체한다. 조명 서비스 대역은 호출과
시각·context ID를 기록하며, 상태 보고는 시험에서 별도로 전달한다.

IKEA 시험 50개와 기존 Aqara 회귀 시험 33개를 실행했다.

- MQTT: 정확한 topic, 클릭 1·2·3회 매핑, 연속 클릭, 빈 클릭, 잘못된 JSON·동작 없는 보고 무시.
- 배포 연결: 루트 README·가이드의 가져오기 주소와 YAML `source_url` 일치, 문서의 로컬 링크 존재.
- 조절: 네 기능의 양방향 계산, 밝기·Kelvin·채도 한계, Hue 순환, 다른 색상 성분과 밝기 유지,
  늦은 상태 보고에도 연속 목표값 유지.
- 시작: 꺼진 밝기 왼쪽 회전 무시, 0% 기준과 복원 밝기 시작, 색상 계열 양방향 켜기,
  상태 대기 실패·중단·시간 제한.
- 수명: 처리 중 정지·클릭·동일/반대 방향 재시작, 느린 클릭 중단, 처리 종료 후 반복 간격,
  최대 시간, 외부 꺼짐·사용 불가 상태, 자동화 다시 불러오기와 HA 종료.
- 오류: boolean·NaN·무한대·누락 속성·뒤집힌 Kelvin 범위·범위 밖 HS 거부,
  실행 추적의 종료 사유, 서비스 오류 후 재시도 없음.

변경 없는 자동화는 HA의 다시 불러오기에서 기존 실행이 유지되므로,
`automation_reloaded` 이벤트가 명시적으로 중단하도록 구성했다.
`test_reload_cancels_rotation`에서 수정 전 추가 조명 호출을 재현하고 수정 후 중단을 확인했다.

## 독립 검토

`3fea9b3c91523fd1304c7f3bbcdc5417fcf6bd91`부터
`8303db18f7a78296aeb65631658a1dfbef369c09`까지의 변경을 별도 검토자가 읽기 전용으로
검토했다. Critical·Important·Minor 발견 사항은 없었고 병합 가능으로 판정했다.
서비스 처리 중 정지·반대 회전, 자동화 다시 불러오기, 잘못된 MQTT 보고,
시작 대기 시간 초과 시험 5개를 두 HA 버전에서 새로 실행해 모두 통과했다.

## 설치 단계의 확인

MQTT 입력은 E1744의 공개 동작 계약에 따른 합성 메시지다. 실제 노브의 무선 통신,
MQTT 패킷, 물리 조명 반응은 이 시험에 포함하지 않았다. 설치와 클릭 지정은
[사용 가이드](../../blueprints/automation/z2m_ikea_e1744_light_control/README.md)를 따른다.
