import os
import re
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import cv2

from app.pipeline.schema import QualityCheckResult

logger = logging.getLogger("medmatch.image_processing")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def order_quad_points(pts: np.ndarray) -> np.ndarray:
    """
    Orders 4 quadrilateral coordinates in clockwise order:
    [top-left, top-right, bottom-right, bottom-left].
    """
    rect = np.zeros((4, 2), dtype="float32")
    pts = pts.reshape(4, 2)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


class ImageQualityProcessor:
    """
    Comprehensive image quality audit, document preprocessing, layout separation,
    and handwriting line segmentation for Indian & general clinical prescriptions.
    """
    BLUR_THRESHOLD = 70.0        # Laplacian variance threshold on ink
    DARK_THRESHOLD = 50.0        # Minimum mean grayscale brightness (0-255)
    GLARE_SHARE_THRESHOLD = 0.10 # Fraction of pixels >= 252 (specular flash glare)

    # Keywords typical of printed Indian clinic headers/footers
    PRINTED_KEYWORDS = re.compile(
        r"(cell\s*:\s*\d|e-?mail|phone|tel\b|regd\.?\s*no|m\.?b\.?b\.?s|m\.?s\b|m\.?d\b|dip\s*diab|"
        r"hospital|clinic|diagnostic|healthcare|nagar|road|street|coimbatore|chennai|delhi|mumbai|"
        r"bangalore|pincode|\bpin\s*-\s*\d|consultant|ortho|dr\.?\s+[a-z]+|d\.?o\.?b|"
        r"allergy\s*:|bp\s*:|sugar\s*:|weight\s*:|temp\s*:|pulse\s*:)",
        re.IGNORECASE
    )

    def __init__(self):
        self.last_segmentation_warning: Optional[str] = None

    def analyze_quality(self, image_bgr: np.ndarray) -> QualityCheckResult:
        """
        Stage 1: Image Quality Audit.
        Inspects image for blur, darkness, and specular flash glare.
        If the image is bad, returns a structured retake guidance message.
        """
        logger.info("[Quality Audit] Inspecting image blur, brightness, and specular glare...")
        if image_bgr is None or image_bgr.size == 0:
            logger.warning("[Quality Audit] Empty or invalid image buffer.")
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

        resized = self.resize_to_long_side(image_bgr, 1600)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        total_pixels = gray.size

        # 1. Blur evaluation: calculated directly on ink pixels to handle sparse handwriting
        dynamic_range = int(np.max(gray)) - int(np.min(gray))
        if dynamic_range < 15:
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

        # 2. Darkness evaluation
        mean_brightness = float(np.mean(gray))
        is_dark = mean_brightness < self.DARK_THRESHOLD

        # 3. Glare evaluation: compact hotspot analysis
        overexposed_mask = (gray >= 252).astype(np.uint8)
        total_overexposed = int(np.sum(overexposed_mask))
        total_overexposed_share = total_overexposed / float(total_pixels)
        has_glare = False
        glare_share = 0.0

        if total_overexposed_share <= 0.40 and total_overexposed > 0:
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(overexposed_mask)
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
        logger.info(f"[Quality Audit] Result: passed={passed}, blur={laplacian_var:.1f}, brightness={mean_brightness:.1f}, glare={has_glare}")

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
        """Resizes image so that its longest side equals target_size."""
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

    def detect_and_warp_perspective(self, image_bgr: np.ndarray) -> Tuple[np.ndarray, bool]:
        """
        Stage 2a: Document Boundary Detection & 4-Point Perspective Transform.
        Rectifies tilted mobile camera shots and crops away surrounding tables/bedsheets.
        """
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(edged, kernel, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            area = cv2.contourArea(c)
            # Must occupy at least 35% of image area to be the main document
            if len(approx) == 4 and area >= 0.35 * (w * h):
                rect = order_quad_points(approx)
                (tl, tr, br, bl) = rect

                widthA = np.linalg.norm(br - bl)
                widthB = np.linalg.norm(tr - tl)
                maxWidth = max(int(widthA), int(widthB))

                heightA = np.linalg.norm(tr - br)
                heightB = np.linalg.norm(tl - bl)
                maxHeight = max(int(heightA), int(heightB))

                if maxWidth >= 200 and maxHeight >= 200:
                    dst = np.array([
                        [0, 0],
                        [maxWidth - 1, 0],
                        [maxWidth - 1, maxHeight - 1],
                        [0, maxHeight - 1]
                    ], dtype="float32")

                    M = cv2.getPerspectiveTransform(rect, dst)
                    warped = cv2.warpPerspective(image_bgr, M, (maxWidth, maxHeight), flags=cv2.INTER_CUBIC)
                    logger.info(f"[Perspective Rectification] Successfully warped prescription quad ({maxWidth}x{maxHeight}).")
                    return warped, True

        # Fallback: Detect largest paper region bounding box
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        paper_mask = ((sat < 80) & (val > 70)).astype(np.uint8) * 255
        paper_mask = cv2.morphologyEx(paper_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25)))
        paper_contours, _ = cv2.findContours(paper_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if paper_contours:
            largest = max(paper_contours, key=cv2.contourArea)
            px, py, pw, ph = cv2.boundingRect(largest)
            if pw * ph >= 0.35 * (w * h) and (pw < 0.98 * w or ph < 0.98 * h):
                logger.info(f"[Perspective Rectification] Cropped to paper bounding box: [{px}, {py}, {pw}, {ph}].")
                return image_bgr[py:py+ph, px:px+pw], True

        return image_bgr, False

    def enhance_contrast_and_ink(self, image_bgr: np.ndarray) -> np.ndarray:
        """
        Stage 2b: CLAHE contrast enhancement & bilateral ink edge preservation.
        Enhances faint ballpoint pen strokes without blowing out paper background.
        """
        lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l)
        enhanced_lab = cv2.merge([l_enhanced, a, b])
        enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        denoised = cv2.bilateralFilter(enhanced_bgr, 5, 50, 50)
        return denoised

    def deskew(self, image_bgr: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Stage 2c: Straightens tilted documents using projection-profile variance search over [-10..+10].
        """
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        ink = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
        )
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
        Stage 2d: Auto-orientation, perspective warp, and deskew.
        """
        resized = self.resize_to_long_side(image_bgr, 1600)
        h, w = resized.shape[:2]

        rotation_applied = 0
        orientation_confident = True

        if manual_rotation is not None and manual_rotation in (0, 90, 180, 270):
            rotation_applied = int(manual_rotation)
            orientation_confident = True
        else:
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
                orientation_confident = False
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

        # Apply perspective rectification if document corners are detectable
        warped, was_warped = self.detect_and_warp_perspective(resized)
        if was_warped:
            resized = warped

        # Enhance contrast and ink
        enhanced = self.enhance_contrast_and_ink(resized)
        deskewed, deskew_angle = self.deskew(enhanced)
        logger.info(f"[Auto-Orient] Applied rotation={rotation_applied}°, deskew={deskew_angle}°")
        return deskewed, deskew_angle, rotation_applied, orientation_confident

    def detect_and_mask_printed_regions(
        self,
        image_bgr: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
        """
        Stage 3: Layout Separation.
        Detects printed stationery regions (clinic header bands, footer contact banners,
        and side parameter tables) and masks them out so only the handwritten medication orders proceed.
        Returns: (body_mask, masked_image, masked_regions_metadata)
        """
        h, w = image_bgr.shape[:2]
        body_mask = np.ones((h, w), dtype=np.uint8) * 255
        masked_regions = []

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10)

        # 1. Search for a printed horizontal divider line in the top 10% - 25% of the page
        horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(w * 0.25), 1))
        horiz_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horiz_kernel)
        top_slice = np.sum(horiz_lines[int(h * 0.08) : int(h * 0.28), :], axis=1)

        header_y = 0
        if len(top_slice) > 0 and np.max(top_slice) > int(w * 0.20):
            header_y = int(h * 0.08) + int(np.argmax(top_slice))
            body_mask[0:header_y, :] = 0
            masked_regions.append({
                "type": "header_band",
                "bbox": [0, 0, w, header_y],
                "description": "Clinic letterhead & doctor credentials above divider line"
            })
            logger.info(f"[Layout Separation] Masked clinic header above divider line at y={header_y}")

        # 2. Search for a printed horizontal divider line in the bottom 85% - 98% of the page
        bottom_slice = np.sum(horiz_lines[int(h * 0.85) : int(h * 0.98), :], axis=1)
        if len(bottom_slice) > 0 and np.max(bottom_slice) > int(w * 0.20):
            footer_y = int(h * 0.85) + int(np.argmax(bottom_slice))
            body_mask[footer_y:h, :] = 0
            masked_regions.append({
                "type": "footer_band",
                "bbox": [0, footer_y, w, h],
                "description": "Clinic contact footer below divider line"
            })
            logger.info(f"[Layout Separation] Masked clinic footer below divider line at y={footer_y}")

        # 3. Detect prominent vertical column divider (separates left vitals from Rx body)
        vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(h * 0.15)))
        vert_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vert_kernel)
        col_sums = np.sum(vert_lines > 0, axis=0)
        left_divider_search = col_sums[int(w * 0.20) : int(w * 0.45)]
        if len(left_divider_search) > 0 and np.max(left_divider_search) > int(h * 0.12):
            divider_x = int(w * 0.20) + int(np.argmax(left_divider_search))
            y_start = header_y if header_y > 0 else int(h * 0.15)
            y_end = int(h * 0.88)
            body_mask[y_start:y_end, 0:divider_x] = 0
            masked_regions.append({
                "type": "vitals_column",
                "bbox": [0, y_start, divider_x, y_end],
                "description": "Patient vitals column (BP, Sugar, Weight, Allergy)"
            })
            logger.info(f"[Layout Separation] Masked patient vitals column up to x={divider_x}")

        masked_bgr = cv2.bitwise_and(image_bgr, image_bgr, mask=body_mask)
        return body_mask, masked_bgr, masked_regions

    def segment_lines(
        self,
        image_bgr: np.ndarray,
        output_dir: Path,
        prefix: str,
        return_warning: bool = False
    ) -> Any:
        """
        Stage 4: Intelligent Handwriting Line Segmentation.
        Splits the handwritten body region into individual medication order lines.
        Drops noise, merges fragments, and allows up to 30 lines.
        """
        self.last_segmentation_warning = None
        output_dir.mkdir(parents=True, exist_ok=True)
        h, w = image_bgr.shape[:2]

        # 1. Apply layout separation to mask printed letterhead, footers, and vitals
        body_mask, masked_img, _ = self.detect_and_mask_printed_regions(image_bgr)
        gray = cv2.cvtColor(masked_img, cv2.COLOR_BGR2GRAY)

        # 2. Adaptive thresholding for handwritten ink strokes
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10)
        thresh = cv2.bitwise_and(thresh, thresh, mask=body_mask)

        # Remove vertical lines (table column dividers, margins)
        vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, int(h * 0.02))))
        vert_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vert_kernel)
        thresh_clean = cv2.subtract(thresh, vert_lines)

        # Horizontal kernel to bridge medication words across a line
        k_w = max(18, int(w * 0.04))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_w, 4))
        dilated = cv2.morphologyEx(thresh_clean, cv2.MORPH_CLOSE, kernel)
        dilated = cv2.bitwise_and(dilated, dilated, mask=body_mask)

        # 3. Contour retrieval & bounding box extraction
        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        min_width = int(w * 0.08)
        min_height = 14
        max_height = int(h * 0.25)

        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            if bw >= min_width and min_height <= bh <= max_height:
                boxes.append([x, y, x + bw, y + bh])

        if not boxes:
            logger.warning("[Line Segmentation] No handwritten lines detected in body region.")
            if return_warning:
                return [], None
            return []

        # 4. Cluster and merge boxes by vertical Y-overlap
        boxes.sort(key=lambda b: b[1])
        clustered_lines = []
        y_tolerance = int(h * 0.02)

        for b in boxes:
            if not clustered_lines:
                clustered_lines.append(b)
            else:
                last_line = clustered_lines[-1]
                y_overlap = min(last_line[3], b[3]) - max(last_line[1], b[1])
                if y_overlap > 0 or (b[1] - last_line[1]) <= y_tolerance:
                    last_line[0] = min(last_line[0], b[0])
                    last_line[1] = min(last_line[1], b[1])
                    last_line[2] = max(last_line[2], b[2])
                    last_line[3] = max(last_line[3], b[3])
                else:
                    clustered_lines.append(b)

        # Cap at 30 lines, warn if truncated
        line_warning = None
        if len(clustered_lines) > 30:
            clustered_lines = clustered_lines[:30]
            line_warning = "Prescription exceeds 30 lines. Line segmentation truncated to top 30 lines."
            self.last_segmentation_warning = line_warning

        line_crops = []
        for idx, bbox in enumerate(clustered_lines):
            line_num = idx + 1
            pad_y = 6
            pad_x = 8
            x1 = max(0, bbox[0] - pad_x)
            y1 = max(0, bbox[1] - pad_y)
            x2 = min(w, bbox[2] + pad_x)
            y2 = min(h, bbox[3] + pad_y)

            crop = image_bgr[y1:y2, x1:x2]
            crop_name = f"{prefix}_line_{line_num}.png"
            crop_path = output_dir / crop_name
            cv2.imwrite(str(crop_path), crop)
            line_crops.append((crop_name, [x1, y1, x2, y2]))

        logger.info(f"[Line Segmentation] Extracted {len(line_crops)} clean handwritten lines.")
        if return_warning:
            return line_crops, line_warning
        return line_crops
