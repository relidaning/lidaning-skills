# Compositions

**Problem:** You're asked to auto-tag ~1000 kinds of products by category for an
e-commerce catalog — hand-labeling doesn't scale, and a 1000-way CNN trained
from scratch won't converge on the data you actually have. The industry fix is
a transfer-learned image classifier built on PyTorch's standard stack (`timm`
backbones, `torchvision`/`albumentations` data pipeline, `wandb`/`MLflow`
tracking, `Optuna` tuning, `ONNX`/`TorchServe` serving). Each leaf below is one
concrete, real-life issue you'll hit while shipping it — the teaching unit.

1. **Collect & label your product images** *(besmart task #53)*
   - **Your images aren't in class folders — scattered across drives, and you
     can't hand-label ~1M** *(leaf #61)* — build a `path,label` manifest
     (CSV/JSONL) from a folder scan, train/val split, drive training from a
     custom `Dataset` reading the manifest; label at scale with CVAT or
     model-assisted labeling
   - **10 photos for your rarest categories vs 10,000 for common ones — the
     loader mostly feeds big classes** *(leaf #62)* — log per-class counts,
     `WeightedRandomSampler` for balanced sampling, stratified train/val split
   - **One corrupt JPG crashes the whole epoch with a PIL decode error at hour
     3** *(leaf #63)* — robust `Dataset.__getitem__` (try/except fallback),
     upfront file verification pass, dedupe near-identical images
   - **GPU sits at 30% because every epoch re-decodes JPGs one-by-one from
     disk** *(leaf #64)* — tune `DataLoader`: `num_workers`, `pin_memory`,
     `prefetch_factor`, `persistent_workers`; downscale images on ingest
2. **Design your classifier** *(besmart task #54)*
   - **A from-scratch 1000-way net won't converge on your data** *(leaf #65)*
     — transfer learning: `timm.create_model(pretrained=True)` frozen backbone
     + new classifier head
   - **The pretrained model outputs 1000 ImageNet classes, not your products,
     and your photos aren't 224×224** *(leaf #66)* — swap the classifier head
     to your class count; match input resolution to what the backbone expects
   - **Can't tell if ResNet50/EfficientNet/ViT is "enough", and the big one
     won't fit your GPU** *(leaf #67)* — head-only benchmark of 2–3 candidates;
     pick by params, val accuracy, and GPU memory fit
3. **Train it** *(besmart task #55)*
   - **Loss explodes to NaN in the first batches** *(leaf #68)* — lower LR,
     normalize inputs to ImageNet mean/std, scan data for `inf`; diagnose
     which of the three it is
   - **Train loss drops but val loss climbs — it's memorizing, not learning**
     *(leaf #69)* — overfitting: augmentation, dropout, early stopping on val,
     watch the train–val gap
   - **Laptop-CPU training would take a week — the GPU is right there, unused**
     *(leaf #70)* — `.to(device)`, mixed precision (`torch.autocast` +
     `GradScaler`), `torch.compile`; verify with `nvidia-smi`
   - **Your 5-hour run dies at epoch 3 from a lid close and restarts from
     zero** *(leaf #71)* — checkpoint model+optimizer+scaler+epoch, save
     best-on-val, resume-from-checkpoint in the loop
   - **Every run differs slightly — you can't tell if a change helped** *(leaf
     #72)* — seeds (`torch.manual_seed`, numpy seed, worker generator,
     deterministic algorithms flag)
4. **Evaluate it** *(besmart task #56)*
   - **"96% accuracy" but it just predicts the 5 biggest categories** *(leaf
     #73)* — imbalance-aware metrics: per-class precision/recall, macro-F1,
     confusion matrix
   - **Top-1 at 1000 classes is brutal — a good model "misses" almost
     everything** *(leaf #74)* — top-5 accuracy, softmax confidence,
     rank-based expectations
   - **Forgot `model.eval()` — validation numbers are garbage and you don't
     know why** *(leaf #75)* — `train()`/`eval()` mode semantics, BatchNorm &
     dropout behavior, `torch.no_grad()`/`inference_mode()`
   - **White sneaker vs off-white sneaker — you need to see exactly where it
     fails** *(leaf #76)* — confusion-matrix visualization, per-class error
     lists, eyeball the misclassified images
5. **Iterate on what evaluation surfaces** *(besmart task #57)*
   - **Val set is from the same photoshoot as training; real deployment photos
     do worse** *(leaf #77)* — distribution shift: production-like val set,
     confidence/calibration tracking
   - **The weak categories are the rare ones with 10 images** *(leaf #78)* —
     targeted collection, class-aware oversampling, relabel the mistakes
     evaluation found
   - **Turned augmentation on and accuracy dropped — too strong is as bad as
     none** *(leaf #79)* — tune augmentation strength; `albumentations` for
     product-appropriate transforms
   - **You can't remember which config gave the 93% model** *(leaf #80)* —
     experiment tracking with Weights & Biases / MLflow
   - **Hand-tuning LR/batch size one at a time eats your week** *(leaf #81)* —
     `Optuna` search; unfreeze more of the backbone after the head converges
6. **Ship it** *(besmart task #58)*
   - **`torch.save(model)` artifacts won't load in production, and inference
     is noisy/slow** *(leaf #82)* — `state_dict` + rebuild architecture,
     `eval()` + `inference_mode()`
   - **Production needs a real API, not a notebook** *(leaf #83)* — export to
     ONNX; serve via ONNX Runtime, FastAPI, or TorchServe; batch requests
   - **Model too big/slow for the phone on the warehouse floor** *(leaf #84)*
     — dynamic/int8 quantization, smaller backbone, latency-vs-accuracy
     tradeoff
