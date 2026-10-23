import os
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import cv2

from app.pipeline.schema import QualityCheckResult

class ImageQualityProcessor:
    # Calibrated thresholds based on mobile phone camera prescription benchmarks
    BLUR_THRESHOLD = 70.0        # Laplacian variance
    DARK_THRESHOLD = 50.0        # Mean grayscale brightness (0-255)
    GLARE_SHARE_THRESHOLD = 0.10 # Fraction of pixels >= 252 (washed out white flash)

    def analyze_quality(self, image_bgr: np.ndarray) -> QualityCheckResult:
        """
        Inspects image for blur, darkness, and flash glare.
        Returns a QualityCheckResult with specific retake guidance if rejected.
        """
        if image_bgr is None or image_bgr.size == 0:
            return QualityCheckResult(
                passed=False,
                is_blurry=True,
                blur_score=0.0,
                is_dark=True,
                mean_brightness=0.0,
                has_glare=False,
                glare_share=0.0,
                message="Invalid or empty image file uploaded. Please retake photo."
            )

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        
        # 1. Blur check via Laplacian variance
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_blurry = laplacian_var < self.BLUR_THRESHOLD
        
        # 2. Dark check via mean brightness
        mean_brightness = float(np.mean(gray))
        is_dark = mean_brightness < self.DARK_THRESHOLD
        
        # 3. Glare check via overexposed pixel ratio
        total_pixels = gray.size
        overexposed_count = int(np.sum(gray >= 252))
        glare_share = float(overexposed_count / total_pixels)
        has_glare = glare_share > self.GLARE_SHARE_THRESHOLD

        messages = []
        if is_blurry:
            messages.append(f"Image is blurry (focus score: {laplacian_var:.1f}). Please hold phone steady and retake.")
        if is_dark:
            messages.append(f"Lighting is too dim (brightness: {mean_brightness:.1f}/255). Turn on room lights or flash.")
        if has_glare:
            messages.append(f"Direct flash glare detected ({glare_share*100:.1f}% washed out). Tilt phone slightly to reduce reflection.")

        passed = not (is_blurry or is_dark or has_glare)
        final_msg = "Image quality passed all checks." if passed else " ".join(messages)

        return QualityCheckResult(
            passed=passed,
            is_blurry=is_blurry,
            blur_score=round(laplacian_var, 2),
            is_dark=is_dark,
            mean_brightness=round(mean_brightness, 2),
            has_glare=has_glare,
            glare_share=round(glare_share, 4),
            message=final_msg
        )

    def deskew(self, image_bgr: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Detects text skew angle and straightens the image.
        """
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        # Invert: text should be white, paper background black
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) < 100:
            return image_bgr, 0.0

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        elif angle > 45:
            angle = 90 - angle
        else:
            angle = -angle

        # Only deskew if noticeable tilt (< 35 degrees)
        if abs(angle) > 0.5 and abs(angle) < 35.0:
            (h, w) = image_bgr.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(image_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            return rotated, round(angle, 2)

        return image_bgr, 0.0

    def auto_orient_and_deskew(self, image_bgr: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Detects if photo was taken in landscape mode for a portrait pad (w > h * 1.15)
        and rotates 90 degrees clockwise, then applies subtle deskewing.
        """
        h, w = image_bgr.shape[:2]
        total_angle = 0.0
        oriented = image_bgr

        if w > h * 1.15:
            oriented = cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE)
            total_angle += 90.0

        deskewed, d_angle = self.deskew(oriented)
        total_angle += d_angle
        return deskewed, round(total_angle, 2)

    def segment_lines(self, image_bgr: np.ndarray, output_dir: Path, prefix: str) -> List[Tuple[str, List[int]]]:
        """
        Cuts prescription image into individual horizontal line crops.
        Uses adaptive Gaussian thresholding, horizontal morphological closing,
        and vertical line clustering to handle real mobile photos with shadows/margins.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

        # Adaptive thresholding to isolate ink despite non-uniform lighting
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10)

        # Horizontal structuring element to bridge words across a line
        k_w = max(15, int(w * 0.04))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_w, 4))
        dilated = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # Mask top 15% (header/clinic banner) and bottom 8% (signature)
        y_start = int(h * 0.15)
        y_end = int(h * 0.90)
        dilated[:y_start, :] = 0
        dilated[y_end:, :] = 0
        dilated[:, :int(w * 0.04)] = 0
        dilated[:, int(w * 0.96):] = 0

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            # Filter noise dots or giant full-page boxes
            if bw > int(w * 0.10) and 15 < bh < int(h * 0.22):
                boxes.append([x, y, x + bw, y + bh])

        # Cluster boxes by Y position into discrete lines
        boxes.sort(key=lambda b: b[1])
        clustered_lines = []
        for b in boxes:
            if not clustered_lines or (b[1] - clustered_lines[-1][1]) > int(h * 0.032):
                clustered_lines.append(b)
            else:
                # Merge into existing line
                clustered_lines[-1][0] = min(clustered_lines[-1][0], b[0])
                clustered_lines[-1][1] = min(clustered_lines[-1][1], b[1])
                clustered_lines[-1][2] = max(clustered_lines[-1][2], b[2])
                clustered_lines[-1][3] = max(clustered_lines[-1][3], b[3])

        # Fallback if no contours found
        if not clustered_lines:
            num_fallback_lines = 3
            slice_h = (y_end - y_start) // num_fallback_lines
            for i in range(num_fallback_lines):
                clustered_lines.append([int(w * 0.05), y_start + i * slice_h, int(w * 0.95), y_start + (i + 1) * slice_h])

        # Cap at top 8 most distinct lines
        clustered_lines = clustered_lines[:8]

        line_crops = []
        for idx, bbox in enumerate(clustered_lines):
            line_num = idx + 1
            pad_y = 8
            pad_x = 10
            x1 = max(0, bbox[0] - pad_x)
            y1 = max(0, bbox[1] - pad_y)
            x2 = min(w, bbox[2] + pad_x)
            y2 = min(h, bbox[3] + pad_y)

            crop = image_bgr[y1:y2, x1:x2]
            crop_name = f"{prefix}_line_{line_num}.png"
            crop_path = output_dir / crop_name
            cv2.imwrite(str(crop_path), crop)
            line_crops.append((crop_name, [x1, y1, x2, y2]))

        return line_crops

