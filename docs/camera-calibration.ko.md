# iPhone 카메라 캘리브레이션 (#5)

> English version [here](camera-calibration.md).

iPhone Xs Max 후면 카메라를 체커보드로 직접 캘리브레이션해 `sensor_msgs/CameraInfo`(REP 104)
필드(K, D, R, P)를 채운다. 공개된 iPhone 스펙값은 쓰지 않는다 — 이 절차로 산출한 값만 쓴다
(개별 기기/렌즈 편차, 캡처 앱의 실제 해상도·크롭이 스펙값과 다를 수 있기 때문).

## 준비물

- 체커보드 패턴(모니터에 띄우거나 인쇄) — 내부 코너 개수(가로×세로)와 정사각형 한 변의 실측
  길이(mm)를 정확히 알아야 한다. 인쇄한다면 프린터 배율로 크기가 틀어지지 않았는지 자로 재서
  확인할 것.
- iPhone Xs Max에서 iOS 캡처 앱(#4, `ios/`) 실행 — `docs/ios-app-setup.md` 참고. TX2/iproxy
  없이 같은 Wi-Fi에서 진행 가능하다.
- TX2(또는 같은 네트워크의 아무 리눅스 머신)에 `opencv-python`, `pyyaml`.

## 1. 촬영 (`capture_calibration_images.py`)

iPhone 앱을 켠 상태에서, iPhone의 IP(설정 → Wi-Fi → 연결된 네트워크 (i) 아이콘)로:

```bash
python3 scripts/capture_calibration_images.py <iPhone IP> 8765 \
    --out calib_images/ --count 20 --interval 2
```

`--interval`초마다 한 장씩 mono8 프레임을 PNG로 저장한다. 그 사이에 체커보드를:

- 화면 전체 영역(모서리 포함)을 골고루 채우도록 위치를 바꿔가며
- 카메라 정면뿐 아니라 여러 각도로 기울여서
- 가까이/멀리 거리를 바꿔가며

움직여야 한다 — 코너 근처와 다양한 각도 데이터가 없으면 왜곡계수(특히 k1, k2)가 부정확해진다.
최소 10~15장, 가능하면 20장 이상 권장.

## 2. 캘리브레이션 (`calibrate_camera.py`)

```bash
python3 scripts/calibrate_camera.py calib_images/ \
    --board-cols <내부 코너 가로 개수> --board-rows <내부 코너 세로 개수> \
    --square-size-mm <정사각형 한 변 길이> \
    --out calibration/iphone_xs_max_back_camera.yaml
```

- `--board-cols`/`--board-rows`는 **내부 코너** 개수다 (예: 10x7 정사각형 체커보드면 내부 코너는
  9x6).
- `cv2.findChessboardCorners` + `cv2.cornerSubPix`로 서브픽셀 코너를 찾고
  `cv2.calibrateCamera`로 내부 파라미터와 왜곡계수(k1, k2, p1, p2, k3)를 산출한다.
- 코너를 못 찾은 이미지는 경고와 함께 자동으로 건너뛴다 — 스크립트 출력에서 몇 장이 실제로
  쓰였는지 확인할 것.
- RMS 재투영 오차가 `--max-rms-error-px`(기본 1.0px)를 넘으면 오류로 종료한다. 넘을 경우 사진을
  더 찍거나(각도/거리 다양성 부족이 흔한 원인), `--square-size-mm` 실측값을 다시 확인할 것.

## 3. 출력

`--out` 경로에 YAML로 저장되며, 필드가 `sensor_msgs/CameraInfo`에 그대로 대입 가능한 이름으로
되어 있다:

```yaml
width: 640
height: 480
distortion_model: plumb_bob
D: [k1, k2, p1, p2, k3]
K: [fx, 0, cx, 0, fy, cy, 0, 0, 1]
R: [1, 0, 0, 0, 1, 0, 0, 0, 1]        # 단안이므로 단위 행렬
P: [fx, 0, cx, 0, 0, fy, cy, 0, 0, 0, 1, 0]
reprojection_error:
  rms_px: ...
  mean_per_image_px: [...]
calibration_images: [...]            # 실제로 코너 검출에 쓰인 이미지 목록
```

브리지 노드(#6)는 이 YAML을 읽어 `K`/`D`/`R`/`P`/`width`/`height`/`distortion_model`을
`CameraInfo` 메시지 필드에 그대로 대입하면 된다 (`docs/ros2-topic-contract.md`의
`/camera/camera_info` 참고 — `header.frame_id`/`header.stamp`는 그 계약에 따라 브리지 노드가
채운다).

## 재현 시 주의

- 캡처 앱의 해상도가 바뀌면(코드 변경 등) 캘리브레이션을 다시 해야 한다 — `width`/`height`가
  실제 스트리밍 해상도와 다르면 `K`/`D`가 무효하다.
- 렌즈를 만지거나 기기가 바뀌면(다른 iPhone Xs Max 개체 포함) 재캘리브레이션 필요 — 개별 기기
  편차가 있을 수 있다.
