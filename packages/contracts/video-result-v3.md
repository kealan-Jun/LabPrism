# labprism-video-result/3 - continuous research candidates

Extends `/2` with bounded, explicitly unreviewed observations. The result is a
product inspection artifact, not a label export or quality acceptance record.

- `texts`: RapidOCR quadrilaterals and strings from sampled frames. `score` is
  the model score, not transcription accuracy. `numeric_value` and `unit` stay
  null until a reviewed readout parser is evaluated. Unsampled frames carry
  `availability.ocr=not_sampled`; text is never carried across frames.
- `relations`: score-qualified fingertip-to-box distances in image pixels,
  bound to the hand/object and their current track IDs. `physical_contact`
  remains null. `events` require four observed relations over at least 600 ms,
  point back to exact frames, and have `step=null`.
- `temporal_instances`: SAM2 video-memory masks from a maximum of three
  detector prompts per 50-frame window. Files are losslessly hashed and retain
  `prompted` versus `memory_propagated` state. Object identity resets at every
  window; no across-window identity or temporal-quality claim is made.
- `metrics`: candidate-stage timing and coverage only. Parent timings live in
  `baseline_metrics`; accuracy, generalization, temporal quality, OCR accuracy,
  event accuracy and NPU measurements remain null until an appropriate protocol
  and independent review exist.

The viewer renders these layers as proposals and keeps the original media,
source lineage, producer receipt and immutable parent result available.
