from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath


DEFAULT_SPLIT_SEED = 20260921
ALLOWED_CATEGORIES = frozenset(
    {
        "bl_comparison",
        "new_si_request",
        "invoice_query",
        "general_message",
        "spam",
    }
)

_EMAIL_PATTERN = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
_URL_PATTERN = re.compile(r"https?://\S+", re.I)
_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,:/-]\d+)*\b")
_SI_PATTERN = re.compile(r"(?:^|[_-])si(?:[_\.-]|$)", re.I)
_BL_PATTERN = re.compile(r"(?:^|[_-])bl(?:[_\.-]|$)", re.I)


class SplitError(ValueError):
    pass


@dataclass(frozen=True)
class SplitRecord:
    email_id: str
    group_id: str
    attachment_pattern: str


@dataclass(frozen=True)
class StageASelection:
    annotation_pool: tuple[SplitRecord, ...]
    production: tuple[SplitRecord, ...]
    seed: int
    source_id_hash: str


@dataclass(frozen=True)
class StageBSelection:
    development: tuple[SplitRecord, ...]
    final_test: tuple[SplitRecord, ...]
    seed: int
    source_id_hash: str


class _UnionFind:
    def __init__(self, size: int):
        self._parent = list(range(size))
        self._rank = [0] * size

    def find(self, index: int) -> int:
        parent = self._parent[index]
        if parent != index:
            self._parent[index] = self.find(parent)
        return self._parent[index]

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self._rank[left_root] < self._rank[right_root]:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        if self._rank[left_root] == self._rank[right_root]:
            self._rank[left_root] += 1


def build_split_records(
    records: Sequence[Mapping[str, object]],
) -> tuple[SplitRecord, ...]:
    ordered_records = sorted(records, key=_email_id)
    email_ids = [_email_id(record) for record in ordered_records]
    if len(email_ids) != len(set(email_ids)):
        raise SplitError("Cannot group records with duplicate email IDs")

    union_find = _UnionFind(len(ordered_records))
    exact_first: dict[tuple[str, str], int] = {}
    template_first: dict[tuple[str, str], int] = {}

    for index, record in enumerate(ordered_records):
        subject = _required_string(record, "subject")
        body = _required_string(record, "body")
        exact_signature = (_normalize_text(subject), _normalize_text(body))
        template_signature = (
            _template_text(subject),
            _template_text(body),
        )
        _union_signature(exact_first, exact_signature, index, union_find)
        _union_signature(template_first, template_signature, index, union_find)

    members_by_root: dict[int, list[str]] = defaultdict(list)
    for index, email_id in enumerate(email_ids):
        members_by_root[union_find.find(index)].append(email_id)

    group_ids = {
        root: _stable_group_id(member_ids)
        for root, member_ids in members_by_root.items()
    }
    split_records = []
    for index, record in enumerate(ordered_records):
        split_records.append(
            SplitRecord(
                email_id=email_ids[index],
                group_id=group_ids[union_find.find(index)],
                attachment_pattern=_attachment_pattern(record),
            )
        )
    return tuple(split_records)


def select_annotation_pool(
    records: Sequence[Mapping[str, object]],
    pool_size: int = 120,
    seed: int = DEFAULT_SPLIT_SEED,
) -> StageASelection:
    split_records = build_split_records(records)
    if pool_size <= 0 or pool_size >= len(split_records):
        raise SplitError("Annotation pool size must be between 1 and source size - 1")

    patterns = tuple(sorted({record.attachment_pattern for record in split_records}))
    pattern_indexes = {pattern: index for index, pattern in enumerate(patterns)}
    source_vector = tuple(
        sum(record.attachment_pattern == pattern for record in split_records)
        for pattern in patterns
    )

    records_by_group: dict[str, list[SplitRecord]] = defaultdict(list)
    for record in split_records:
        records_by_group[record.group_id].append(record)

    ordered_groups = sorted(
        records_by_group,
        key=lambda group_id: _seeded_group_key(seed, group_id),
    )
    group_vectors = {
        group_id: _pattern_vector(
            records_by_group[group_id],
            pattern_indexes,
        )
        for group_id in ordered_groups
    }

    selected_groups = _select_groups(
        ordered_groups=ordered_groups,
        group_vectors=group_vectors,
        source_vector=source_vector,
        target_size=pool_size,
        require_pattern_coverage=True,
        prefer_both_sides=False,
        error_context="exact annotation pool",
    )

    annotation_pool = tuple(
        sorted(
            (
                record
                for record in split_records
                if record.group_id in selected_groups
            ),
            key=lambda record: record.email_id,
        )
    )
    production = tuple(
        sorted(
            (
                record
                for record in split_records
                if record.group_id not in selected_groups
            ),
            key=lambda record: record.email_id,
        )
    )
    return StageASelection(
        annotation_pool=annotation_pool,
        production=production,
        seed=seed,
        source_id_hash=_source_id_hash(record.email_id for record in split_records),
    )


def finalize_labeled_split(
    annotation_pool: Sequence[SplitRecord],
    labels: Mapping[str, str],
    development_size: int = 80,
    test_size: int = 40,
    seed: int = DEFAULT_SPLIT_SEED,
) -> StageBSelection:
    pool_ids = [record.email_id for record in annotation_pool]
    if len(pool_ids) != len(set(pool_ids)):
        raise SplitError("Annotation pool contains duplicate email IDs")
    if development_size <= 0 or test_size <= 0:
        raise SplitError("Development and final-test sizes must both be positive")
    if development_size + test_size != len(annotation_pool):
        raise SplitError(
            "Development and final-test sizes must equal annotation pool size"
        )

    pool_id_set = set(pool_ids)
    label_id_set = set(labels)
    missing_ids = sorted(pool_id_set - label_id_set)
    if missing_ids:
        raise SplitError(f"Annotation file has missing labels for {len(missing_ids)} IDs")
    unknown_ids = sorted(label_id_set - pool_id_set)
    if unknown_ids:
        raise SplitError(f"Annotation file has unknown label IDs: {unknown_ids[0]}")

    invalid_categories = sorted(
        {
            category
            for category in labels.values()
            if category not in ALLOWED_CATEGORIES
        }
    )
    if invalid_categories:
        raise SplitError(f"Annotation file has invalid category: {invalid_categories[0]}")

    categories = tuple(sorted(ALLOWED_CATEGORIES))
    category_indexes = {
        category: index for index, category in enumerate(categories)
    }
    source_vector = tuple(
        sum(labels[email_id] == category for email_id in pool_ids)
        for category in categories
    )

    records_by_group: dict[str, list[SplitRecord]] = defaultdict(list)
    for record in annotation_pool:
        records_by_group[record.group_id].append(record)
    ordered_groups = sorted(
        records_by_group,
        key=lambda group_id: _seeded_group_key(seed, group_id),
    )
    group_vectors = {}
    for group_id, group_records in records_by_group.items():
        vector = [0] * len(categories)
        for record in group_records:
            vector[category_indexes[labels[record.email_id]]] += 1
        group_vectors[group_id] = tuple(vector)

    selected_groups = _select_groups(
        ordered_groups=ordered_groups,
        group_vectors=group_vectors,
        source_vector=source_vector,
        target_size=test_size,
        require_pattern_coverage=False,
        prefer_both_sides=True,
        error_context="exact final test",
    )
    final_test = tuple(
        sorted(
            (
                record
                for record in annotation_pool
                if record.group_id in selected_groups
            ),
            key=lambda record: record.email_id,
        )
    )
    development = tuple(
        sorted(
            (
                record
                for record in annotation_pool
                if record.group_id not in selected_groups
            ),
            key=lambda record: record.email_id,
        )
    )
    if len(development) != development_size or len(final_test) != test_size:
        raise SplitError("Internal split size verification failed")

    return StageBSelection(
        development=development,
        final_test=final_test,
        seed=seed,
        source_id_hash=_source_id_hash(pool_ids),
    )


def _select_groups(
    ordered_groups: Sequence[str],
    group_vectors: Mapping[str, tuple[int, ...]],
    source_vector: tuple[int, ...],
    target_size: int,
    require_pattern_coverage: bool,
    prefer_both_sides: bool,
    error_context: str,
) -> frozenset[str]:
    zero_vector = (0,) * len(source_vector)
    states: dict[tuple[int, ...], tuple[str, ...]] = {zero_vector: ()}
    groups_by_vector: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for group_id in ordered_groups:
        groups_by_vector[group_vectors[group_id]].append(group_id)

    for group_vector, bucket_groups in groups_by_vector.items():
        next_states = dict(states)
        group_size = sum(group_vector)
        max_bucket_count = min(len(bucket_groups), target_size // group_size)
        for vector, selected_groups in states.items():
            for take_count in range(1, max_bucket_count + 1):
                candidate = tuple(
                    value + addition * take_count
                    for value, addition in zip(vector, group_vector, strict=True)
                )
                if sum(candidate) > target_size:
                    break
                next_states.setdefault(
                    candidate,
                    selected_groups + tuple(bucket_groups[:take_count]),
                )
        states = next_states

    candidates = [
        (vector, selected_groups)
        for vector, selected_groups in states.items()
        if sum(vector) == target_size
    ]
    if require_pattern_coverage:
        covered_candidates = [
            candidate
            for candidate in candidates
            if all(count > 0 for count in candidate[0])
        ]
        candidates = covered_candidates
    elif prefer_both_sides:
        covered_candidates = [
            candidate
            for candidate in candidates
            if all(
                source < 2 or 0 < selected < source
                for selected, source in zip(
                    candidate[0], source_vector, strict=True
                )
            )
        ]
        if covered_candidates:
            candidates = covered_candidates
    if not candidates:
        raise SplitError(
            f"Cannot create {error_context} of size {target_size} without splitting a group"
        )

    source_size = sum(source_vector)

    def candidate_key(
        item: tuple[tuple[int, ...], tuple[str, ...]],
    ) -> tuple[float, tuple[int, ...], tuple[str, ...]]:
        vector, selected_groups = item
        score = sum(
            (selected - source * target_size / source_size) ** 2
            for selected, source in zip(vector, source_vector, strict=True)
        )
        return score, vector, selected_groups

    _, selected_groups = min(candidates, key=candidate_key)
    return frozenset(selected_groups)


def _pattern_vector(
    records: Sequence[SplitRecord],
    pattern_indexes: Mapping[str, int],
) -> tuple[int, ...]:
    counts = [0] * len(pattern_indexes)
    for record in records:
        counts[pattern_indexes[record.attachment_pattern]] += 1
    return tuple(counts)


def _email_id(record: Mapping[str, object]) -> str:
    return _required_string(record, "email_id")


def _required_string(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str):
        raise SplitError(f"Record field {field} must be a string")
    return value


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _template_text(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = _EMAIL_PATTERN.sub("<email>", normalized)
    normalized = _URL_PATTERN.sub("<url>", normalized)
    normalized = _NUMBER_PATTERN.sub("<n>", normalized)
    return " ".join(normalized.split())


def _union_signature(
    first_indexes: dict[tuple[str, str], int],
    signature: tuple[str, str],
    index: int,
    union_find: _UnionFind,
) -> None:
    first_index = first_indexes.setdefault(signature, index)
    union_find.union(first_index, index)


def _stable_group_id(email_ids: Sequence[str]) -> str:
    value = "\n".join(sorted(email_ids)).encode("utf-8")
    return f"group_{hashlib.sha256(value).hexdigest()[:12]}"


def _source_id_hash(email_ids: Iterable[str]) -> str:
    ordered_ids = sorted(str(email_id) for email_id in email_ids)
    value = "\n".join(ordered_ids).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _seeded_group_key(seed: int, group_id: str) -> str:
    return hashlib.sha256(f"{seed}:{group_id}".encode("utf-8")).hexdigest()


def _attachment_pattern(record: Mapping[str, object]) -> str:
    attachments = record.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return "none"

    names = [
        PurePosixPath(str(attachment).replace("\\", "/")).name
        for attachment in attachments
    ]
    has_si = any(_SI_PATTERN.search(name) for name in names)
    has_bl = any(_BL_PATTERN.search(name) for name in names)
    if has_si and has_bl:
        return "si_bl"
    if has_si:
        return "si"
    if has_bl:
        return "bl"
    return "other"
