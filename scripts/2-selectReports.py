
import pandas as pd
from pathlib import Path

# ============================================================
# 1. CONFIGURATION — CHANGE THESE VALUES
# ============================================================

INPUT_CSV = Path("kreston_records.csv")
OUTPUT_CSV = Path("selected_dataset_list.csv")

RANDOM_SEED = 42

# Training set
TRAIN_UNMODIFIED = 800
TRAIN_MODIFIED = 800

# Validation set
VAL_UNMODIFIED = 169
VAL_MODIFIED = 31

# Test set
TEST_UNMODIFIED = 169
TEST_MODIFIED = 31


# ============================================================
# 2. AUDIT OPINION CATEGORIES
# ============================================================

UNMODIFIED_OPINIONS = [
    "Ý kiến chấp nhận toàn phần",
    "Ý kiến chấp nhận toàn phần, nhấn mạnh",
]

MODIFIED_OPINIONS = [
    "Ý kiến ngoại trừ",
    "Ý kiến trái ngược",
    "Ý kiến từ chối đưa ra ý kiến",
]

ADVERSE_OPINION = "Ý kiến trái ngược"

INPUT_COLUMNS = [
    "id",
    "id_report",
    "ky_bao_cao",
    "cong_ty",
    "mo_ta",
    "loai_bctc",
    "cong_ty_kiem_toan",
    "y_kien_kiem_toan",
    "link_gdrive",
    "link_vnreport",
]

OUTPUT_COLUMNS = INPUT_COLUMNS + ["set", "modified"]


# ============================================================
# 3. LOAD AND VALIDATE SOURCE DATA
# ============================================================

if not INPUT_CSV.exists():
    raise FileNotFoundError(
        f"Input CSV not found: {INPUT_CSV.resolve()}"
    )

df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")

missing_columns = [
    col for col in INPUT_COLUMNS if col not in df.columns
]

if missing_columns:
    raise ValueError(
        f"Missing required columns: {missing_columns}"
    )

# Keep only the required input columns and make a copy
df = df[INPUT_COLUMNS].copy()

# Normalize whitespace in opinion labels
df["y_kien_kiem_toan"] = (
    df["y_kien_kiem_toan"]
    .astype("string")
    .str.strip()
)

# Keep only recognized opinion categories
recognized_opinions = (
    UNMODIFIED_OPINIONS + MODIFIED_OPINIONS
)

unknown_mask = ~df["y_kien_kiem_toan"].isin(
    recognized_opinions
)

if unknown_mask.any():
    unknown_values = (
        df.loc[unknown_mask, "y_kien_kiem_toan"]
        .value_counts(dropna=False)
    )

    raise ValueError(
        "Some reports have missing or unrecognized audit opinions.\n"
        "Please inspect these values before continuing:\n"
        f"{unknown_values.to_string()}"
    )

# Assign binary labels
df["modified"] = (
    df["y_kien_kiem_toan"]
    .isin(MODIFIED_OPINIONS)
    .astype(int)
)

# Ensure each source row is uniquely identifiable
if df["id"].duplicated().any():
    raise ValueError(
        "Duplicate values found in the 'id' column. "
        "Resolve duplicates before sampling."
    )


# ============================================================
# 4. CHECK REQUESTED COUNTS
# ============================================================

requested = {
    "train": {0: TRAIN_UNMODIFIED, 1: TRAIN_MODIFIED},
    "val":   {0: VAL_UNMODIFIED,   1: VAL_MODIFIED},
    "test":  {0: TEST_UNMODIFIED,  1: TEST_MODIFIED},
}

if any(
    count < 0
    for split_counts in requested.values()
    for count in split_counts.values()
):
    raise ValueError("Requested counts cannot be negative.")

# All adverse-opinion reports must go into training
adverse_df = df[
    df["y_kien_kiem_toan"] == ADVERSE_OPINION
].copy()

number_of_adverse = len(adverse_df)

if TRAIN_MODIFIED < number_of_adverse:
    raise ValueError(
        f"Training requires at least {number_of_adverse} "
        "modified slots to include every adverse-opinion report."
    )

# Check whether enough reports exist for each class
available_unmodified = int((df["modified"] == 0).sum())
available_modified = int((df["modified"] == 1).sum())

required_unmodified = sum(
    counts[0] for counts in requested.values()
)
required_modified = sum(
    counts[1] for counts in requested.values()
)

if required_unmodified > available_unmodified:
    raise ValueError(
        f"Need {required_unmodified} unmodified reports, "
        f"but only {available_unmodified} are available."
    )

if required_modified > available_modified:
    raise ValueError(
        f"Need {required_modified} modified reports, "
        f"but only {available_modified} are available."
    )

# Adverse reports are reserved for training.
# Other modified reports must fill all remaining modified slots.
other_modified_required = required_modified - number_of_adverse

other_modified_available = df[
    (df["modified"] == 1)
    & (df["y_kien_kiem_toan"] != ADVERSE_OPINION)
]

if other_modified_required > len(other_modified_available):
    raise ValueError(
        "Not enough non-adverse modified reports available."
    )


# ============================================================
# 5. SELECT REPORTS RANDOMLY WITHOUT REPLACEMENT
# ============================================================

rng = RANDOM_SEED

# Every adverse-opinion report goes into training
train_adverse = adverse_df.copy()
train_adverse["set"] = "train"

# Select the remaining modified reports for each split.
# Adverse reports are excluded from this pool because
# they have already been reserved for training.
modified_pool = df[
    (df["modified"] == 1)
    & (df["y_kien_kiem_toan"] != ADVERSE_OPINION)
]

remaining_train_modified = (
    TRAIN_MODIFIED - number_of_adverse
)

train_modified = modified_pool.sample(
    n=remaining_train_modified,
    random_state=rng
).copy()

train_modified["set"] = "train"

used_modified_ids = set(train_modified["id"]) | set(
    train_adverse["id"]
)

modified_pool_remaining = modified_pool[
    ~modified_pool["id"].isin(used_modified_ids)
]

val_modified = modified_pool_remaining.sample(
    n=VAL_MODIFIED,
    random_state=rng + 1
).copy()

val_modified["set"] = "val"

used_modified_ids.update(val_modified["id"])

modified_pool_remaining = modified_pool[
    ~modified_pool["id"].isin(used_modified_ids)
]

test_modified = modified_pool_remaining.sample(
    n=TEST_MODIFIED,
    random_state=rng + 2
).copy()

test_modified["set"] = "test"


# Select unmodified reports
unmodified_pool = df[df["modified"] == 0]

train_unmodified = unmodified_pool.sample(
    n=TRAIN_UNMODIFIED,
    random_state=rng + 3
).copy()

train_unmodified["set"] = "train"

used_unmodified_ids = set(train_unmodified["id"])

unmodified_pool_remaining = unmodified_pool[
    ~unmodified_pool["id"].isin(used_unmodified_ids)
]

val_unmodified = unmodified_pool_remaining.sample(
    n=VAL_UNMODIFIED,
    random_state=rng + 4
).copy()

val_unmodified["set"] = "val"

used_unmodified_ids.update(val_unmodified["id"])

unmodified_pool_remaining = unmodified_pool[
    ~unmodified_pool["id"].isin(used_unmodified_ids)
]

test_unmodified = unmodified_pool_remaining.sample(
    n=TEST_UNMODIFIED,
    random_state=rng + 5
).copy()

test_unmodified["set"] = "test"


# Combine all selected reports
result = pd.concat(
    [
        train_adverse,
        train_modified,
        train_unmodified,
        val_modified,
        val_unmodified,
        test_modified,
        test_unmodified,
    ],
    ignore_index=True
)

# Shuffle rows within the output CSV
result = result.sample(
    frac=1,
    random_state=RANDOM_SEED
).reset_index(drop=True)

# Keep exactly the requested output columns
result = result[OUTPUT_COLUMNS]


# ============================================================
# 6. FINAL VALIDATION
# ============================================================

# No report may appear more than once
if result["id"].duplicated().any():
    raise RuntimeError("A report was selected more than once.")

# All adverse reports must be in training
selected_adverse = result[
    result["y_kien_kiem_toan"] == ADVERSE_OPINION
]

if len(selected_adverse) != number_of_adverse:
    raise RuntimeError("Not all adverse reports were included.")

if not (selected_adverse["set"] == "train").all():
    raise RuntimeError(
        "An adverse-opinion report was assigned outside training."
    )

# Verify counts for every split
for split_name, class_counts in requested.items():
    split_df = result[result["set"] == split_name]

    actual_unmodified = int(
        (split_df["modified"] == 0).sum()
    )
    actual_modified = int(
        (split_df["modified"] == 1).sum()
    )

    assert actual_unmodified == class_counts[0], (
        f"{split_name}: incorrect unmodified count"
    )
    assert actual_modified == class_counts[1], (
        f"{split_name}: incorrect modified count"
    )


# ============================================================
# 7. SAVE OUTPUT
# ============================================================

OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

result.to_csv(
    OUTPUT_CSV,
    index=False,
    encoding="utf-8-sig"
)

print("\nDataset list created successfully!")
print(f"Output: {OUTPUT_CSV.resolve()}")
print(f"Total reports: {len(result)}")
print(f"Adverse reports placed in training: {number_of_adverse}")

print("\nCounts by set and label:")
print(
    pd.crosstab(result["set"], result["modified"])
    .reindex(["train", "val", "test"])
    .rename(columns={0: "unmodified", 1: "modified"})
)

print("\nOpinion subcategories by set:")
print(
    pd.crosstab(
        result["set"],
        result["y_kien_kiem_toan"]
    ).reindex(["train", "val", "test"])
)
