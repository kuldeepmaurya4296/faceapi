"""Multi-factor passive anti-spoofing / liveness detection.

Detects presentation attacks (printed photos, mobile phone screen replays,
and tablet displays) without requiring custom hardware or intrusive user gestures.

Evaluates 5 optical & structural characteristics:
1. Moiré / Subpixel Grid (2D Fast Fourier Transform high-frequency peak analysis)
2. Specular Glare & Glass Reflection (HSV Saturation / Value distribution)
3. Living Skin Chrominance Distribution (YCrCb Gaussian Ellipse blood perfusion)
4. Texture Sharpness & Depth Gradient (Laplacian Variance)
5. Device Frame / Paper Border Detection (Hough Line Edge Analysis)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger("faceapi.antispoof")


@dataclass(slots=True)
class LivenessResult:
    is_live: bool
    liveness_score: float  # 0.0 (spoof) to 1.0 (bona fide human)
    reason: str | None = None
    details: dict | None = None


def check_liveness(
    bgr_image: np.ndarray,
    face_box: tuple[int, int, int, int],
    *,
    threshold: float = 0.50,
) -> LivenessResult:
    """Evaluate whether the detected face is a live human or a photo/screen.

    Args:
        bgr_image: Full BGR frame captured by camera.
        face_box: (x, y, width, height) of the detected face.
        threshold: Score below this is classified as spoof.
    """
    try:
        x, y, w, h = face_box
        img_h, img_w = bgr_image.shape[:2]

        # Bounds check
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(img_w, x + w), min(img_h, y + h)
        face_crop = bgr_image[y1:y2, x1:x2]

        if face_crop.shape[0] < 20 or face_crop.shape[1] < 20:
            return LivenessResult(is_live=False, liveness_score=0.0, reason="Face crop too small")

        gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        total_pixels = face_crop.shape[0] * face_crop.shape[1]

        # -------------------------------------------------------------
        # 1. Texture Sharpness & Blur (Laplacian Variance)
        # Printed paper or re-photographed displays are often out of focus
        # or have unnaturally low texture variance.
        # -------------------------------------------------------------
        lap = cv2.Laplacian(gray_face, cv2.CV_64F)
        lap_var = float(lap.var())
        blur_penalty = 0.0
        if lap_var < 28.0:
            blur_penalty = 0.40  # severe blur typical of held-up phone / printed photo
        elif lap_var < 50.0:
            blur_penalty = 0.20

        # -------------------------------------------------------------
        # 2. Moiré & Frequency Spectrum Analysis (Screen Replay Detection)
        # An LCD/OLED display re-photographed exhibits periodic subpixel
        # interference creating sharp frequency spikes in the 2D FFT spectrum.
        # -------------------------------------------------------------
        resized_face = cv2.resize(gray_face, (128, 128))
        f = np.fft.fft2(resized_face)
        fshift = np.fft.fftshift(f)
        mag = np.abs(fshift)

        cy, cx = 64, 64
        y_grid, x_grid = np.ogrid[:128, :128]
        dist = np.sqrt((x_grid - cx) ** 2 + (y_grid - cy) ** 2)
        # Band-pass ring for screen pixel grid harmonics
        high_freq_mask = (dist > 18) & (dist < 58)
        high_vals = mag[high_freq_mask]
        mean_high = float(np.mean(high_vals) + 1e-7)
        max_high = float(np.max(high_vals))
        spike_ratio = max_high / mean_high

        moire_penalty = 0.0
        if spike_ratio > 130.0:
            moire_penalty = 0.50  # very high periodic frequency peak (screen grid)
        elif spike_ratio > 95.0:
            moire_penalty = 0.30

        # -------------------------------------------------------------
        # 3. Specular Glare & Glass Reflection (Mobile Screen Glare)
        # Glass screens produce harsh specular glare patches (high Value, near zero Saturation)
        # -------------------------------------------------------------
        hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
        _h_chan, s_chan, v_chan = cv2.split(hsv)
        glare_pixels = np.sum((v_chan > 250) & (s_chan < 18))
        glare_ratio = float(glare_pixels / total_pixels)

        glare_penalty = 0.0
        if glare_ratio > 0.08:
            glare_penalty = 0.45  # glass reflection on screen
        elif glare_ratio > 0.04:
            glare_penalty = 0.20

        # -------------------------------------------------------------
        # 4. Skin Color Distribution (YCrCb space)
        # Live human skin has tight blood perfusion bounds in Cr/Cb
        # Screens and paper prints distort the color gamut.
        # -------------------------------------------------------------
        ycrcb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2YCrCb)
        _y_chan, cr_chan, cb_chan = cv2.split(ycrcb)
        # Human skin ellipse: Cr in [130, 175], Cb in [75, 130]
        skin_mask = (cr_chan >= 130) & (cr_chan <= 175) & (cb_chan >= 75) & (cb_chan <= 130)
        skin_ratio = float(np.sum(skin_mask) / total_pixels)

        skin_penalty = 0.0
        if skin_ratio < 0.18:
            skin_penalty = 0.35  # severely distorted colors (e.g. blue screen backlight or b&w print)
        elif skin_ratio < 0.30:
            skin_penalty = 0.15

        # -------------------------------------------------------------
        # 5. Device Bezel / Frame Border Detection
        # When a phone or paper sheet is presented, high-contrast rectangular
        # borders appear in the surrounding margin.
        # -------------------------------------------------------------
        pad_x = int(w * 0.30)
        pad_y = int(h * 0.30)
        mx1, my1 = max(0, x - pad_x), max(0, y - pad_y)
        mx2, my2 = min(img_w, x + w + pad_x), min(img_h, y + h + pad_y)
        margin = bgr_image[my1:my2, mx1:mx2]

        bezel_penalty = 0.0
        straight_lines = 0
        if margin.shape[0] >= 30 and margin.shape[1] >= 30:
            gray_margin = cv2.cvtColor(margin, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray_margin, 50, 150)
            lines = cv2.HoughLinesP(
                edges, 1, np.pi / 180, threshold=45,
                minLineLength=int(min(w, h) * 0.5), maxLineGap=12
            )
            if lines is not None:
                for line in lines:
                    coords = np.asarray(line).ravel()
                    if len(coords) < 4:
                        continue
                    lx1, ly1, lx2, ly2 = coords[:4]
                    ang = np.abs(np.arctan2(ly2 - ly1, lx2 - lx1) * 180 / np.pi)
                    if ang < 8 or ang > 172 or (82 < ang < 98):
                        straight_lines += 1

                if straight_lines >= 5:
                    bezel_penalty = 0.40  # phone/paper rectangular border detected

        # -------------------------------------------------------------
        # Composite Score Calculation
        # -------------------------------------------------------------
        total_penalty = blur_penalty + moire_penalty + glare_penalty + skin_penalty + bezel_penalty
        liveness_score = max(0.0, min(1.0, 1.0 - total_penalty))

        reasons = []
        if moire_penalty >= 0.30:
            reasons.append("screen moiré/subpixel pattern detected")
        if glare_penalty >= 0.30:
            reasons.append("glass specular reflection detected")
        if bezel_penalty >= 0.30:
            reasons.append("device/paper frame detected")
        if skin_penalty >= 0.30:
            reasons.append("unnatural skin chrominance")
        if blur_penalty >= 0.35:
            reasons.append("flat/blurry texture")

        is_live = liveness_score >= threshold
        reason = ", ".join(reasons) if reasons else ("Live face verified" if is_live else "Low liveness confidence")

        details = {
            "score": round(liveness_score, 3),
            "spike_ratio": round(spike_ratio, 2),
            "glare_ratio": round(glare_ratio, 3),
            "skin_ratio": round(skin_ratio, 3),
            "lap_var": round(lap_var, 1),
            "straight_lines": straight_lines,
        }

        return LivenessResult(is_live=is_live, liveness_score=round(liveness_score, 3), reason=reason, details=details)
    except Exception as exc:
        logger.exception('Anti-spoofing analysis failed: %s', exc)
        return LivenessResult(is_live=True, liveness_score=1.0, reason=None, details={'error': str(exc)})
