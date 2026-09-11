#!/usr/bin/env bash
# #3 EuRoC 데이터셋 기반 SLAM 노드 검증: EuRoC V1_01_easy(ASL 포맷) -> rosbag2 변환 -> mono-inertial
# 노드로 재생 -> 궤적 저장 -> ATE 평가까지 한 번에 돌린다.
#
# 전제조건: scripts/setup_tx2.sh가 이미 실행되어 ROS2 Foxy/ORB-SLAM3/orbslam3 패키지가
# /mnt/ssd에 빌드되어 있을 것. EuRoC V1_01_easy는 ASL 포맷(zip 압축 해제된 mav0/ 디렉터리)으로
# 준비되어 있어야 한다 - docs/euroc-validation.md 참고 (원본 ETH 서버가 이 네트워크에서
# 접근되지 않아 자동 다운로드 스크립트는 없다).
#
# 사용법:
#   bash scripts/run_euroc_validation.sh <EuRoC V1_01_easy mav0 디렉터리> <출력 디렉터리> [재생 속도]
#
# 재생 속도는 기본 0.3 - TX2가 20Hz 실시간 처리를 못 따라가면 이미지 버퍼가 처리 못 한 프레임을
# 조용히 버려서 정확도가 크게 떨어진다(docs/euroc-validation.md 참고). --rate 1.0으로 처음
# 검증했을 때 ATE RMSE 1.18m, --rate 0.3으로는 0.094m이 나왔다.

set -euo pipefail

MAV0_DIR="${1:?Usage: $0 <mav0 dir> <output dir> [rate]}"
OUT_DIR="${2:?Usage: $0 <mav0 dir> <output dir> [rate]}"
RATE="${3:-0.3}"

ROS2_WS=/mnt/ssd/ros2_foxy
ORB_SLAM3_DIR=/mnt/ssd/orb_slam3_stack/ORB_SLAM3
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source_ros2_setup() {
  set +u
  source "$ROS2_WS/install/setup.bash"
  set -u
}

mkdir -p "$OUT_DIR"
source_ros2_setup
export ROS_PYTHON_VERSION=3

BAG_DIR="$OUT_DIR/rosbag2"
if [ ! -d "$BAG_DIR" ]; then
  echo "== EuRoC -> rosbag2 변환 =="
  python3 "$REPO_DIR/scripts/euroc_to_rosbag2.py" "$MAV0_DIR" "$BAG_DIR"
else
  echo "== rosbag2가 이미 있음, 변환 건너뜀: $BAG_DIR =="
fi

GT_TUM="$OUT_DIR/groundtruth_tum.txt"
python3 "$REPO_DIR/scripts/groundtruth_to_tum.py" \
  "$MAV0_DIR/state_groundtruth_estimate0/data.csv" "$GT_TUM"

echo "== mono-inertial 노드 시작 =="
cd "$OUT_DIR"
ros2 run orbslam3 mono-inertial \
  "$ORB_SLAM3_DIR/Vocabulary/ORBvoc.txt" \
  "$ROS2_WS/src/slam-tx2/orbslam3/config/monocular-inertial/EuRoC.yaml" \
  > "$OUT_DIR/node.log" 2>&1 &
NODE_PID=$!

# vocabulary(145MB) 로딩에 시간이 걸리므로 준비될 때까지 기다린다.
until grep -qE "There are 1 cameras|ERROR|Segmentation" "$OUT_DIR/node.log" 2>/dev/null; do
  if ! kill -0 "$NODE_PID" 2>/dev/null; then
    echo "노드가 시작 중 종료됨 - node.log 확인" >&2
    exit 1
  fi
  sleep 3
done

echo "== rosbag2 재생 (rate=$RATE) =="
ros2 bag play "$BAG_DIR" --rate "$RATE" > "$OUT_DIR/bag_play.log" 2>&1

echo "== 재생 종료, 노드 정상 종료(SIGINT) 대기 =="
kill -INT "$NODE_PID"
CHILD_PID=""
for _ in $(seq 1 10); do
  CHILD_PID=$(pgrep -f "orbslam3/lib/orbslam3/mono-inertial" || true)
  [ -n "$CHILD_PID" ] && break
  sleep 1
done
if [ -n "$CHILD_PID" ]; then
  kill -INT "$CHILD_PID" 2>/dev/null || true
  while kill -0 "$CHILD_PID" 2>/dev/null; do sleep 2; done
fi

TRAJ="$OUT_DIR/KeyFrameTrajectory.txt"
if [ ! -f "$TRAJ" ]; then
  echo "궤적 파일이 생성되지 않음: $TRAJ" >&2
  exit 1
fi

echo "== ATE 평가 =="
python3 "$REPO_DIR/scripts/evaluate_ate.py" "$TRAJ" "$GT_TUM"
