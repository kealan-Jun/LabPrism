# LabPrism — 实验棱镜

## Mission and priority

Build two connected deliverables: a complete LabPrism website/demo experience and a working laboratory computer-vision system, inspired by the capabilities shown in Transfyr's public demonstrations. Optimize real detection, instance/semantic/video segmentation, hand pose and tracking, object interaction, actions/steps, OCR, geometry and deployment. Data preparation supports this work; rebuilding the old data flywheel is not the main project or a release dependency.

Read `README.md`, `docs/CURRENT-WORK.md`, `docs/ROADMAP.zh-CN.md`, and the relevant architecture/contract before implementation. Keep this guidance current when the user changes direction. User instructions take precedence; execute authorized reversible work without inventing additional approval gates.

2026-09-23 latest user authorization supersedes earlier training/promotion restrictions: deliver the complete working product and models; continuously train and iterate without waiting for another instruction. After short, same-condition validation and real-output checks demonstrate an improvement without material critical regressions, promptly deploy the versioned better model to its corresponding service, retain rollback and verify actual loaded weights. The user explicitly authorizes these qualified production model replacements. Do not keep weaker production weights merely because a replacement needs another approval. Keep quarantined legacy data excluded; this authorizes qualified candidate deployments, not declaring all proposals ground truth or blindly releasing all candidates. Preserve capture/Web operation and the original GPU window restoration deadline.

2026-09-23 latest user correction: the goal is the final working experimental vision product, not annotation completion. Do not spend prolonged time reviewing every proposal. Use explicitly identified pseudo supervision with existing reviewed replay and fixed validation to start GPU training once a task's initial labels are ready, then iterate from actual model/video errors. Keep unreviewed labels honest and preserve the legacy automatic-training quality hold. Label-generation workers do not deploy weights themselves; LabPrism carries out qualified deployments under the latest authorization above. Detection, segmentation, pose and the other product capabilities remain important; continue in this conversation without new agents or tasks.

Current user priority: improve real model capabilities first. Defer NPU conversion, quantization and board deployment until the final phase. Use the website as an inspection surface for real outputs.

2026-09-23 latest website direction: LabPrism is the brand/technology presentation surface. Continuous recording of a researcher's day or work period, time-index retrieval, uploads, queues and operational experiment analysis belong to VisionCortex. Do not rebuild or expose an analysis workspace as the LabPrism website. Show curated, read-only real recordings with time navigation and clear source/duration boundaries; a short excerpt is not evidence of all-day coverage or confirmed action segmentation. Use concise English display headlines for brand sections, with Chinese explanations and understandable controls. Prioritize large actual footage and a chronological filmstrip over generic software cards and oversized Chinese slogans. This supersedes the earlier website/workspace wording below; it does not authorize production service changes or claim existing analysis code has been migrated upstream.

2026-09-23 resource coordination update: the user subsequently chose automatic processing first in the existing task “修复精扫解码并发限制”. The temporary annotation GPU priority window has ended and analysis was restored. Do not stop/restart VisionCortex analysis, change its production configuration/systemd overrides or resume an exclusive annotation window. That task owns production deployment. Continue annotation/review using resources that do not interfere with automatic processing; preserve completed GPU batches and their resumable state.

2026-09-23 latest sequencing: the user has approved rapid bulk annotation of the expanded useful dataset: 17,001 priority candidates plus the separate 1,136 inactive-context review cohort. Proceed with detection, instance/semantic segmentation and hand-keypoint work in AnnotationWorkbench. Keep model/publisher proposals separate from actual project-reviewed labels, preserve unknown and ignore regions, and track completeness independently by task. Keep all new media, annotations, manifests, databases and logs directly on the verified AW NAS volume; code and models stay local. Preserve source-group/exposure/split evidence and the automatic-training quality hold; annotation authorization does not promote models or authorize changing production GPU allocations.

2026-09-23: rapidly fix duplicate proposals and evaluate on material absent from the current training run; audit exact and near duplicates before claiming independence. In parallel, build a polished product website and coherent experiment workspace, using the reference for information hierarchy and interaction quality. Keep research details accessible without making the main product flow a debugging dashboard. Website polish does not imply model promotion or public release.

2026-09-20: the user prioritizes rapid hand-keypoint, equipment-confusion and occlusion annotation in AnnotationWorkbench, with brief actual visual review followed by diagnostic training. Work in small frozen batches with old validated-data replay; record diagnostic results and regressions promptly. Preserve unknown labels and the existing automatic-training quality hold; isolated user-requested diagnostics do not authorize automatic promotion or use of quarantined legacy batches.

2026-09-22: continue the complete product goal in this conversation. The user authorizes reading `VisionCortexExperimentArchive/ProcessedClips`, reusing VisionCortex and FieldRecognition, and updating the responsible upstream repository when improving shared processing. Use the existing TimeIndex/ProcessedClips activity selection; an active clip is a sampling proposal, not frame-level experiment truth. Maintain separate repositories and versioned handoffs, without hardcoded camera/experiment/device relationships. Do not create additional conversations or agents. GPU diagnostics must respect actual available memory and existing locks; prepared requests are not completed training.

2026-09-23 execution pace: prioritize short cycles with visible product or model-output changes. Reuse hash-verified unchanged comparison results, run focused necessary validation, and batch archival instead of repeating it for every small iteration. Provide comprehensive status/model/dataset reports when requested; otherwise keep progress concise. Diagnose target-definition and data-coverage failures before launching more similar short training runs.

2026-09-23 最新纠正：检测、实例/语义分割、手姿等任务同样重要，不再单独手部优先；当前集中批量完成标注并准备分任务训练。初标、实际复核和导出资格分别统计。用户再次明确授权最多2小时标注优先窗口，只暂停分析，采集/Web保持；结束/失败自动恢复，有独立定时恢复保障。

2026-09-23 latest website correction: the product is a time-aligned multi-camera record with first- and third-person views and multimodal step-level understanding. Inspect VisionCortexExperimentArchive and FieldRecognitionArchive before choosing examples; do not describe an old single-camera website sample as the limit of the system. The main showcase should link actual producer steps, shared-clock views, source frames and available readout/audio evidence. Preserve the producer’s uncertainty and distinguish simultaneous playback from measured alignment precision or cross-view confirmation.

2026-09-23 website completion scope: the user approved all six improvements: stronger real excerpts, workday/work-period overview, footage visible in the first viewport, concise step names with expandable raw evidence, contextual voice/readouts, and consistent visual/product hierarchy. Preserve time gaps and partial step coverage; filename-time photos support nearby navigation only, not confirmed synchronization or step association. Keep all candidate reading differences and raw ASR wording visible with their actual status.

## Project ownership

- Repository: `/home/x1/Projects/LabPrism`. It has its own Git history, Python environment and dependencies.
- Runtime/data: `${LABPRISM_DATA_ROOT:-/home/x1/.local/share/labprism}`.
- NAS: `${LABPRISM_NAS_ROOT:-/mnt/realityloop-nas/LabPrism}`. Check the real mount and `.labprism-volume.json` identity before writing; never silently use an unmounted local directory.
- `apps/website` owns the brand website and read-only technology/recording showcases. Operational experiment analysis belongs to VisionCortex. Existing `apps/viewer` code is preserved research/integration work, not a second public analysis product. Keep actual connections and future capabilities distinguishable.
- AnnotationWorkbench owns datasets, annotation operations, training implementations, training environments and original training records. The user explicitly kept those responsibilities there. LabPrism owns the overall product, website, inference integration, product acceptance and deployment. Do not create a competing dataset store or trainer inside LabPrism. Training requests/specifications and inference-weight handoffs cross the boundary through versioned contracts and receipts.
- VisionCortex and FieldRecognition remain external projects. The integration task authorizes necessary producer code improvements in their own repositories, preferably isolated worktrees, while preserving existing changes. The latest user authorization also permits qualified model replacements and necessary service reloads with rollback; GPU pauses retain their explicit scope and deadline. Work assigned to AnnotationWorkbench is implemented there under its AGENTS.md.
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
