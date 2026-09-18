# labprism-video-result/2 — model research candidates

Extends `/1`, preserving source media, PTS, decoded RGB hashes, model identities and proposal status. `/1` remains supported. All additions are predictions or computed associations, never accepted labels.

- `derived_from`: hashes of the immutable baseline receipt and result. Baseline detection/SAM predictions are reused; candidate latency excludes that earlier execution. The exact parent result is retained as `baseline-result.json`.
- `hands`: 21 points with `[x_px,y_px,null]` for a 2D model, `depth_available=false`, and 21 raw `point_scores`. These are uncalibrated model scores, not visibility ground truth. Draw only scores at or above `keypoint_threshold`. Handedness is null when unmeasured. Original MediaPipe outputs remain in `baseline_hands`; rejected hand candidates remain in `rejected_hands`.
- `context_objects`, `conflicting_objects` and `objects[].model_conflict`: separate context model predictions and conflicts, with original detections retained. Automatic screen filtering was rejected after regression deleted real balances. Earlier research runs retain `rejected_objects`; these are fallible policy outputs, not verified laptops.
- `semantic_regions`: actual ADE20K class labels and simplified display contours; `semantic_map` points to the exact indexed PNG, SHA256 and taxonomy. Retain the complete label map; omission of tiny display regions is not an ignore label. ADE20K predictions must not be presented as an accepted laboratory taxonomy.
- `track_id`, `track_state`, `track_gap_ms`, `trail`: forward-only matching within one camera/run. A trail contains past observed centroids, not interpolated positions. During missing detections no box/mask is generated. A tentative reassociation after a short gap is not proven physical identity.
- `metrics`: coverage counts and conflicts are diagnostic measurements. Parent stage timings are isolated in `baseline_metrics`; new candidate timings exclude parent computations. Accuracy, PCK, mIoU, IDF1/HOTA, full pipeline latency and NPU remain null until measured under an appropriate protocol.

SegFormer candidate weights are restricted to research/evaluation. There is no commercial or production promotion. No semantic pixels, hands, events, OCR or trajectories may be synthesized by the viewer.
