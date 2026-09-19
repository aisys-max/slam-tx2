# iPhone camera calibration (#5)

> 한국어 버전은 [여기](camera-calibration.ko.md)에 있습니다.

Calibrates the iPhone Xs Max's rear camera directly with a checkerboard to fill in the
`sensor_msgs/CameraInfo` (REP 104) fields (K, D, R, P). Published iPhone spec values are not
used — only values produced by this procedure (per-device/lens variance, and the capture app's
actual resolution/crop, can differ from spec values).

## What you need

- A checkerboard pattern (displayed on a monitor or printed) — you need to know the exact number
  of internal corners (columns × rows) and the measured side length (mm) of one square. If
  printed, measure with a ruler to confirm the printer's scaling didn't distort the size.
- The iOS capture app (#4, `ios/`) running on the iPhone Xs Max — see `docs/ios-app-setup.md`.
  Can be done on the same Wi-Fi without the TX2/iproxy.
- `opencv-python`, `pyyaml` on the TX2 (or any Linux machine on the same network).

## 1. Capture (`capture_calibration_images.py`)

With the iPhone app running, using the iPhone's IP (Settings → Wi-Fi → connected network → the
(i) icon):

```bash
python3 scripts/capture_calibration_images.py <iPhone IP> 8765 \
    --out calib_images/ --count 20 --interval 2
```

Saves one mono8 frame as a PNG every `--interval` seconds. During that time, move the
checkerboard:

- across the whole frame (including the corners), varying its position
- tilted at various angles, not just facing the camera straight-on
- at varying distances, near and far

Without corner-area and varied-angle data, the distortion coefficients (especially k1, k2) come
out inaccurate. At least 10-15 shots, ideally 20+.

## 2. Calibrate (`calibrate_camera.py`)

```bash
python3 scripts/calibrate_camera.py calib_images/ \
    --board-cols <number of internal corners, horizontal> --board-rows <number of internal corners, vertical> \
    --square-size-mm <side length of one square> \
    --out calibration/iphone_xs_max_back_camera.yaml
```

- `--board-cols`/`--board-rows` are counts of **internal corners** (e.g. a 10x7-square
  checkerboard has 9x6 internal corners).
- Finds sub-pixel corners with `cv2.findChessboardCorners` + `cv2.cornerSubPix`, then computes
  intrinsics and distortion coefficients (k1, k2, p1, p2, k3) with `cv2.calibrateCamera`.
- Images where corners couldn't be found are skipped automatically with a warning — check the
  script's output to see how many images were actually used.
- Exits with an error if the RMS reprojection error exceeds `--max-rms-error-px` (default
  1.0px). If it does, take more photos (insufficient angle/distance variety is a common cause)
  or double-check the measured `--square-size-mm` value.

## 3. Output

Saved as YAML at the `--out` path, with field names that can be assigned directly into
`sensor_msgs/CameraInfo`:

```yaml
width: 640
height: 480
distortion_model: plumb_bob
D: [k1, k2, p1, p2, k3]
K: [fx, 0, cx, 0, fy, cy, 0, 0, 1]
R: [1, 0, 0, 0, 1, 0, 0, 0, 1]        # identity matrix, since this is monocular
P: [fx, 0, cx, 0, 0, fy, cy, 0, 0, 0, 1, 0]
reprojection_error:
  rms_px: ...
  mean_per_image_px: [...]
calibration_images: [...]            # list of images actually used for corner detection
```

The bridge node (#6) reads this YAML and assigns `K`/`D`/`R`/`P`/`width`/`height`/
`distortion_model` directly into the `CameraInfo` message fields (see `/camera/camera_info` in
`docs/ros2-topic-contract.md` — `header.frame_id`/`header.stamp` are filled by the bridge node
per that contract).

## Caveats for reproducing this

- If the capture app's resolution changes (e.g. a code change), you must recalibrate — if
  `width`/`height` don't match the actual streaming resolution, `K`/`D` are invalid.
- If the lens is touched or the device changes (including swapping to a different physical
  iPhone Xs Max unit), recalibration is needed — there can be per-device variance.
