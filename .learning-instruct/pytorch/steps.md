# Teaching Steps

## Part 1: Collect & label your product images — in progress

### Leaf 1: Your images aren't in class folders — scattered across drives, and you can't hand-label ~1M — done

### Concepts explained

**The data manifest pattern** — real image datasets are too big to hand-arrange
into folders, and labels live in a database or spreadsheet anyway. Industry
practice is to write one small tabular file (`path,label`) that *describes*
the dataset, then have the code read that file. Everything downstream (train
split, evaluation, serving) reads the same manifest.

**`torch.utils.data.Dataset`** — the two-method contract PyTorch uses to wrap
any data source: `__len__` (how many samples) and `__getitem__(i)` (return
sample `i` as a `(input, label)` tuple). `Dataset` doesn't move data or shuffle
it — it's a plain indexable object. All the real-world mess (scattered paths,
corrupt files, DB lookups) is contained in `__getitem__`.

**`torch.utils.data.DataLoader`** — wraps a `Dataset` and adds batching,
shuffling, and parallel prefetching. `DataLoader(ds, batch_size=32, shuffle=True)`
gives you batches to iterate in the training loop. (Deep dive on its worker
knobs is leaf #64.)

**Labeling at scale** — three tiers: (1) annotators + a tool like **CVAT**
(self-hosted, supports polygon/bbox/classification labels and teamwork), (2)
outsourced labeling services, (3) **model-assisted / active learning**: train a
weak first model on a small labeled subset, let it pre-label the rest, and have
humans only correct the low-confidence ones. Tier 3 is the industry workhorse
because it cuts labeling cost by ~10x.

### Full coverage checklist

- [x] Manifest (CSV/JSONL) as the source of truth for `path,label`
- [x] Folder-scanning to bootstrap a manifest (`ImageFolder` and its limits)
- [x] Custom `Dataset` subclass reading a manifest
- [x] train/val split (stratified) at manifest build time
- [x] DataLoader basics: batching, shuffle, collate
- [x] Labeling tooling: CVAT, outsourced, model-assisted/active learning

### Exercise & outcome

To be recorded after the user's hands-on step.

### Notes

Level confirmed: beginner→intermediate — knows some concepts, hasn't shipped a
pipeline. Storage: local (besmart only, no vault writes per user choice).
