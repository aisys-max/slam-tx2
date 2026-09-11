# EuRoC 데이터셋 기반 SLAM 노드 검증 (#3)

`scripts/run_euroc_validation.sh`로 EuRoC V1_01_easy를 재생해 SLAM 노드(`orbslam3` mono-inertial)를 검증한 기록.

## 데이터셋 확보

원본 ETH 서버(`robotics.ethz.ch`)가 이 TX2 네트워크에서 연결되지 않고(타임아웃), ETH Research Collection 페이지도 500 에러를 반환하며, 커뮤니티 rosbag2 미러(OpenVINS가 관리하는 Google Drive 링크)도 접근이 안 됐다(할당량 소진으로 추정). 최종적으로 사용자가 다른 경로로 직접 받은 표준 EuRoC ASL 포맷 zip(`mav0/cam0`, `mav0/imu0`, `mav0/state_groundtruth_estimate0` 등)을 받아 진행했다.

**필요한 입력**: `<V1_01_easy>/mav0/` 디렉터리(zip 압축 해제됨) — 자동 다운로드는 이번 범위에서 다루지 않는다.

## rosbag2 변환

이 TX2의 ROS2 Foxy 빌드에는 `rosbag2_py`(파이썬 바인딩)가 없다 — Foxy 시점엔 아직 추가되지 않은 패키지다. `scripts/euroc_to_rosbag2.py`가 `ros2 bag record`로 만든 실제 bag을 열어 확인한 sqlite3 스토리지 스키마(`topics`/`messages` 테이블)를 그대로 직접 써서 rosbag2를 만든다. `ros2 bag info`로 정상 인식되는 것을 확인했다.

생성되는 토픽은 프로젝트 표준 계약([docs/ros2-topic-contract.md](ros2-topic-contract.md))을 따른다: `/camera/image_raw`, `/camera/camera_info`(cam0/sensor.yaml의 pinhole+radtan 캘리브레이션), `/imu`.

## `orbslam3` mono-inertial 노드 신규 작성

`zang09/ORB_SLAM3_ROS2`(#2에서 fork)에는 mono(non-inertial), stereo, stereo-inertial만 있고 mono-inertial이 없어서, stereo-inertial의 IMU 버퍼링/동기화 패턴을 본떠 새로 작성했다 (`aisys-max/ORB_SLAM3_ROS2` 커밋 참고). 개발 중 발견/수정한 문제:

- `Thirdparty/Sophus` include 경로 누락 → 컴파일 실패 (다른 노드들과 같은 문제, #2에서도 겪음)
- **종료 시 행(hang)**: `SyncWithImu()`가 무조건 `while(1)`이라 소멸자의 `syncThread_->join()`이 SIGINT 후에도 영원히 멈췄다 — bag 재생이 끝나고 실제로 노드가 안 죽는 것을 확인한 뒤 `std::atomic<bool>` 정지 플래그를 추가해 고쳤다.
- 헤드리스 실행을 위해 Pangolin 뷰어(`visualization`)를 꺼서 X11 없이도 동작하게 했다 — 이 TX2엔 DISPLAY가 설정되어 있지 않다.

## 재생 속도가 정확도에 미친 영향 (중요)

처음에 `--rate 1.0`(실시간)으로 재생했을 때:
- `Fail to track local map!`가 반복적으로 발생, 맵 리셋 여러 번
- **ATE RMSE 1.18m** — 참고 문헌 수준(수 cm)과 1~1.5자릿수 차이, 기준 미달

원인으로 의심한 것: TX2가 20Hz 실시간 처리를 못 따라가면, `GrabImage()`의 단일 슬롯 버퍼(새 프레임이 오면 처리 안 된 이전 프레임을 버림)가 프레임을 조용히 드롭하고, 이게 궤적 품질을 떨어뜨린다는 가설.

`--rate 0.3`으로 재생 속도를 늦추자:
- `Fail to track local map!` 0회, VIBA 1/2(IMU 초기화) 정상 완료, 맵 리셋 없음
- **ATE RMSE 0.093m** — 참고 문헌 수준과 같은 자릿수, 기준 통과

**결론**: TX2에서 이 노드를 실시간(1.0배속)으로 신뢰할 만큼 처리하려면 별도의 성능 최적화가 필요하다 — 이번 티켓 범위 밖이다. 오프라인 검증(이 스크립트가 하는 일)은 재생 속도를 낮춰서 처리 여유를 주는 방식으로 우회했다. 실제 iPhone 라이브 캡처(#6/#7)에서는 TX2가 실시간으로 처리해야 하므로, 이 한계를 염두에 두고 프레임레이트/해상도/ORB feature 수 등을 조정해야 할 수 있다 — 별도 이슈로 남길 가치가 있다.

## 결과

- `bash scripts/run_euroc_validation.sh <mav0 dir> <출력 디렉터리> 0.3` 로 처음부터 재현 확인 완료 (exit 0)
- ATE RMSE 0.093~0.094m (두 번 실행 결과 거의 동일) — 참고 문헌이 보고하는 EuRoC V1_01_easy VIO 수준과 같은 자릿수
- 궤적(`KeyFrameTrajectory.txt`, TUM 포맷)이 크래시 없이 저장됨
- ATE 평가는 TUM 벤치마크 표준 절차(Sturm et al. 2012)를 직접 구현 (`scripts/evaluate_ate.py`) — `evo` 패키지가 이 TX2의 Python 3.6과 의존성이 맞지 않아 설치가 안 됐다 (numpy 최신 버전을 요구, py3.6 미지원)
