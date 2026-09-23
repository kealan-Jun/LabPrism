# VisionCortex temporal-mask handoff / 1

LabPrism exports source-verified sampled frames and detector seeds; VisionCortex
owns SAM2 execution through `visioncortex.temporal_mask_handoff`. The consumer is
`scripts/run_upstream_video_masks.py`. It receives models from the existing runtime,
not new training or an implicit promotion. Original labels/training stay in AW.

Each original frame is checked against the parent dimensions, RGB hash, PTS and
time base before JPEG95 export. The JPEG's bytes and decoded pixels are separately
pinned: it is a declared input derivative, not an identical-pixel replay. Seed
selection is the three highest-confidence non-hand boxes at the beginning of each
50-sample window. Windows without seeds remain explicitly not_prompted.

The upstream receipt binds native 0/1 PNG masks, contours with holes, source and
camera identity, model/checkpoint, implementation, inputs and request. The consumer
rejects changed files, omitted/repeated frames, changed PTS/pixels/camera, undeclared
quality promotion, wrong seeds, wrong raster dimensions or pixel counts. It retains
the request, upstream result/receipt, original parent result/receipt and unchanged
parent layers. `verify_run` remains the final accepted-artifact gate.

The existing video-result/3 and /4 `temporal_instances` and inspection toggle render
these masks. IDs reset per window; propagated masks are proposals, not physical
object identity or action evidence. Parent inference remains distinguishable from
the added SAM2 model. No production weights are changed by this entry point.

New media, input derivatives, masks and logs go to the identity-checked NAS; code
and checkpoints remain local. CUDA memory and the existing AW GPU lock are checked;
production analysis/capture/Web are not paused. Browser delivery is loopback only.
