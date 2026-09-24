# VisionCortex temporal-mask handoff / 1

2026-09-24: request `/2` adds explicit `data_use`. It accepts existing development
sources or receipted `production_observation` inputs with `split: null`,
`training_use_authorized: false` and `independent_ground_truth: false`. Unknown
roles and sealed evaluation sources remain rejected. Version `/1` remains
development-only. The producer echoes the purpose and the consumer checks it.

LabPrism exports source-verified sampled frames and detector seeds; VisionCortex
owns SAM2 execution through `visioncortex.temporal_mask_handoff`. The consumer is
`scripts/run_upstream_video_masks.py`. It receives models from the existing runtime,
not new training or an implicit promotion. Original labels/training stay in AW.

Each original frame is checked against the parent dimensions, RGB hash, PTS and
time base before JPEG95 export. The JPEG's bytes and decoded pixels are separately
pinned: it is a declared input derivative, not an identical-pixel replay. Seed
selection defaults to three highest-confidence non-hand boxes at the beginning of
each 50-sample window. `--seed-policy geometry_diverse --max-objects 8` reuses the
upstream complete-link geometry grouping and class-diverse selection: mutually
overlapping IoU≥0.85 boxes share one provisional seed while all hypotheses remain
in `proposal_group`. Conflicting classes stay explicitly unresolved. Windows without
seeds remain not_prompted. This grouping never confirms physical identity.

The upstream receipt binds native 0/1 PNG masks, contours with holes, source and
camera identity, model/checkpoint, implementation, inputs and request. The consumer
rejects changed files, omitted/repeated frames, changed PTS/pixels/camera, undeclared
quality promotion, wrong seeds, wrong raster dimensions or pixel counts. It retains
the request, upstream result/receipt, original parent result/receipt and unchanged
parent layers. Seed-group members must exactly match original detector instances;
resolved-identity or false resolved-class claims are rejected. `verify_run` remains
the final accepted-artifact gate. Original raw detections are not silently removed.

The existing video-result/3 and /4 `temporal_instances` and inspection toggle render
these masks. IDs reset per window; propagated masks are proposals, not physical
object identity or action evidence. Parent inference remains distinguishable from
the added SAM2 model. No production weights are changed by this entry point.

New media, input derivatives, masks and logs go to the identity-checked NAS; code
and checkpoints remain local. CUDA memory and the existing AW GPU lock are checked;
production analysis/capture/Web are not paused. Browser delivery is loopback only.

`scripts/run_service_detector.py` refreshes a frozen parent video's complete sampled
detector output using the current configured VisionCortex `RoleScanner`, TensorRT
engine and duplicate policy. It pins engine SHA, actual CUDA backend and execution
batch size; verifies decoded RGB/ordinal/time against the parent; and excludes old
pose/relations/events from the new result. Those old outputs remain in the parent
receipt. This is inference integration, not a new trainer or service restart.

The same detector entry now accepts `--media RECEIPTED_INPUT` instead of `--parent`.
Fresh videos use 1–10 Hz native-PTS sampling and emit video-result/4 with independent
output states, an explicit PTS origin, null unknown global/capture clocks, and
source/crop provenance. It uses the configured role-specific TensorRT engine and
duplicate policy. `--parent` still verifies every original sample's ordinal,
native PTS/timebase, dimensions and RGB hash. Both paths share inference; neither
requires inventing an empty prior model run. PyAV is the pinned dependency in
`configs/deployment/inference-requirements.txt` and must be available in the
TensorRT execution environment. These callable stages do not by themselves prove
that the VisionCortex Web task queue invokes the full pipeline.
