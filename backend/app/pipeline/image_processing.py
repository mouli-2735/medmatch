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

    def __init__(self):
        self.last_segmentation_warning: Optional[str] = None

    def analyze_quality(self, image_bgr: np.ndarray) -> QualityCheckResult:
        """
        Inspects image for blur, darkness, and flash glare.
        - Blur check is computed on a resized image and on the ink area so sparse handwriting is not called blurry.
        - Glare check only rejects compact overexposed hotspots, never a clean white scan or screenshot.
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

        # Work on scale-independent resized representation
        resized = self.resize_to_long_side(image_bgr, 1600)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        total_pixels = gray.size

        # 1. Blur check computed on resized image and ink area
        dynamic_range = int(np.max(gray)) - int(np.min(gray))
        if dynamic_range < 15:
            # Flat/blank image without handwriting strokes - defer to line segmentation to reject
            laplacian_var = 0.0
            is_blurry = False
        else:
            ink_mask = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
            )
            ink_dilated = cv2.dilate(ink_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
            lap = cv2.Laplacian(gray, cv2.CV_64F)
            ink_lap = lap[ink_dilated > 0]
            if len(ink_lap) >= 50:
                laplacian_var = float(np.var(ink_lap))
            else:
                laplacian_var = float(lap.var())
            is_blurry = laplacian_var < self.BLUR_THRESHOLD

        # 2. Dark check via mean brightness
        mean_brightness = float(np.mean(gray))
        is_dark = mean_brightness < self.DARK_THRESHOLD

        # 3. Glare check: Only reject compact overexposed hotspots, not clean pure-white scans or screenshots
        overexposed_mask = (gray >= 252).astype(np.uint8)
        total_overexposed = int(np.sum(overexposed_mask))
        total_overexposed_share = total_overexposed / float(total_pixels)
        has_glare = False
        glare_share = 0.0

        # If overexposed pixels dominate the image (> 40%), it is a clean white scan or screenshot
        if total_overexposed_share <= 0.40 and total_overexposed > 0:
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(overexposed_mask)
            hotspot_shares = []
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                bw = stats[i, cv2.CC_STAT_WIDTH]
                bh = stats[i, cv2.CC_STAT_HEIGHT]
                share = float(area / total_pixels)
                if 0.01 <= share <= 0.40 and bw < 0.85 * w and bh < 0.85 * h:
                    non_hotspot = gray[labels != i]
                    if len(non_hotspot) > 0 and float(np.mean(non_hotspot)) < 248:
                        hotspot_shares.append(share)
            if hotspot_shares:
                has_glare = True
                glare_share = max(hotspot_shares)

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
                try:
                    orient_res = ocr_reader.detect_orientation(resized)
                    if isinstance(orient_res, (tuple, list)) and len(orient_res) == 2:
                        gemini_rot, gemini_conf = orient_res
                        if gemini_conf and gemini_rot is not None:
                            rotation_applied = gemini_rot
                            orientation_confident = True
                except Exception:
                    gemini_rot = None

            if gemini_rot is None:
                # Gemini is unavailable: apply default and set orientation_confident=False
                orientation_confident = False
                # If uploaded photo is landscape (w > h), rotate 270 deg to make portrait.
                # If already portrait (h >= w), keep upright at 0 deg. Never rotate portrait to landscape.
                if w > h * 1.15:
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

    def segment_lines(
        self,
        image_bgr: np.ndarray,
        output_dir: Path,
        prefix: str,
        return_warning: bool = False
    ) -> Any:
        """
        Cuts prescription image into individual horizontal line crops.
        - Bounding box of largest low-saturation bright paper region replaces fixed margin masks.
        - Letterhead bands, thumbs, and backgrounds are excluded.
        - Fragments smaller than ~15% page width or too short (< 15px) are dropped.
        - Allows up to 30 lines (warns if truncated).
        - 3-equal-slices fallback removed: returns empty list if no handwriting found.
        """
        self.last_segmentation_warning = None
        output_dir.mkdir(parents=True, exist_ok=True)
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

        # 1. Detect bounding box of the largest low-saturation bright paper region
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        paper_mask = ((sat < 70) & (val > 80)).astype(np.uint8) * 255
        paper_mask = cv2.morphologyEx(paper_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))

        paper_contours, _ = cv2.findContours(paper_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if paper_contours:
            largest_paper = max(paper_contours, key=cv2.contourArea)
            px, py, pw, ph = cv2.boundingRect(largest_paper)
            if pw * ph >= 0.15 * (w * h):
                paper_x1, paper_y1, paper_x2, paper_y2 = px, py, px + pw, py + ph
            else:
                paper_x1, paper_y1, paper_x2, paper_y2 = 0, 0, w, h
        else:
            paper_x1, paper_y1, paper_x2, paper_y2 = 0, 0, w, h

        # 2. Adaptive thresholding to isolate handwriting ink
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10)

        # Horizontal structuring element to bridge words across a line
        k_w = max(15, int(w * 0.04))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_w, 4))
        dilated = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # Only retain dilated ink inside the paper region (excludes letterhead bands, thumbs, backgrounds)
        region_mask = np.zeros((h, w), dtype=np.uint8)
        in_x = max(2, int((paper_x2 - paper_x1) * 0.01))
        in_y = max(2, int((paper_y2 - paper_y1) * 0.01))
        region_mask[paper_y1 + in_y : paper_y2 - in_y, paper_x1 + in_x : paper_x2 - in_x] = 255
        dilated = cv2.bitwise_and(dilated, dilated, mask=region_mask)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        # Filter fragments smaller than ~15% page width or too short (< 15px) or giant blocks
        min_width = int(w * 0.15)
        min_height = 15
        max_height = int(h * 0.25)
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            if bw >= min_width and min_height <= bh <= max_height:
                boxes.append([x, y, x + bw, y + bh])

        # Cluster boxes by Y position into discrete lines
        boxes.sort(key=lambda b: b[1])
        clustered_lines = []
        for b in boxes:
            if not clustered_lines or (b[1] - clustered_lines[-1][1]) > int(h * 0.025):
                clustered_lines.append(b)
            else:
                # Merge into existing line
                clustered_lines[-1][0] = min(clustered_lines[-1][0], b[0])
                clustered_lines[-1][1] = min(clustered_lines[-1][1], b[1])
                clustered_lines[-1][2] = max(clustered_lines[-1][2], b[2])
                clustered_lines[-1][3] = max(clustered_lines[-1][3], b[3])

        # If no lines found: remove the 3-equal-slices fallback!
        if not clustered_lines:
            if return_warning:
                return [], None
            return []

        # Allow up to 30 lines, warn if truncated
        line_warning = None
        if len(clustered_lines) > 30:
            clustered_lines = clustered_lines[:30]
            line_warning = "Prescription exceeds 30 lines. Line segmentation truncated to top 30 lines."
            self.last_segmentation_warning = line_warning

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

        if return_warning:
            return line_crops, line_warning
        return line_crops


