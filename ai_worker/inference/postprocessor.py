"""
VisionGuard AI - Result Postprocessor

Decodes YOLOv8 ONNX model output and applies confidence thresholding + NMS.

YOLOv8 output format:
  - Detection models: (1, 4+num_classes, 8400) — 8400 candidate boxes
    Rows 0-3: bbox (cx, cy, w, h) in pixel coordinates
    Rows 4+:  class confidence scores (already sigmoid-normalized, 0-1)
    
  - Pose models (fall): (1, 4+num_classes+keypoints, 8400)
    Row 0-3: bbox, Row 4: single class score, Rows 5+: keypoint data

Processing steps:
  1. Transpose to (8400, N) so each row is one candidate box
  2. Extract class scores and find best class per box
  3. Filter by confidence threshold
  4. Apply NMS to remove overlapping duplicates
  5. Return best detection (highest confidence post-NMS)
"""

import cv2
import numpy as np
import logging
from typing import Optional, Dict


class Postprocessor:
    """
    Result postprocessor for YOLOv8 ONNX model outputs.
    
    Correctly parses (1, 4+C, 8400) transposed format,
    applies confidence thresholding and NMS.
    """
    
    # NMS parameters
    NMS_IOU_THRESHOLD = 0.45     # IoU threshold for NMS overlap removal
    NMS_SCORE_THRESHOLD = 0.10   # Pre-NMS score filter (very permissive, real filtering is confidence_threshold)
    
    def __init__(
        self,
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        agnostic_nms: bool = False,
        allowed_class_ids: str = ""
    ):
        """
        Initialize postprocessor.
        
        Args:
            confidence_threshold: Minimum confidence for valid detections (0-1)
            iou_threshold: NMS IoU threshold (lower = merge overlapping boxes)
            agnostic_nms: If True, treat all classes as one during NMS
                          (recommended for fire+smoke to prevent redundant boxes)
            allowed_class_ids: Comma-separated list of allowed class IDs.
        """
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.agnostic_nms = agnostic_nms
        
        self.allowed_classes = None
        if allowed_class_ids:
            try:
                self.allowed_classes = {int(x.strip()) for x in allowed_class_ids.split(",") if x.strip()}
            except ValueError:
                pass
        
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(
            f"Postprocessor initialized",
            extra={
                "confidence_threshold": confidence_threshold,
                "iou_threshold": iou_threshold,
                "agnostic_nms": agnostic_nms,
            }
        )
    
    def postprocess(self, output: np.ndarray) -> Optional[Dict]:
        """
        Postprocess YOLOv8 model output.
        
        Handles:
          - 3D output (1, 4+C, N): YOLOv8 detection/pose format
          - 2D output (1, C): classification-only format
        
        Args:
            output: Raw model output from ONNX inference
            
        Returns:
            Dictionary with 'confidence' and 'bbox', or None if no detection above threshold
        """
        try:
            if output.ndim == 3:
                return self._postprocess_yolov8(output)
            elif output.ndim == 2:
                return self._postprocess_classification(output)
            else:
                self.logger.warning(
                    "Unexpected output shape",
                    extra={"output_shape": output.shape}
                )
                return None
                
        except Exception as e:
            self.logger.error(
                f"Postprocessing failed: {e}",
                extra={"error": str(e), "output_shape": output.shape}
            )
            return None
    
    def _postprocess_yolov8(self, output: np.ndarray) -> Optional[Dict]:
        """
        Process YOLOv8 detection output.
        
        Input format: (1, 4+num_classes, num_boxes) e.g. (1, 84, 8400)
        - Rows 0-3: cx, cy, w, h (bounding box in pixel coords)
        - Rows 4+: class confidence scores (sigmoid-normalized, 0-1)
        
        For pose models like fall detection: (1, 56, 8400)
        - Row 0-3: cx, cy, w, h
        - Row 4: single class score
        - Rows 5+: keypoint data (ignored for classification)
        """
        # Step 1: Transpose from (1, features, boxes) to (boxes, features)
        # e.g. (1, 84, 8400) -> (8400, 84)
        predictions = output[0].T  # (8400, 84)
        
        num_features = predictions.shape[1]
        num_boxes = predictions.shape[0]
        
        # Step 2: Split bbox and class scores
        bboxes = predictions[:, :4]       # (8400, 4) - cx, cy, w, h
        
        # Determine model type from feature count
        # YOLOv8 detection: 4 bbox + N classes (e.g., 84 = 4+80 COCO classes)
        # YOLOv8-pose:      4 bbox + 1 class + 51 keypoints (17 joints × 3) = 56
        is_pose_model = (num_features == 56)
        
        if is_pose_model:
            # Pose model: only column 4 is the class score
            # Columns 5-55 are keypoint data (x, y, visibility × 17), NOT classes
            class_scores = predictions[:, 4:5]  # (8400, 1)
        else:
            # Detection model: columns 4+ are all class scores
            class_scores = predictions[:, 4:]   # (8400, num_classes)
        
        num_classes = class_scores.shape[1]
        
        # Apply sigmoid if scores look like raw logits (any value outside 0-1)
        # YOLOv8-pose models may output un-normalized logits
        if class_scores.max() > 1.0 or class_scores.min() < 0.0:
            class_scores = 1.0 / (1.0 + np.exp(-np.clip(class_scores, -500, 500)))
        
        self.logger.debug(
            "YOLO output parsed",
            extra={
                "num_boxes": num_boxes,
                "num_features": num_features,
                "num_classes": num_classes,
                "is_pose_model": is_pose_model
            }
        )
        
        # Step 3: Get best class score per box
        if num_classes == 1:
            # Single-class model (pose or single-class detection)
            max_scores = class_scores[:, 0]
            max_class_ids = np.zeros(num_boxes, dtype=np.int32)
        else:
            max_scores = class_scores.max(axis=1)
            max_class_ids = class_scores.argmax(axis=1)
        
        # Step 4: Filter by confidence threshold
        mask = max_scores >= self.confidence_threshold
        
        # Step 4b: Filter by allowed classes
        if self.allowed_classes is not None:
            # Only keep boxes where the class ID is in the allowed list
            class_mask = np.isin(max_class_ids, list(self.allowed_classes))
            mask = mask & class_mask
            
        filtered_count = mask.sum()
        
        if filtered_count == 0:
            self.logger.debug(
                "No detections above threshold (or failed class filter)",
                extra={
                    "max_score": float(max_scores.max()) if len(max_scores) > 0 else 0.0,
                    "threshold": self.confidence_threshold
                }
            )
            return None
        
        filtered_bboxes = bboxes[mask]       # (N, 4) in cx, cy, w, h
        filtered_scores = max_scores[mask]    # (N,)
        filtered_classes = max_class_ids[mask]
        
        # Step 5: Convert from center format (cx, cy, w, h) to corner format (x1, y1, w, h)
        # cv2.dnn.NMSBoxes expects (x, y, w, h) where x,y is top-left
        nms_bboxes = np.zeros_like(filtered_bboxes)
        nms_bboxes[:, 0] = filtered_bboxes[:, 0] - filtered_bboxes[:, 2] / 2  # x1
        nms_bboxes[:, 1] = filtered_bboxes[:, 1] - filtered_bboxes[:, 3] / 2  # y1
        nms_bboxes[:, 2] = filtered_bboxes[:, 2]  # w
        nms_bboxes[:, 3] = filtered_bboxes[:, 3]  # h
        
        # Step 6: Apply NMS
        # agnostic_nms: treat all boxes as same class (best for fire+smoke overlap)
        nms_class_ids = np.zeros_like(filtered_classes) if self.agnostic_nms else filtered_classes
        
        indices = cv2.dnn.NMSBoxes(
            bboxes=nms_bboxes.tolist(),
            scores=filtered_scores.tolist(),
            score_threshold=self.NMS_SCORE_THRESHOLD,
            nms_threshold=self.iou_threshold
        )
        
        if len(indices) == 0:
            self.logger.debug(
                "All detections removed by NMS",
                extra={"pre_nms_count": int(filtered_count)}
            )
            return None
        
        # Flatten indices (OpenCV returns nested array in some versions)
        if isinstance(indices, np.ndarray):
            indices = indices.flatten()
        
        # Step 7: Pick best detection (highest confidence post-NMS)
        best_nms_idx = indices[0]
        for idx in indices:
            if filtered_scores[idx] > filtered_scores[best_nms_idx]:
                best_nms_idx = idx
        
        best_score = float(filtered_scores[best_nms_idx])
        best_class = int(filtered_classes[best_nms_idx])
        
        # Convert bbox to (x1, y1, x2, y2) format for output
        cx, cy, w, h = filtered_bboxes[best_nms_idx]
        bbox = [
            float(cx - w / 2),  # x1
            float(cy - h / 2),  # y1
            float(cx + w / 2),  # x2
            float(cy + h / 2),  # y2
        ]
        
        result = {
            "confidence": best_score,
            "bbox": bbox,
            "class_id": best_class
        }
        
        self.logger.debug(
            "Detection postprocessed",
            extra={
                "confidence": round(best_score, 4),
                "class_id": best_class,
                "bbox": [round(b, 1) for b in bbox],
                "pre_nms_count": int(filtered_count),
                "post_nms_count": len(indices)
            }
        )
        
        return result
    
    def _postprocess_classification(self, output: np.ndarray) -> Optional[Dict]:
        """
        Process classification-only output.
        
        Input format: (1, num_classes) — raw logits or probabilities.
        Applies softmax if values look like raw logits (any value > 1 or < 0).
        """
        scores = output[0]  # (num_classes,)
        
        # Apply softmax if these look like raw logits (not already probabilities)
        if scores.max() > 1.0 or scores.min() < 0.0:
            # Raw logits — apply softmax to normalize
            exp_scores = np.exp(scores - scores.max())  # numerical stability
            scores = exp_scores / exp_scores.sum()
        
        confidence = float(scores.max())
        class_id = int(scores.argmax())
        
        if confidence < self.confidence_threshold:
            self.logger.debug(
                "Classification below threshold",
                extra={
                    "confidence": round(confidence, 4),
                    "threshold": self.confidence_threshold
                }
            )
            return None
        
        result = {
            "confidence": confidence,
            "bbox": None,
            "class_id": class_id
        }
        
        self.logger.debug(
            "Classification postprocessed",
            extra={"confidence": round(confidence, 4), "class_id": class_id}
        )
        
        return result
