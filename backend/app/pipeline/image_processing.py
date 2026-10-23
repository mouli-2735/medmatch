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

    def segment_lines(self, image_bgr: np.ndarray, output_dir: Path, prefix: str) -> List[Tuple[str, List[int]]]:
        """
        Cuts prescription image into horizontal line crops using horizontal projection profile.
        Saves each crop and returns list of (crop_filename, [x1, y1, x2, y2]).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

        # Skip top header area (first 180px) and bottom signature area (last 100px)
        roi_y_start = min(180, int(h * 0.18))
        roi_y_end = max(h - 100, int(h * 0.88))
        
        roi_gray = gray[roi_y_start:roi_y_end, :]
        thresh = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        # Horizontal projection: count of ink pixels across each row
        proj = np.sum(thresh > 0, axis=1)
        
        # Smooth projection
        kernel_size = 15
        kernel = np.ones(kernel_size) / kernel_size
        smooth_proj = np.convolve(proj, kernel, mode="same")
        
        ink_threshold = np.mean(smooth_proj) * 0.25
        is_ink = smooth_proj > ink_threshold
        
        # Find continuous ink segments
        segments = []
        in_segment = False
        start_y = 0
        
        for y, val in enumerate(is_ink):
            if val and not in_segment:
                in_segment = True
                start_y = y
            elif not val and in_segment:
                in_segment = False
                if (y - start_y) >= 20: # Minimum line height
                    segments.append((start_y, y))
                    
        if in_segment and (len(is_ink) - start_y) >= 20:
            segments.append((start_y, len(is_ink)))

        # If projection didn't find clear lines, fallback to equal vertical slicing
        if not segments:
            num_fallback_lines = 3
            slice_h = (roi_y_end - roi_y_start) // num_fallback_lines
            for i in range(num_fallback_lines):
                segments.append((i * slice_h, (i + 1) * slice_h))

        line_crops = []
        for idx, (seg_start, seg_end) in enumerate(segments):
            line_num = idx + 1
            # Add padding
            pad_y = 12
            y1 = max(0, roi_y_start + seg_start - pad_y)
            y2 = min(h, roi_y_start + seg_end + pad_y)
            x1 = int(w * 0.05)
            x2 = int(w * 0.95)

            crop = image_bgr[y1:y2, x1:x2]
            crop_name = f"{prefix}_line_{line_num}.png"
            crop_path = output_dir / crop_name
            cv2.imwrite(str(crop_path), crop)
            line_crops.append((crop_name, [x1, y1, x2, y2]))

        return line_crops
