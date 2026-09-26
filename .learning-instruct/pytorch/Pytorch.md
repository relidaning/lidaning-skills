# Subject Reference: PyTorch

**Track:** besmart plan #8 — "Pytorch learning" (2026-08-12 → 09-09)
**Problem anchor:** auto-tag ~1000 product categories for e-commerce — hand-labeling doesn't scale; from-scratch 1000-way nets won't converge. Industry stack: timm backbones, torchvision/albumentations data pipeline, wandb/MLflow, Optuna, ONNX/TorchServe.

## Key Concepts

### The data manifest pattern

**Core idea:** One small tabular file (`path,label`) is the source of truth for
an image dataset. Folders are an organization for humans; a manifest is an
organization for code.

**How it works:** Scan the raw image locations once, write rows of
`image_path,category_id` to a CSV (or JSONL), then every consumer — train
split, validation, evaluation, serving — reads the same file. You get
reproducibility (the manifest is a snapshot of exactly what went into
training) and decoupling (labels can come from a database, a labeling tool's
export, or a spreadsheet without touching image files).

**Use cases:**
- Datasets whose labels live outside the filesystem (DB, labeling tool)
- >100k images where folder layout is inconsistent or shared across machines
- Reproducible experiments: the manifest is the dataset version

**Variants:**
- CSV: `path,label` — human-readable, diffable
- JSONL: one JSON object per line — supports extra fields (`split`, `source`,
  `is_augmented`, confidence for model-assisted labels) without schema pain
- Hugging Face `datasets` / `webdataset` (tar) for very large or sharded data

**Edge cases & limitations:**
- Manifest must be regenerated when images are added/removed (stale paths
  crash at runtime)
- Paths should be relative to a data root so the manifest survives moves
  between machines/containers
- Multi-class-per-image (multi-label) needs a different schema — one column
  per class or a JSON list, plus a multi-label loss later

**Connections:**
- `torchvision.datasets.ImageFolder` is the no-manifest shortcut — requires
  `class/xxx.jpg` folders; breaks the moment data isn't in that shape
- The manifest is the "label join" that a labeling tool (CVAT export) produces

**Common mistakes:**
- Using `ImageFolder` when data isn't folder-per-class → immediate custom
  `Dataset` need
- Hardcoding absolute paths in the manifest
- Forgetting to stratify the split — random split can drop a rare class from
  the validation set entirely

### `torch.utils.data.Dataset`

**Core idea:** The two-method interface PyTorch uses to represent "anything
that can be indexed to get samples": `__len__` and `__getitem__(i)`.

**How it works:** `__getitem__` returns a `(input, label)` pair (or a dict).
All messiness — file I/O, decoding, DB lookups, transform application — lives
inside it. `Dataset` is lazy: it does nothing until you actually call
`dataset[i]`, and typically holds only paths, not decoded pixels, so even a
million-image dataset is cheap to instantiate.

**Use cases:**
- Reading a manifest/CSV into samples
- Files outside the filesystem (DB, S3, network share)
- On-the-fly processing (decoding, transforms)

**Variants:**
- Map-style (`__getitem__`) — most common; random access by index
- Iterable-style (`IterableDataset`) — for streamed/non-random-access sources

**Edge cases & limitations:**
- `__getitem__` must be fast-ish or worker processes stall the pipeline
- Never put CUDA ops inside `__getitem__` — DataLoader workers are
  CPU processes and cannot use the GPU
- Exceptions inside `__getitem__` crash the worker and fail the epoch — that's
  exactly leaf #63's problem

**Connections:**
- DataLoader calls `dataset[i]` under the hood and batches the results
- The same Dataset contract powers train/val/test — just different manifests

**Common mistakes:**
- Returning raw PIL/NumPy instead of tensors (transform pipeline must convert)
- Inconsistent return shapes across samples (breaks `collate`)
- Using global state / module-level caches that break under `num_workers`

### `torch.utils.data.DataLoader`

**Core idea:** Batches + shuffling + parallel prefetch on top of a Dataset.

**How it works:** `DataLoader(dataset, batch_size=32, shuffle=True)` iterates
the Dataset, groups samples into tensors (via `collate_fn`), and with
`num_workers>0` runs several subprocesses that decode and transform ahead of
time so the training step never waits on disk. (Worker/throughput tuning is
leaf #64; only the basics here.)

**Use cases:**
- Feeding the training loop one batch at a time
- Shuffling to break correlation between consecutive samples

**Variants:**
- `shuffle=False` for val/test (order irrelevant, but reproducibility)
- `sampler` / `batch_sampler` for custom sampling (leaf #62)
- `drop_last=True` for stable batch shapes

**Edge cases & limitations:**
- `shuffle=True` requires a map-style Dataset (has `__len__`)
- Default `collate_fn` stacks same-shape tensors; ragged shapes need a custom
  `collate_fn`

**Connections:**
- Feeds the training loop: `for x, y in dataloader:`
- Sampling strategies swap in via `sampler` without touching the Dataset

**Common mistakes:**
- `shuffle=True` on validation (valid, but pointless; hurts comparability)
- `num_workers=0` and wondering why the GPU is idle (leaf #64)

### Labeling at scale

**Core idea:** For ~1000 categories you do not hand-label a million images one
at a time. Real teams use annotation tooling + pre-labels from a weak model.

**How it works:**
- **CVAT** (Computer Vision Annotation Tool, open source, self-hostable):
  orgs/teams, tasks, and exports straight to manifest/COCO/YOLO formats. Good
  for drawing boxes/polygons AND pure classification labels.
- **Model-assisted / active learning (the 10x trick):** train a rough first
  model on a small hand-labeled subset, have it label the rest automatically,
  and route only low-confidence predictions to a human. Each round of
  "predict → correct → retrain" focuses human effort where the model is wrong.
- **Outsourced services:** for very large bulk labeling, paid labelers via
  service platforms.

**Use cases:**
- Bootstrap labels when you start with raw, unlabeled catalog images
- Continuously improve labels after evaluation finds errors (leaf #78)

**Edge cases & limitations:**
- Labeler disagreement = noisy labels; a few points of label noise is usually
  tolerable and baked into real production budgets
- Model-assisted labels inherit the model's biases — human check is mandatory
  on the tails (rare categories)

**Connections:**
- Output of labeling = the manifest (leaf #61)
- Bad/noisy labels are a class-imbalance + mislabel problem (leaf #62, #78)

**Common mistakes:**
- Perfect labels on 10k images instead of good-enough labels on 100k — recall
  that CNN training is noise-tolerant; coverage beats polish
- No labeler-agreement measurement on ambiguous categories

## Quiz Log

*(to be filled during Phase 3)*

## Scenario Log

*(to be filled during Phase 3)*

## Gotchas

- Never put CUDA operations in `Dataset.__getitem__` — workers are CPU-only
  processes.
- A manifest with absolute paths breaks the moment data moves/containerizes —
  store paths relative to a data root.
- `ImageFolder` is a convenience, not a requirement — the manifest + custom
  `Dataset` is the pattern that scales past tidy folder layouts.
- Random (unstratified) splits can silently drop a rare class from
  validation → misleading metrics later (leaf #73).
