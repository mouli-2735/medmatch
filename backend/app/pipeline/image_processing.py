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

    @staticmethod
    def resize_to_long_side(image_bgr: np.ndarray, target_size: int = 1600) -> np.ndarray:
        """Resizes image so that its longest side equals target_size (scale-independent thresholds)"""
        if image_bgr is None or image_bgr.size == 0:
            return image_bgr
        h, w = image_bgr.shape[:2]
        long_side = max(h, w)
        if long_side == target_size:
            return image_bgr
        scale = target_size / float(long_side)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        return cv2.resize(image_bgr, (new_w, new_h), interpolation=interp)

    def deskew(self, image_bgr: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Straightens skewed document using a projection-profile variance search
        over -10..+10 degrees on ink pixels.
        """
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        ink = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
        )
        # Downsample for fast profile search (~50ms)
        scale = 400.0 / max(h, w)
        small_w = max(1, int(round(w * scale)))
        small_h = max(1, int(round(h * scale)))
        small_ink = cv2.resize(ink, (small_w, small_h), interpolation=cv2.INTER_NEAREST)

        center = (small_w // 2, small_h // 2)
        best_angle = 0.0
        max_var = -1.0

        for a in np.arange(-10.0, 10.5, 0.5):
            M = cv2.getRotationMatrix2D(center, float(a), 1.0)
            rot = cv2.warpAffine(small_ink, M, (small_w, small_h), flags=cv2.INTER_NEAREST)
            proj = np.sum(rot > 0, axis=1)
            v = float(np.var(proj))
            if v > max_var:
                max_var = v
                best_angle = float(a)

        # Only deskew if noticeable tilt (>= 0.5 degrees)
        if abs(best_angle) >= 0.5:
            full_center = (w // 2, h // 2)
            M_full = cv2.getRotationMatrix2D(full_center, best_angle, 1.0)
            deskewed = cv2.warpAffine(
                image_bgr, M_full, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
            return deskewed, round(best_angle, 2)

        return image_bgr, 0.0

    def auto_orient_and_deskew(
        self,
        image_bgr: np.ndarray,
        ocr_reader: Optional[Any] = None,
        manual_rotation: Optional[int] = None
    ) -> Tuple[np.ndarray, float, int, bool]:
        """
        1. Resizes image to long side 1600 before processing so thresholds are scale-independent.
        2. Applies manual rotation override if provided (0, 90, 180, 270).
           Otherwise computes row-projection variance on paper ink vs transpose to detect axis,
           and invokes low-res (<=512px) Gemini orientation call to resolve 0/180 or 90/270.
           If Gemini is unavailable, applies default and sets orientation_confident=False.
        3. Straightens tilt using projection-profile variance search over -10..+10 degrees.
        Returns: (deskewed_image, deskew_angle, rotation_applied, orientation_confident)
        """
        resized = self.resize_to_long_side(image_bgr, 1600)
        h, w = resized.shape[:2]

        rotation_applied = 0
        orientation_confident = True

        if manual_rotation is not None and manual_rotation in (0, 90, 180, 270):
            rotation_applied = int(manual_rotation)
            orientation_confident = True
            if rotation_applied == 90:
                resized = cv2.rotate(resized, cv2.ROTATE_90_CLOCKWISE)
            elif rotation_applied == 180:
                resized = cv2.rotate(resized, cv2.ROTATE_180)
            elif rotation_applied == 270:
                resized = cv2.rotate(resized, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            # Detect axis: compute row-projection variance of ink pixels
            hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
            sat = hsv[:, :, 1]
            val = hsv[:, :, 2]
            paper_mask = ((sat < 70) & (val > 80)).astype(np.uint8) * 255
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            ink = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10
            )
            ink = cv2.bitwise_and(ink, ink, mask=paper_mask)

            proj_h = np.sum(ink > 0, axis=1).astype(float)
            proj_v = np.sum(ink.T > 0, axis=1).astype(float)
            var_h = float(np.var(proj_h))
            var_v = float(np.var(proj_v))

            # Query small low-res (<=512px) Gemini orientation call if available
            gemini_rot = None
            if ocr_reader and hasattr(ocr_reader, "detect_orientation"):
                gemini_rot, gemini_conf = ocr_reader.detect_orientation(resized)
                if gemini_conf and gemini_rot is not None:
                    rotation_applied = gemini_rot
                    orientation_confident = True

            if gemini_rot is None:
                # Gemini is unavailable: apply default and set orientation_confident=False
                orientation_confident = False
                if w > h * 1.15 or var_v > var_h:
                    rotation_applied = 270
                else:
                    rotation_applied = 0

            if rotation_applied == 90:
                resized = cv2.rotate(resized, cv2.ROTATE_90_CLOCKWISE)
            elif rotation_applied == 180:
                resized = cv2.rotate(resized, cv2.ROTATE_180)
            elif rotation_applied == 270:
                resized = cv2.rotate(resized, cv2.ROTATE_90_COUNTERCLOCKWISE)

        deskewed, deskew_angle = self.deskew(resized)
        return deskewed, deskew_angle, rotation_applied, orientation_confident

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

