# WindowRift 한국어 가이드

WindowRift는 실행 중인 프로그램의 **보이는 화면 속 객체를 데스크톱 위로 꺼내는 시각적 실험 도구**이다. 선택한 창을 캡처하고 객체를 잘라낸 다음, 독립적인 투명 창으로 띄워 드래그하고 중력·창 경계 충돌을 적용한다.

**실제 게임 객체를 메모리에서 꺼내거나 원본 게임에서 제거하는 프로그램은 아니다.** 추출 대상은 화면 픽셀이며, 내부 게임 상태나 원본 애니메이션 정보를 복사하는 것은 현재 범위 밖이다.

## 기능

- Windows와 Linux X11에서 보이는 프로그램 창 선택 및 영역 캡처
- OpenCV GrabCut 배경 제거, 선택적 `rembg` AI 배경 제거, 사각형 캡처
- 데스크톱 위 투명 캐릭터 드래그·중력·반사·다른 창 위에 착지
- **Live pixels:** 원본 창의 선택 영역을 주기적으로 다시 캡처하여 **고정된 마스크 내부 픽셀을 갱신**한다. 정지 이미지보다는 동적인 모습을 볼 수 있지만, 움직이는 캐릭터를 자동 추적하지는 않는다.
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
