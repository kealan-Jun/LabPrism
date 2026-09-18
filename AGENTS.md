# LabPrism — 实验棱镜

## Mission and priority

Build two connected deliverables: a complete LabPrism website/demo experience and a working laboratory computer-vision system, inspired by the capabilities shown in Transfyr's public demonstrations. Optimize real detection, instance/semantic/video segmentation, hand pose and tracking, object interaction, actions/steps, OCR, geometry and deployment. Data preparation supports this work; rebuilding the old data flywheel is not the main project or a release dependency.

Read `README.md`, `docs/CURRENT-WORK.md`, `docs/ROADMAP.zh-CN.md`, and the relevant architecture/contract before implementation. Keep this guidance current when the user changes direction. User instructions take precedence; execute authorized reversible work without inventing additional approval gates.

Current user priority: improve real model capabilities first. Defer NPU conversion, quantization and board deployment until the final phase. Use the website as an inspection surface for real outputs.

## Project ownership

- Repository: `/home/x1/Projects/LabPrism`. It has its own Git history, Python environment and dependencies.
- Runtime/data: `${LABPRISM_DATA_ROOT:-/home/x1/.local/share/labprism}`.
- NAS: `${LABPRISM_NAS_ROOT:-/mnt/realityloop-nas/LabPrism}`. Check the real mount and `.labprism-volume.json` identity before writing; never silently use an unmounted local directory.
- `apps/website` owns public-facing website source; `apps/viewer` will own the video analysis interface. Website preview is a preview until models are actually connected.
- AnnotationWorkbench owns datasets, annotation operations, training implementations, training environments and original training records. The user explicitly kept those responsibilities there. LabPrism owns the overall product, website, inference integration, product acceptance and deployment. Do not create a competing dataset store or trainer inside LabPrism. Training requests/specifications and inference-weight handoffs cross the boundary through versioned contracts and receipts.
- VisionCortex and FieldRecognition remain external projects. Do not modify or start their code, services or production weights without a task explicitly authorizing that project. Work explicitly assigned to AnnotationWorkbench must be implemented in that repository under its AGENTS.md.
- Existing source paths are provenance, not permission to resume another repository. Read original NAS recordings without modifying or deleting them.
- Do not create new Codex tasks or sub-agents unless the user or applicable instructions explicitly request them.

The LabPrism data root is for inference caches, received deployment artifacts, website assets and product evidence. Authoritative datasets, labels, training checkpoints and training logs remain in AnnotationWorkbench. A copied website asset or exported inference weight must retain the producer receipt and does not transfer dataset/training ownership.

## Evidence and data

- Keep frames, videos, annotations, predictions, checkpoints, databases, embeddings and evaluation output outside Git. Code, schemas, recipes, manifests without sensitive data, and documentation may be versioned.
- Preserve `source_id`, source SHA256, experiment/session, camera identity, camera role, timestamps, frame dimensions, coordinate system, parent/crop lineage, data split, label revision, provenance and licenses.
- Camera ID and first-/third-person role are separate. Unknown roles do not enter an export or run requiring a known role.
- Split by experiment/source group before sampling or augmenting. Duplicate media, adjacent frames, derived crops and synchronized views of the same experiment must not cross splits. Track exposure of all shared components.
- Detection boxes, instance masks, semantic masks, keypoints, tracks, relations, events, text and calibration each have their own completeness and review state.
- Model output is a proposal. Visually inspect actual media before accepting or correcting labels. Never label project/agent review as human or independent ground truth. Keep unresolved/ignore regions; do not hide incomplete labels by turning them into background.
- AnnotationWorkbench edits go through its CLI/API with revision checks, never direct SQLite edits. Imported legacy flywheel batches that failed quality review remain excluded unless their specific issues are resolved and receipted. Do not remove the producer's quality hold.
- Independent baseline inference and website development do not require rebuilding or restarting that flywheel. New dataset/annotation/training work belongs in AnnotationWorkbench. Respect source licenses and record code/weights/dependency license separately.

## Models and scientific claims

- Track models by task, dataset/project, role, version and backend. Do not overwrite another task/role's current model.
- Compare an executable baseline and an improvement candidate for each core task. Use frozen development validation for selection; reserve final test data for final evaluation.
- When specifying training work for AnnotationWorkbench, require an appropriate approved checkpoint, old validated-data replay and explicit partial initialization when architecture/heads change. Never describe partial loading as full optimizer resume.
- Training in AnnotationWorkbench uses GPU, prioritizing AMP and actual batch 16 or 32 when feasible. Require honest microbatch/effective-batch and throughput records; do not kill unrelated workloads.
- Consume its versioned receipt containing parent checkpoint hash, dataset version, source revision, configuration, environment, metrics and promotion decision. Keep original training records in the producer; store received inference artifacts and product acceptance reports here. Reject deployment regressions and retain rollback.
- Report accuracy, generalization, temporal quality, latency and resources separately, including first-/third-person and difficult-condition slices. Do not invent metrics; unmeasured values are null.
- Model FPS, full-pipeline latency, ONNX conversion and actual NPU execution are distinct measurements. Record the real execution provider, board/SDK, quantization and preprocessing/postprocessing.
- Local 3D hand coordinates and unscaled reconstruction are not calibrated global geometry. Require suitable evidence for metric depth, identity across cameras or physical contact.
- Never claim superiority over Transfyr without comparable outputs or benchmark evidence. Reproducing visible functionality and improving our own baseline are separately valid claims.

## Website and product

- Brand: LabPrism / 实验棱镜. Build our own site and visual assets using the reference as capability/design inspiration.
- Keep real algorithm results distinguishable from original footage and interface prototypes. Do not fabricate boxes, masks, skeletons, event captions, customers, performance, testimonials or hiring/news facts.
- Do not publish private NAS footage or a local preview externally as an incidental step. A local `127.0.0.1` preview is authorized; public release needs a concrete release task and suitable material.
- Keep the homepage, technology explanation and video experience cohesive, responsive and keyboard-accessible. Links and actions must work or clearly show their actual availability.

## Validation and handoff

- Run `python3 scripts/check_project.py` for scaffold/config/site changes. For website changes, inspect the real browser, navigation, relevant interactions and viewport layout.
- Run focused tests for changed implementation. Data revision/export/training gates need meaningful failure-case tests when implemented; do not add tests that merely repeat static documentation.
- Keep `docs/CURRENT-WORK.md` and `docs/backlog.json` aligned with evidence. Report code, browser verification, actual annotation, actual training, independent quality and deployment separately.
- Publish versioned artifacts and hash receipts to the LabPrism NAS root. Preserve prior releases. Never mark an item complete merely because its calendar week has ended.
- Default new Git branches to `codex/…`; preserve user changes and avoid blanket resets, cleans or staging data.
