# 세션 타임스탬프는 iPhone 캡처 시각 기준

> English version [here](0001-timestamp-basis.md).

USB 전송 지연이 일정하지 않기 때문에, TX2가 데이터를 수신한 시각을 세션의 타임스탬프 기준으로 삼으면 카메라-IMU 간 상대 타이밍이 흔들려 visual-inertial 초기화/정합이 깨질 수 있다. 따라서 세션(Session)의 모든 프레임과 IMU 샘플 타임스탬프는 iPhone의 모노토닉 클럭 기준 캡처 시각을 사용하고, TX2 수신 시각은 사용하지 않는다.
