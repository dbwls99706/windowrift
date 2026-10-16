# WindowRift 한국어 가이드

WindowRift는 실행 중인 프로그램의 **보이는 화면 속 객체를 데스크톱 위로 꺼내는 시각적 실험 도구**이다. 선택한 창을 캡처하고 객체를 잘라낸 다음, 독립적인 투명 창으로 띄워 드래그하고 중력·창 경계 충돌을 적용한다.

**임의 게임 객체를 메모리에서 꺼내는 프로그램은 아니다.** 추출 대상은 화면 픽셀이다. 다만 번들 예제 게임 Rift Arcade는 별도 동의로 켠 로컬 핸드오프를 통해 원본 캐릭터를 일시적으로 숨기고 복귀시킬 수 있다. 이는 다른 게임에 적용되는 범용 기능이 아니다.

## 직접 조종하는 Play Mode

이제 자동 경로 시연과 별개로 **키보드로 객체를 직접 조종**할 수 있다.
\`windowrift\`에서 객체를 추출한 뒤 **Take control of latest actor**를 누른다.

- \`A\`·\`D\` 또는 좌우 방향키: 이동과 방향 전환
- \`Space\`·\`W\`·위쪽 방향키: 점프
- \`Shift\`: 달리기
- \`S\`+\`Space\` 또는 아래 방향키+\`Space\`: 창·주소창 발판 아래로 내려가기
- \`Esc\`: 조작 해제

조작은 WindowRift 제어판에 키보드 포커스가 있을 때만 적용한다.
Chrome에서 입력하는 내용을 수집하지 않고 원본 게임 코드를 변경하지 않는다.

## 실제 Chromium 검색·주소창 탈출 시연

![실제로 실행 중인 게임에서 Chromium 검색·주소창으로 객체가 이동하는 X11 데스크톱 녹화](media/omnibox-handoff.gif)

[원본 스크린샷](media/chrome-omnibox-actual.png)

가상 X11에서 직접 실행 중인 Rift Arcade와 Chromium을 캡처한 결과이다. Chrome UI를 흉내 낸 HTML이 아니고, 별도의 투명 X11 창을 Chrome의 **실제 주소창 위에 겹친 것**이다. 검색창에서 키보드로 문장을 입력해도 정상 동작한다. Chrome의 내부 UI를 변조하거나 게임 코드를 크롬 프로세스에 삽입하는 기능은 아니다.

Ubuntu X11에서 아래 순서로 실행하면 된다. 첫 번째, 두 번째 터미널에 동일한 임시 토큰을 지정한다.

```bash
export WINDOWRIFT_DEMO_TOKEN='change-this-local-demo-token'
# 터미널 1
python examples/rift_arcade.py --demo-handoff
# 터미널 2 (Chrome/Chromium 일반 창을 먼저 열어둘 것)
python examples/chrome_omnibox_demo.py --duration 0
```

게임은 실제로 동작하며, 핸드오프 활성화 시 원본 캐릭터를 숨겼다가 종료 시 복원한다. 포털 프로세스가 비정상 종료되면 게임이 제한시간 내 자동 복원한다. Chrome 창이 여러 개라면 `wmctrl -l`의 창 ID를 `--browser-id 0x...`로 지정한다. 다른 프로그램에서 시험하려면 `--source-title`과 `--crop x,y,w,h`로 소스와 영역을 지정하면 된다. 다만 다른 프로그램의 캐릭터를 제거하는 기능은 없다.

일반 WindowRift Qt 앱에서도 객체를 추출한 뒤 Chrome 창을 선택하고 **Into address bar**를 누를 수 있으며, **Release from Chrome**으로 다시 데스크톱에 내려놓을 수 있다. Windows에서 이 UI의 실기 테스트는 아직 진행되지 않았다.

## 기능

- Windows와 Linux X11에서 보이는 프로그램 창 선택 및 영역 캡처
- OpenCV GrabCut 배경 제거, 선택적 `rembg` AI 배경 제거, 사각형 캡처
- 데스크톱 위 투명 캐릭터 드래그·중력·반사·다른 창 위에 착지
- **Live pixels:** 원본 창의 선택 영역을 주기적으로 다시 캡처하여 고정된 마스크 내부 픽셀을 갱신한다. 선택적 **Track motion**은 주변 72픽셀 안에서 원본과 비슷한 패턴을 찾아 추적하지만, 빠른 이동이나 가림에 취약하다.
- **Chrome 주소창 오버레이:** 실제 브라우저 검색·주소창 위에 투명 캐릭터 창을 표시하고 브라우저 창 이동을 따라간다. 키 입력을 막지 않는다.
- Chrome 확장을 켜면 실제 DOM 요소의 CSS가 변화하고, `data-windowrift-target` 영역에는 `windowrift:impact` 이벤트가 발생한다.

## 설치 (Ubuntu 22.04, X11 기준)

로그인 화면에서 **Ubuntu on Xorg** 세션을 선택한다. Wayland와 macOS는 현재 지원하지 않는다.

```bash
sudo apt install xdotool
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
windowrift
```

Windows는 가상환경 활성화 후 같은 pip 설치 명령을 사용할 수 있다. AI 추출 기능은 다음 명령으로 별도 설치한다.

```bash
python -m pip install -e '.[ai]'
```

`rembg`가 필요한 모델을 처음 내려받을 수 있다. CPU에서 처리되므로 고해상도 이미지는 느릴 수 있다. 기본 GrabCut 모드에는 별도 모델이 필요 없다.

## 데스크톱 탈출 시연

1. 창 모드 게임이나 브라우저에 움직이는 객체를 표시한다. 원본 창은 **최대한 가리지 않는다**.
2. WindowRift에서 프로그램을 선택하고 추출 방식(GrabCut/AI/Rectangle)을 고른다.
3. 계속 움직이는 모습을 원하면 **Live pixels**를 체크한다. 이때 추출할 영역은 최대 512×512 픽셀로 제한한다. 가능하면 해당 영역 안에서 제자리 애니메이션을 하는 객체를 선택한다.
4. **Capture window**를 누르고 스크린샷에서 객체 주변을 사각형으로 지정한다.
5. 투명 객체가 나오면 **원본 선택 영역 밖으로 드래그**한다. WindowRift 객체 자체가 원본을 가리면 Live 모드는 자동으로 해당 프레임을 건너뛴다.
6. 객체를 다른 창 위에 떨어뜨려 중력과 충돌을 확인한다. 제거는 우클릭 더블클릭이다.

원본 창이 이동하면 Live 모드 캡처 영역은 그 창의 새 위치를 따른다. 원본 창이 크기 변경으로 선택 영역을 잃거나 화면 밖으로 나가면 기존 프레임을 유지한다. 다른 프로그램이 원본을 가리는 상황은 완벽하게 검출하지 못한다.

## 실제 웹페이지 상호작용 시연

1. Chrome의 `chrome://extensions`에서 개발자 모드를 활성화한다.
2. **압축해제된 확장 프로그램 로드**로 `browser-extension` 폴더를 선택한다.
3. 저장소 루트에서 `python -m http.server 8000`을 실행한다.
4. Chrome에서 `http://127.0.0.1:8000/examples/browser-lab.html`을 연다.
5. WindowRift의 **Copy session token**으로 토큰을 복사한다.
6. Chrome 확장 팝업에 토큰을 넣고 해당 탭에서 **Enable this tab**을 누른다.
7. WindowRift 객체를 페이지의 Crystal, Portal, Power Core 카드 위로 움직인다. 카드의 CSS 스타일이 바뀌고 **Rift impacts** 숫자가 증가한다.
8. **Reset page**를 눌러 원래 CSS로 복구하고 연결을 끊는다.

`Rift impacts` 카운터는 데모 페이지가 `windowrift:impact` 커스텀 이벤트에 명시적으로 반응한 결과이다. 임의 사이트의 DB나 게임 내부 상태를 마음대로 바꾸는 기능은 아니다.

## 테스트

```bash
python -m pip install -e '.[dev]' pytest-asyncio
pytest -q
python -m compileall -q src
node --test tests/js/*.test.cjs
```

GUI와 실제 게임, 다양한 디스플레이 배율에 대한 완전한 자동 테스트는 아직 없다. 기능은 Windows 및 Linux X11에서 직접 실기 확인해야 한다.

## 개발 범위

이미지 배경 제거, 실시간 소스 픽셀 샘플링, 데스크톱 물리, 명시적으로 연결한 웹페이지 DOM 이벤트까지 구현하였다. AI가 게임을 자동 개조하거나, 모든 응용프로그램 속 객체를 실제로 제거·복제하고 내부 상태를 동기화하는 것은 지원하지 않는다. 이러한 기능은 장기 연구 과제이다.

기본적으로 이미지는 외부 서버로 전송하지 않으며, 로컬 브리지는 `127.0.0.1`에서 세션 토큰을 요구한다. 선택적 AI 모델은 첫 설치 때 다운로드가 필요할 수 있다.

라이선스는 [MIT](../LICENSE)이다.


## v0.3.0 실제 게임 데모

[실제 X11 실행 화면](media/actual-x11-demo.png)에서는 직접 제작한 Rift Arcade 게임 창,
실제 캡처 이미지에서 분리한 별도 투명 객체 창, Chromium의 충돌 횟수 변경을 확인할 수 있다.
이 이미지는 Xvfb에서 실행한 실제 GUI 화면의 **크롭된 캡처**이며 합성 이미지가 아니다.
해당 시연은 환경상 PySide6를 실행할 수 없어 `examples/x11_proof.py` 검증 프로그램으로
수행했다. 주 애플리케이션의 Windows 및 Linux Qt GUI 통합 검증 결과로 간주하면 안 된다.

Rift Arcade를 실행하려면 `python examples/rift_arcade.py`를 사용한다. 화살표로
이동하고, 스페이스로 점프하며, R로 초기화할 수 있는 실제 게임이다. 별도 터미널에서
`windowrift`를 실행하고 Rift Arcade 창을 선택한 뒤 **Pixel art / flat background
color key**를 사용하면 어두운 단색 배경을 쉽게 제거할 수 있다.

새로운 **Track motion** 옵션은 Live pixels를 활성화한 경우 원래 선택한 객체를
기준으로 최대 72픽셀의 주변 영역에서 매번 객체를 다시 찾는다. 객체가 빠르게
움직이거나 가려지는 경우 추적을 보장하지 않으며 마지막 정상 프레임을 유지한다.

브라우저의 `examples/browser-lab.html`에서는 이제 확장 프로그램 설치 없이도
WindowRift 세션 토큰을 입력하여 **Connect local lab** 버튼으로 연결할 수 있다.
세션 토큰은 URL이나 디스크에 저장하지 않는다. 일반 웹페이지에는 기존 Chrome
확장 프로그램을 사용하는 방식이 필요하다.


## 실제 상용 게임: DOOM 셰어웨어 검증

[DOOM 원본 셰어웨어 실험 설명](DOOM_SHAREWARE.md)에서는 id Software의
DOOM 1.9 셰어웨어 데이터를 CI 실행 환경에서 별도로 받아 무결성을 검사한 뒤,
Chocolate Doom으로 게임을 실행하는 절차를 다룬다. 진짜 DOOM WAD에 포함된
`TROOA1` 몬스터 이미지를 읽어 Chrome의 실제 주소창 위에서 독립적인
X11 투명 창으로 표시한다. WAD 파일과 추출한 원본 게임 자산은 저장소에
포함하지 않는다.

이 검증은 **실제 상용 게임 실행과 게임 이미지 데이터 이용**을 목표로 하지만
게임 프로세스 내부 객체 이동·원본 캐릭터 삭제·범용 게임 모딩을
구현했다는 뜻은 아니다. CI 성공 로그와 이미지가 모두 있어야 성공한
실험으로 판단한다.
