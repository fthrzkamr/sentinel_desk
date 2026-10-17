"""Best-effort auto-linking of an incoming asset_dfm sync record to one of
this fleet's own Device rows. There is no shared identifier between the two
systems (no BIOS asset tag in use - see Asset's docstring) - the only
signals available are free-text "who holds this" and "which branch" from
asset_dfm, matched against SentinelDesk's own clean Employee/Branch data via
the device each employee is currently assigned. This is intentionally a
plain string-similarity heuristic, not a call to an LLM: the inputs are
short, structured-ish strings (a name, a city), and difflib's ratio on them
is fast, free, and exactly as predictable as this kind of fuzzy lookup needs
to be - a real AI call would add latency and cost for a problem that doesn't
need language understanding, just approximate string matching.

Every match is provisional until kept or overridden by an admin: a
confident match still shows up as AUTO_MATCHED (not silently "done"), and
anything under the threshold is left for manual review rather than guessed.
"""

import difflib

from .models import Asset, Device, Employee

# Below this, a guess is more likely to be wrong than right - leave it for a
# human instead of silently mis-linking someone else's laptop.
AUTO_MATCH_THRESHOLD = 0.72
# Below THIS, don't even show a suggested_device - plenty of asset_dfm `user`
# values are department/role labels with no name in them at all ("IT", "HR",
# "Admin Gudang T6"), and comparing a short, name-less label against a full
# name via plain character-overlap ratio produces a misleadingly nonzero
# score from sheer coincidence (e.g. "IT" vs "Azka Aulia" shares an "i" and
# an "a"), not from any real partial match. A guess that isn't at least
# this confident does more harm than good - it reads as "the system thinks
# this is Azka" when it's actually just two letters in common.
SUGGEST_THRESHOLD = 0.55
# A token shorter than this can never carry a fuzzy-ratio score on its own -
# only an exact match to a whole word in the target counts. Without this,
# two-letter department codes ("IT", "HR", "GA") coincidentally overlap
# enough characters with almost any name to score nonzero.
MIN_FUZZY_TOKEN_LEN = 3
NAME_WEIGHT = 0.75
BRANCH_WEIGHT = 0.25
# Raw text meaning "this is a spare/pool laptop, not assigned to one
# person" - NOT the same thing as a department label with no name filled
# in yet ("Sales Surabaya", "Finance Bekasi" - those ARE actively used by
# a specific employee, asset_dfm's data entry just didn't name them; the
# fix there is correcting that data, not guessing a device). Deliberately
# a narrow, exact set rather than reusing DEPARTMENT_WORDS/
# _is_department_label wholesale - confirmed with the company that only
# a bare "IT" means genuinely unclaimed, see _find_spare_device_candidate.
SPARE_LABELS = {"it"}


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _name_candidates(raw_name: str) -> list[str]:
    """asset_dfm's `user` field is often "Name - Role" (e.g. "Hamal -
    Apoteker") or just a role with no name at all ("IT - KEPALA GUDANG") -
    trying the text before the first " - " as its own candidate catches the
    common case without needing to guess which half, if either, is a real
    name. Matching against the full raw string too costs nothing and still
    wins when there's no " - " separator at all."""
    normalized = _normalize(raw_name)
    candidates = [normalized]
    if " - " in normalized:
        candidates.append(normalized.split(" - ", 1)[0].strip())
    elif "-" in normalized:
        candidates.append(normalized.split("-", 1)[0].strip())
    return [c for c in candidates if c]


def _string_pair_score(word_a: str, word_b: str) -> float:
    """Exact match / substring / near-typo scoring for two strings - used
    both word-against-word AND, for a multi-word candidate, whole-phrase
    against whole-phrase (see _name_score). Short strings (department
    codes, initials) skip the fuzzy ratio entirely and only score on an
    exact match - see MIN_FUZZY_TOKEN_LEN."""
    if len(word_a) < MIN_FUZZY_TOKEN_LEN or len(word_b) < MIN_FUZZY_TOKEN_LEN:
        return 1.0 if word_a == word_b else 0.0
    if word_a == word_b:
        return 1.0
    if word_a in word_b or word_b in word_a:
        # A full short word embedded in a longer one ("hamal" inside
        # "hamalyusuf", not that this spacing would normally happen, but
        # also "hamal" == a token on its own already handled above) - still
        # worth a strong score, same reasoning as the old substring bonus.
        return 0.85
    # A real typo ("fathi" vs "fathy") sits well above this; two different
    # Indonesian names sharing a vowel-heavy pattern ("aprilia" vs "aulia",
    # ratio 0.67) sit well below it. Below the floor, treat it as zero
    # signal rather than a discounted one - a mushy 0.5-0.7 ratio from two
    # unrelated names was clearing SUGGEST_THRESHOLD once combined with a
    # branch-match bonus, which is worse than just saying "no idea".
    ratio = difflib.SequenceMatcher(None, word_a, word_b).ratio()
    return ratio if ratio >= 0.8 else 0.0


def _name_score(raw_name: str, employee_full_name: str) -> float:
    """A single-word candidate ("Azka", "Hamal") is a plausible nickname or
    first name - matched against ANY one word of the employee's full name.
    A multi-word candidate is compared as a WHOLE PHRASE against the whole
    target name instead of word-by-word - two different people can easily
    share one common given-name fragment ("Rizki Ardi Bachtiar" vs "Fathi
    Rizki Ammar" both contain "Rizki"), and crediting that single shared
    word as "found the name" would treat two different employees as the
    same person. Comparing full phrases means a real match still needs the
    *whole* name to line up, not just a fragment of it."""
    if not raw_name or not employee_full_name:
        return 0.0
    target = _normalize(employee_full_name)
    best = 0.0
    for candidate in _name_candidates(raw_name):
        candidate_words = candidate.split(" ")
        if len(candidate_words) == 1:
            for target_word in target.split(" "):
                best = max(best, _string_pair_score(candidate_words[0], target_word))
        else:
            best = max(best, _string_pair_score(candidate, target))
    return best


def _branch_score(raw_lokasi: str, device: Device) -> float:
    if not raw_lokasi or not device.branch:
        return 0.0
    return 1.0 if _normalize(raw_lokasi) == _normalize(device.branch.name) else 0.0


def _find_spare_device_candidate(raw_lokasi: str) -> tuple[Device | None, float]:
    """For a genuinely-unclaimed asset ("IT" - see SPARE_LABELS) there's no
    person's name to match on at all, so the only plausible candidates are
    SentinelDesk devices nobody's claimed either (no assigned_employee -
    this fleet's own way of saying "this is a pool/spare laptop"),
    narrowed by branch when a candidate device has one set. Only ever
    returned as a suggestion (never confident enough to clear
    AUTO_MATCH_THRESHOLD) when there's EXACTLY one such device: with two
    or more equally-unclaimed spares, nothing distinguishes them, so
    picking one would be a coin flip dressed up as a match - left fully
    manual instead (the Assets page's "Tautkan Lain" already lists
    employee-less devices too, so this isn't a dead end for the admin).

    Excludes a device some OTHER asset already has an active link to
    (device FK set, condition not Hilang/Dihapus) - without this, every
    "IT"-labeled asset independently sees the same single spare device as
    "the one candidate" and keeps suggesting it even after one of them has
    already claimed it.

    Deliberately does NOT also require this to be the only pending asset
    competing for that device - with seven "IT" assets and one actual
    spare device enrolled, only one of the seven can really be it, but
    there's no way to tell which from text alone, and suppressing the
    suggestion for all seven throws away real information (the admin can
    still eyeball nama_aset/merk/spesifikasi via the asset's View button
    against the physical laptop and confirm the right one). Confirming the
    wrong one is caught by AssetLinkView's own duplicate-link guard, which
    now returns a specific, visible error instead of silently rejecting -
    see confirmSuggestion() on the frontend."""
    already_claimed_ids = set(
        Asset.objects.filter(device__isnull=False)
        .exclude(kondisi__in=[Asset.Condition.HILANG, Asset.Condition.DIHAPUS])
        .values_list("device_id", flat=True)
    )
    unclaimed = [
        d
        for d in Device.objects.filter(assigned_employee__isnull=True).select_related("branch")
        if d.id not in already_claimed_ids
    ]
    if raw_lokasi:
        same_branch = [d for d in unclaimed if d.branch and _normalize(d.branch.name) == _normalize(raw_lokasi)]
        if same_branch:
            unclaimed = same_branch
    if len(unclaimed) != 1:
        return None, 0.0
    return unclaimed[0], SUGGEST_THRESHOLD


def find_best_match(raw_penanggung_jawab: str, raw_lokasi: str) -> tuple[Device | None, float]:
    """Only considers devices that already have an assigned employee - with
    no name to compare against, there's nothing to match on, and leaving an
    employee-less device out of contention also means it can't accidentally
    outrank a real candidate on branch score alone.

    Returns (None, 0.0) - no candidate at all, not just a weak one - unless
    something cleared SUGGEST_THRESHOLD, so a department/role label with no
    real name in it ("IT", "HR", "Admin Gudang T6") comes back as "nothing
    to suggest" rather than whichever employee happened to share the most
    letters with it.

    Cross-checked against find_employee_by_name() before accepting a
    device: this function only ever compares against the handful of
    employees who happen to already have an enrolled device, so a raw name
    that's a near-miss for one of THEM ("Auliya" vs "Azka Aulia" - 0.909,
    from the shared "Aulia") can out-score the real match even when the
    actual person ("Auliya Nurul Haqim") exists in SentinelDesk but just
    doesn't have a device yet. find_employee_by_name() searches every
    employee, not just device-holders, so it's the more reliable read of
    "who is this really" - a device is only accepted here when it agrees
    with that answer (or when no confident employee match exists at all,
    e.g. the raw text doesn't clear EMPLOYEE_MATCH_THRESHOLD either way).

    A bare "IT" (SPARE_LABELS) skips all of the above entirely and goes
    through _find_spare_device_candidate() instead - there's no name in
    it to resolve against anyone, by design (it means "spare", not "an
    employee named IT")."""
    if _normalize(raw_penanggung_jawab) in SPARE_LABELS:
        return _find_spare_device_candidate(raw_lokasi)
    resolved_employee = find_employee_by_name(raw_penanggung_jawab)
    candidates = Device.objects.select_related("assigned_employee", "branch").filter(
        assigned_employee__isnull=False
    )
    best_device = None
    best_score = 0.0
    for device in candidates:
        if resolved_employee and device.assigned_employee_id != resolved_employee.id:
            continue  # a different, more confident employee match exists - this isn't their laptop
        name_score = _name_score(raw_penanggung_jawab, device.assigned_employee.full_name)
        if name_score == 0.0:
            continue  # no name signal at all - branch alone is too weak to act on
        branch_score = _branch_score(raw_lokasi, device)
        combined = NAME_WEIGHT * name_score + BRANCH_WEIGHT * branch_score
        if combined > best_score:
            best_score = combined
            best_device = device
    if best_score < SUGGEST_THRESHOLD:
        return None, 0.0
    return best_device, best_score


def sync_asset(
    *,
    asset_code: str,
    kondisi: str,
    status_barang: str,
    penanggung_jawab: str,
    lokasi: str,
    nama_aset: str = "",
    merk: str = "",
    spesifikasi: str = "",
    lokasi_detail: str = "",
) -> Asset:
    """Upserts by asset_code (asset_dfm is the source of truth for these
    fields, so a later sync always overwrites them) and re-runs matching
    every time - a laptop's holder in asset_dfm can change between syncs,
    and a manually-fixed link (LINKED_MANUALLY) is deliberately the one
    status this never overwrites, since that already reflects an admin's
    explicit, presumably-correct decision."""
    asset, _created = Asset.objects.get_or_create(asset_code=asset_code)
    asset.kondisi = kondisi
    asset.status_barang = status_barang
    asset.raw_penanggung_jawab = penanggung_jawab
    asset.raw_lokasi = lokasi
    asset.nama_aset = nama_aset
    asset.merk = merk
    asset.spesifikasi = spesifikasi
    asset.lokasi_detail = lokasi_detail

    # A damaged/lost/retired unit can't physically be the laptop behind any
    # active Device, no matter how well its name/branch text scores - auto-
    # matching one anyway (confirmed live: a "Rusak Berat" asset got
    # suggested as a match candidate for a perfectly working device) is
    # always wrong, not just low-confidence. Left UNLINKED/no suggestion
    # rather than guessed - kondisi itself is the "tandai rusak" marker,
    # already visible as its own column wherever Asset is shown.
    not_matchable = asset.kondisi != Asset.Condition.BAIK
    if not_matchable:
        asset.device = None
        asset.suggested_device = None
        asset.match_status = Asset.MatchStatus.UNLINKED
        asset.match_confidence = None
    elif asset.match_status != Asset.MatchStatus.LINKED_MANUALLY:
        device, score = find_best_match(penanggung_jawab, lokasi)
        if device and score >= AUTO_MATCH_THRESHOLD:
            asset.device = device
            asset.suggested_device = None
            asset.match_status = Asset.MatchStatus.AUTO_MATCHED
            asset.match_confidence = round(score, 3)
            # Convenience pre-fill only - see current_employee's docstring.
            # Never overwrites an admin's own choice once one has been made.
            if asset.current_employee_id is None:
                asset.current_employee = device.assigned_employee
                asset.user_status = Asset.UserStatus.IDENTIFIED
        else:
            asset.device = None
            # Kept even though it's below the auto-match bar - see
            # suggested_device's docstring: this is what lets the Assets
            # page show "mungkin <nama>" instead of a blank review row.
            asset.suggested_device = device
            asset.match_status = Asset.MatchStatus.NEEDS_REVIEW if device else Asset.MatchStatus.UNLINKED
            asset.match_confidence = round(score, 3) if device else None

    classify_user(asset)
    asset.save()
    return asset


# Role/department words that regularly show up in asset_dfm's `user` field
# instead of (or alongside) an actual person's name - "IT", "Sales
# Banjarmasin", "Mayla HR" (that last one IS a name, "HR" is just tacked on
# as a department). Checked word-by-word, not against the whole string, so
# a real name that happens to share a sentence with a department word still
# gets through. Lowercase, matched after normalization.
DEPARTMENT_WORDS = {
    "it", "hr", "ga", "admin", "sales", "finance", "accounting", "marketing",
    "gudang", "apoteker", "kepala", "direktur", "manager", "manajer",
    "supervisor", "staff", "karyawan", "analis", "data", "ttk", "kacab",
    "asisten", "asmen", "operasional", "leader", "driver", "kurir",
    "security", "cleaning", "service", "teknisi", "mekanik", "apj",
}
# asset_dfm's own lokasi_asset table (see its dump) - a "Sales <City>"
# label is a department+branch pairing, not a person, so these need
# excluding the same way DEPARTMENT_WORDS are.
BRANCH_CITY_WORDS = {
    "jakarta", "bekasi", "cibinong", "bali", "medan", "surabaya", "malang",
    "banjarmasin", "gorontalo", "palembang",
}
# Below this, matching a name against SentinelDesk's whole Employee list
# (not just employees with a device, which already have the branch-score
# fallback find_best_match gets) needs to be stricter - there's no second
# signal here to corroborate a borderline word-similarity score.
EMPLOYEE_MATCH_THRESHOLD = 0.8


def _is_department_label(raw_text: str) -> bool:
    """True once every word in raw_text is accounted for by a department
    word, a branch city name, or is too short to be a name on its own -
    i.e. nothing is left that looks like it could be an actual person."""
    words = _normalize(raw_text).replace("-", " ").split()
    if not words:
        return True
    for word in words:
        if word in DEPARTMENT_WORDS or word in BRANCH_CITY_WORDS:
            continue
        if len(word) >= MIN_FUZZY_TOKEN_LEN:
            return False
    return True


def find_employee_by_name(raw_name: str) -> Employee | None:
    """Same word/phrase scoring as find_best_match above, but against every
    Employee in the system rather than only those already holding a
    device - this is the fallback for an asset whose laptop isn't enrolled
    at all yet, so there's no Device to search through in the first place."""
    best_employee = None
    best_score = 0.0
    for employee in Employee.objects.all():
        score = _name_score(raw_name, employee.full_name)
        if score > best_score:
            best_score = score
            best_employee = employee
    return best_employee if best_score >= EMPLOYEE_MATCH_THRESHOLD else None


def rematch_unlinked_assets(device: Device) -> None:
    """Call whenever a Device gets an assigned_employee - at enrollment, a
    re-enroll, or an admin's later org-assignment PATCH. Matching otherwise
    only ever runs when asset_dfm pushes a sync (see sync_asset), so an
    asset synced before this laptop ever had SentinelDesk installed would
    sit UNLINKED/NEEDS_REVIEW forever afterward, waiting on a next
    asset_dfm edit that might not come for months. Re-running sync_asset
    on every not-yet-confirmed asset re-evaluates them against the fleet
    as it now stands, including this device - cheap enough at this
    dataset's size to just do on every assignment change rather than
    trying to pre-filter to "could plausibly be this employee"."""
    if not device.assigned_employee_id:
        return
    candidates = Asset.objects.filter(device__isnull=True).exclude(
        match_status=Asset.MatchStatus.LINKED_MANUALLY
    )
    for asset in candidates:
        sync_asset(
            asset_code=asset.asset_code,
            kondisi=asset.kondisi,
            status_barang=asset.status_barang,
            penanggung_jawab=asset.raw_penanggung_jawab,
            lokasi=asset.raw_lokasi,
            nama_aset=asset.nama_aset,
            merk=asset.merk,
            spesifikasi=asset.spesifikasi,
            lokasi_detail=asset.lokasi_detail,
        )


SPEC_SUGGEST_THRESHOLD = 0.3


def _spec_score(device_text: str, asset_text: str) -> float:
    """Word-overlap (Jaccard) comparison between a device's own reported
    model/system_family and an asset_dfm record's free-text item name -
    independent of employee-name text entirely, for the case where a
    freshly-enrolled device has no assigned employee yet to compare
    against in the first place. Jaccard rather than a plain character
    sequence ratio: the same physical model routinely gets written in a
    different word order / with or without the brand prefix across
    records ("Lenovo Thinkpad X13" vs "ThinkPad X13 Gen 1"), which a
    straight sequence ratio penalizes far more than it should."""
    device_words = set(_normalize(device_text).split())
    asset_words = set(_normalize(asset_text).split())
    if not device_words or not asset_words:
        return 0.0
    overlap = device_words & asset_words
    union = device_words | asset_words
    return len(overlap) / len(union)


def find_asset_candidates_by_spec(device: Device, limit: int = 8) -> list[tuple[Asset, float]]:
    """For a Device nobody has assigned an employee to yet - the exact
    case name-based matching has nothing to work from - suggest candidate
    Assets by comparing the device's OWN reported hardware against each
    still-unclaimed asset's free-text item name instead. Confirmed live:
    this can't fully disambiguate when the company bought several
    identical units (asset_dfm tracks no serial number to tell them
    apart), so this surfaces every plausible candidate ranked by
    similarity for a human to pick from - never auto-links on its own,
    unlike the name-based path in sync_asset()."""
    device_text = device.system_family or device.model
    if not device_text:
        return []
    candidates = Asset.objects.filter(kondisi=Asset.Condition.BAIK).exclude(
        match_status__in=[Asset.MatchStatus.LINKED_MANUALLY, Asset.MatchStatus.AUTO_MATCHED]
    )
    scored = []
    for asset in candidates:
        if not asset.nama_aset:
            continue
        score = _spec_score(device_text, asset.nama_aset)
        if score >= SPEC_SUGGEST_THRESHOLD:
            scored.append((asset, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def classify_user(asset: Asset) -> None:
    """Fills in current_employee/user_status when nothing set one already
    (device-based matching above, or an admin's own edit via
    AssetSetUserView) - never overwrites either. Three outcomes: a real
    Employee found by name (IDENTIFIED), a real-looking name with no
    matching Employee record yet (NEEDS_EMPLOYEE - add them as an Employee,
    or this will keep landing here), or asset_dfm's text wasn't a person at
    all (INCOMPLETE - a department/role label, nothing to identify)."""
    if asset.current_employee_id is not None:
        return
    raw = asset.raw_penanggung_jawab
    # A bare "IT" (SPARE_LABELS) means a real, known pool: the company's
    # IT department, not "nobody" - unlike other department labels
    # ("Sales Surabaya" etc, still INCOMPLETE below), there IS a specific
    # Employee record for this, so it's as confident an answer as any
    # name match. Falls through to the generic INCOMPLETE case if nobody
    # has created that placeholder Employee yet - see find_best_match's
    # own IT-specific handling for devices for the symmetric case.
    if raw and _normalize(raw) in SPARE_LABELS:
        it_employee = Employee.objects.filter(full_name__iexact="IT").first()
        if it_employee:
            asset.current_employee = it_employee
            asset.user_status = Asset.UserStatus.IDENTIFIED
            return
    if not raw or _is_department_label(raw):
        asset.user_status = Asset.UserStatus.INCOMPLETE
        return
    employee = find_employee_by_name(raw)
    if employee:
        asset.current_employee = employee
        asset.user_status = Asset.UserStatus.IDENTIFIED
    else:
        asset.user_status = Asset.UserStatus.NEEDS_EMPLOYEE
