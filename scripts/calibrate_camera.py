#!/usr/bin/env python3
"""OpenCV 체커보드 캘리브레이션으로 iPhone Xs Max 후면 카메라 내부 파라미터를 산출한다 (#5).

capture_calibration_images.py로 모은 체커보드 이미지 디렉터리를 입력받아
cv2.findChessboardCorners + cv2.calibrateCamera로 내부 파라미터를 계산하고,
sensor_msgs/CameraInfo 필드(K, D, R, P)에 바로 대입 가능한 형태로 YAML에 저장한다.
공개된 iPhone 스펙값은 쓰지 않는다 — 이 스크립트가 산출한 값만 사용한다.

사용법:
    python3 scripts/calibrate_camera.py calib_images/ \\
        --board-cols 9 --board-rows 6 --square-size-mm 25.0 \\
        --out calibration/iphone_xs_max_back_camera.yaml
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)


def find_corners(image_paths, board_size):
    """(objpoints, imgpoints, image_size, used_files) 반환. 코너를 못 찾은 이미지는 건너뛴다."""
    objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0 : board_size[0], 0 : board_size[1]].T.reshape(-1, 2)

    objpoints = []
    imgpoints = []
    used_files = []
    image_size = None

    for path in image_paths:
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"경고: 이미지를 읽을 수 없음, 건너뜀: {path}", file=sys.stderr)
            continue
        if image_size is None:
            image_size = (img.shape[1], img.shape[0])  # (width, height)
        elif (img.shape[1], img.shape[0]) != image_size:
            print(f"경고: 해상도가 다름({img.shape[1]}x{img.shape[0]}), 건너뜀: {path}", file=sys.stderr)
            continue

        found, corners = cv2.findChessboardCorners(img, board_size)
        if not found:
            print(f"경고: 체커보드를 못 찾음, 건너뜀: {path}", file=sys.stderr)
            continue

        corners = cv2.cornerSubPix(img, corners, (11, 11), (-1, -1), CRITERIA)
        objpoints.append(objp)
        imgpoints.append(corners)
        used_files.append(str(path))

    return objpoints, imgpoints, image_size, used_files


def calibrate(objpoints, imgpoints, image_size, square_size_mm):
    scaled_objpoints = [op * square_size_mm for op in objpoints]
    rms, k, d, rvecs, tvecs = cv2.calibrateCamera(scaled_objpoints, imgpoints, image_size, None, None)

    per_image_errors = []
    for i in range(len(scaled_objpoints)):
        projected, _ = cv2.projectPoints(scaled_objpoints[i], rvecs[i], tvecs[i], k, d)
        error = cv2.norm(imgpoints[i], projected, cv2.NORM_L2) / len(projected)
        per_image_errors.append(float(error))

    return rms, k, d, per_image_errors


def to_camera_info_dict(k, d, image_size, rms, per_image_errors, used_files):
    width, height = image_size
    fx, fy = k[0, 0], k[1, 1]
    cx, cy = k[0, 2], k[1, 2]
    # OpenCV는 기본 5개 왜곡계수(k1,k2,p1,p2,k3)를 낸다 — CameraInfo의 plumb_bob과 그대로 일치.
    d_flat = d.flatten().tolist()
    if len(d_flat) < 5:
        d_flat += [0.0] * (5 - len(d_flat))

    return {
        "width": int(width),
        "height": int(height),
        "distortion_model": "plumb_bob",
        # sensor_msgs/CameraInfo.d
        "D": d_flat[:5],
        # sensor_msgs/CameraInfo.k (row-major 3x3)
        "K": [float(fx), 0.0, float(cx), 0.0, float(fy), float(cy), 0.0, 0.0, 1.0],
        # 스테레오/외부 리그가 아니므로 단위 행렬 (REP 104)
        "R": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        # 단안이므로 P의 좌측 3x3은 K와 동일, 마지막 컬럼은 0
        "P": [float(fx), 0.0, float(cx), 0.0, 0.0, float(fy), float(cy), 0.0, 0.0, 0.0, 1.0, 0.0],
        "reprojection_error": {
            "rms_px": float(rms),
            "mean_per_image_px": per_image_errors,
        },
        "calibration_images": used_files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image_dir", type=Path, help="체커보드 이미지가 있는 디렉터리 (png/jpg)")
    parser.add_argument("--board-cols", type=int, required=True, help="체커보드 내부 코너 개수 (가로)")
    parser.add_argument("--board-rows", type=int, required=True, help="체커보드 내부 코너 개수 (세로)")
    parser.add_argument("--square-size-mm", type=float, required=True, help="체커보드 정사각형 한 변 길이(mm)")
    parser.add_argument("--out", type=Path, required=True, help="출력 YAML 경로")
    parser.add_argument(
        "--max-rms-error-px",
        type=float,
        default=1.0,
        help="이 값을 넘는 RMS 재투영 오차(px)는 실패로 취급 (기본 1.0px)",
    )
    args = parser.parse_args()

    image_paths = sorted(p for p in args.image_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    if not image_paths:
        print(f"오류: {args.image_dir}에 이미지가 없음", file=sys.stderr)
        return 1

    board_size = (args.board_cols, args.board_rows)
    objpoints, imgpoints, image_size, used_files = find_corners(image_paths, board_size)

    print(f"{len(image_paths)}장 중 {len(used_files)}장에서 체커보드 코너를 찾음.")
    if len(used_files) < 10:
        print(
            f"경고: 캘리브레이션에 쓸 이미지가 {len(used_files)}장뿐입니다. "
            "다양한 각도/거리/위치로 최소 10~15장을 권장합니다.",
            file=sys.stderr,
        )
    if len(used_files) < 4:
        print("오류: cv2.calibrateCamera에 최소 4장이 필요합니다.", file=sys.stderr)
        return 1

    rms, k, d, per_image_errors = calibrate(objpoints, imgpoints, image_size, args.square_size_mm)
    print(f"RMS 재투영 오차: {rms:.4f}px")
    print(f"이미지별 평균 오차(px): {[round(e, 4) for e in per_image_errors]}")

    result = to_camera_info_dict(k, d, image_size, rms, per_image_errors, used_files)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        yaml.safe_dump(result, f, default_flow_style=False)
    print(f"\nCameraInfo 파라미터를 저장함: {args.out}")

    if rms > args.max_rms_error_px:
        print(
            f"오류: RMS 재투영 오차 {rms:.4f}px가 허용치 {args.max_rms_error_px}px를 초과함. "
            "이미지를 더 찍거나 체커보드 치수를 다시 확인하세요.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
