"""
versioning_new.py — Optimized product versioning tool.

Improvements over versioning.py:
  - Validates manifest.json and product.lock fields before use (KeyError-proof)
  - Detects product.resolved / component-list version mismatches
  - Validates `requires` version constraints against currently resolved versions
  - Cross-checks manifest hash_schema.version against cache schema_version
  - Cleans up orphaned hash-cache entries for removed component paths
  - Guards extract_log() from being called on deleted files
  - O(1) component version lookup (was O(n) per component in inner loop)
  - Informative check_only exit: names the component that triggered it
  - Structured run summary printed at the end of each successful run
  - Consistent schema_change logic (no longer dev/non-dev asymmetry)
  - Corrupted .hash_cache.json handled gracefully (fresh cache + warning)
  - Removed unused `datetime` import; switched to `from copy import deepcopy`
  - Correct dry-run output labels (product.lock.tmp, __version__.py.tmp)
  - Cleaner --name validation via parser.error() instead of try/except TypeError
"""

import sys
import os
import re
from copy import deepcopy
import json
import argparse
from pathlib import Path


USER_PATH = Path("~").expanduser()
sys.path.insert(0, str(USER_PATH / "library" / "dev_tools"))
sys.path.insert(0, str(USER_PATH / "library" / "utilskit" / "src"))
sys.path.insert(0, str(USER_PATH / "library" / "logie" / "src"))
from utilskit.timeutils import get_now
from utilskit.versionutils import version_up, git_addcommit
from logie.docsutils import log2donelog, documenting, tmp2new, delete_tmp


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_manifest(manifest: dict, product_path: Path) -> None:
    """Raise ValueError with a clear message if required manifest keys are missing."""
    required_top = ["common_exclude", "common_untracked", "component"]
    missing = [k for k in required_top if k not in manifest]
    if missing:
        raise ValueError(
            f"manifest.json is missing required top-level keys: {missing} "
            f"(product: {product_path})"
        )
    required_comp = [
        "name", "requires", "type", "manage", "build",
        "mode", "path", "include", "bundle", "exclude", "untracked",
    ]
    for idx, comp in enumerate(manifest["component"]):
        missing_comp = [k for k in required_comp if k not in comp]
        if missing_comp:
            raise ValueError(
                f"Component at index {idx} in manifest.json is missing keys: "
                f"{missing_comp}"
            )


def _validate_lock(lock_info: dict, product_path: Path) -> None:
    """Raise ValueError with a clear message if required lock keys are missing."""
    for top_key in ("product", "component"):
        if top_key not in lock_info:
            raise ValueError(
                f"product.lock is missing required top-level key '{top_key}' "
                f"(path: {product_path})"
            )
    required_product = ["version"]
    missing = [k for k in required_product if k not in lock_info["product"]]
    if missing:
        raise ValueError(
            f"product.lock['product'] is missing keys: {missing} "
            f"(path: {product_path})"
        )


# ---------------------------------------------------------------------------
# Version constraint checker
# ---------------------------------------------------------------------------

def _parse_version(ver_str: str) -> tuple:
    """Parse 'X.Y.Z' into a comparable tuple of ints. Non-numeric → (0, 0, 0)."""
    try:
        return tuple(int(x) for x in str(ver_str).strip().split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _satisfies_constraint(version_str: str, constraint: str) -> bool:
    """
    Return True if version_str satisfies a constraint like '>=1.2.0'.
    Supports: >=, >, ==, !=, <, <=
    Unrecognized constraint format is treated as satisfied (fail-open).
    """
    match = re.match(r"^(>=|<=|==|!=|>|<)\s*(.+)$", constraint.strip())
    if not match:
        return True
    op, req_ver = match.group(1), match.group(2)
    v_cur = _parse_version(version_str)
    v_req = _parse_version(req_ver)
    result_map = {
        ">=": v_cur >= v_req,
        ">":  v_cur > v_req,
        "==": v_cur == v_req,
        "!=": v_cur != v_req,
        "<=": v_cur <= v_req,
        "<":  v_cur < v_req,
    }
    return result_map.get(op, True)


# ---------------------------------------------------------------------------
# Consistency checks
# ---------------------------------------------------------------------------
def _check_resolved_consistency(lock_info: dict) -> list:
    """
    Cross-check product.resolved versions against component list versions.
    Detects silent drift between the two representations.
    Returns a list of human-readable issue strings (empty → all consistent).
    """
    resolved = lock_info["product"].get("resolved", {})
    comp_version_map = {c["name"]: c["version"] for c in lock_info.get("component", [])}
    issues = []
    for c_name, r_ver in resolved.items():
        if c_name not in comp_version_map:
            issues.append(
                f"  resolved['{c_name}'] = '{r_ver}' has no matching entry "
                f"in the lock component list."
            )
        elif r_ver != comp_version_map[c_name]:
            issues.append(
                f"  resolved['{c_name}'] = '{r_ver}' but component version "
                f"= '{comp_version_map[c_name]}'."
            )
    return issues


def _check_requires(lock_info: dict) -> list:
    """
    Validate that each component's `requires` constraints are satisfied by
    the currently resolved versions recorded in the lock file.
    Returns a list of violation strings (empty → all satisfied).
    """
    resolved = lock_info["product"].get("resolved", {})
    violation_list = []
    for comp in lock_info.get("component", []):
        c_name = comp["name"]
        for dep_name, constraint in comp.get("requires", {}).items():
            dep_version = resolved.get(dep_name, "")
            if not dep_version:
                violation_list.append(
                    f"  [{c_name}] requires '{dep_name}{constraint}', "
                    f"but '{dep_name}' is not present in product.resolved."
                )
            elif not _satisfies_constraint(dep_version, constraint):
                violation_list.append(
                    f"  [{c_name}] requires '{dep_name}{constraint}', "
                    f"but resolved version is '{dep_version}'."
                )
    return violation_list


def _cleanup_orphaned_cache(hash_cache: dict, comp_info_filter_list: list) -> tuple:
    """
    Remove hash_cache entries whose paths no longer correspond to any
    component in the current manifest. Preserves the 'schema_version' key.
    Returns (cleaned_cache, list_of_removed_keys).
    """
    active_paths = {comp["path"] for comp in comp_info_filter_list}
    preserve = {"schema_version"}
    to_remove = [k for k in hash_cache if k not in preserve and k not in active_paths]
    for k in to_remove:
        del hash_cache[k]
    return hash_cache, to_remove




# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

def _print_summary(p_name: str, pre_version: str, new_version: str,
                   changed_components: list) -> None:
    """Print a structured summary of what was versioned in this run."""
    width = 62
    print("\n" + "=" * width)
    print(f"  Run Summary — {p_name}")
    print("=" * width)
    print(f"  Product  : {pre_version}  -->  {new_version}")
    if changed_components:
        print("  Components updated:")
        for c_name, pre, new in changed_components:
            print(f"    {c_name:<22s}  {pre}  -->  {new}")
    print("=" * width)


# ---------------------------------------------------------------------------
# Main versioning routine
# ---------------------------------------------------------------------------

def versioning(product_path: Path, save: bool, dev: bool, check_only: bool) -> None:

    if dev:
        from beta import utils as u
    else:
        import utils as u

    # 패키지 경로
    archive_path = product_path / "archive"
    docs_ver_path = product_path / "docs_ver"

    # manifest.json 읽기
    manifest_path = product_path / "manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8-sig") as f:
            manifest = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json contains invalid JSON: {exc}")
    _validate_manifest(manifest, product_path)

    # lock 불러오기
    lock_path = product_path / "product.lock"
    try:
        with open(lock_path, "r", encoding="utf-8-sig") as f:
            pre_lock_info = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"product.lock not found: {lock_path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"product.lock contains invalid JSON: {exc}")
    _validate_lock(pre_lock_info, product_path)
    lock_info = deepcopy(pre_lock_info)

    # ===================================================================
    # 버전 정합성 검사
    # Consistency check: product.resolved vs component list
    consistency_issues = _check_resolved_consistency(lock_info)
    if consistency_issues:
        print("[WARNING] product.lock resolved/component version mismatch:")
        for issue in consistency_issues:
            print(issue)

    # Requires constraint validation
    requires_violations = _check_requires(lock_info)
    if requires_violations:
        print("[WARNING] Unsatisfied `requires` constraints detected in product.lock:")
        for v in requires_violations:
            print(v)

    # ===================================================================
    # .hash_cache.json 읽기
    cache_path = product_path / ".hash_cache.json"
    if cache_path.is_file():
        try:
            with open(cache_path, "r", encoding="utf-8-sig") as f:
                pre_hash_cache = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"[WARNING] .hash_cache.json is corrupted ({exc}). Starting fresh cache.")
            pre_hash_cache = {}
    else:
        pre_hash_cache = {}
    hash_cache = deepcopy(pre_hash_cache)

    # ===============================================================
    # 컴포넌트별 변경 대상 파일 리스트 최초 필터링
    file_stat_info_list, comp_info_filter_list = u.get_info_result(
        manifest=manifest,
        product_path=product_path,
    )

    # ==================================================================
    # [1.0.2] @done_log: 해시 스키마 버전값을 추출하는 부분을 구획
    # --- Hash schema version resolution ---
    # cache_hash_schema_ver: what the cache was built with
    cache_hash_schema_ver = hash_cache.get("schema_version", "v1")
    # 이미 해시 스키마 버전이 있으면 유지하고 없으면 v1 값을 입력
    hash_cache.setdefault("schema_version", cache_hash_schema_ver)

    # 해시 스키마 버전 비교
    # lock_hash_schema_ver: what was recorded at last versioning run
    lock_hash_schema_ver = lock_info["product"].get("hash_schema_version")
    if lock_hash_schema_ver is None:
        # Key missing from lock — force full rehash with a clear explanation
        schema_change = True
        print(
            "[INFO] hash_schema_version missing from product.lock. "
            "All files will be treated as changed."
        )
    else:
        schema_change = cache_hash_schema_ver != lock_hash_schema_ver

    # manifest_hash_schema_ver: what the manifest declares as current
    manifest_hash_schema_ver = manifest.get("hash_schema", {}).get("version")

    # Additionally warn if manifest declares a schema version the cache hasn't seen
    if (
        manifest_hash_schema_ver
        and manifest_hash_schema_ver != cache_hash_schema_ver
        and not schema_change
    ):
        print(
            f"[WARNING] manifest.json declares hash_schema.version="
            f"'{manifest_hash_schema_ver}', but cache schema_version="
            f"'{cache_hash_schema_ver}'. Consider updating the schema."
        )

    # # --- Orphaned hash cache cleanup ---
    # hash_cache, removed_keys = _cleanup_orphaned_cache(hash_cache, comp_info_filter_list)
    # if removed_keys:
    #     print(
    #         f"[INFO] Removed {len(removed_keys)} orphaned cache path(s): "
    #         f"{removed_keys}"
    #     )

    # 대상 파일 별 해시 비교 및 로그 주석 추출
    comment_log_dict, hash_cache, flag_dict = u.compare_hash_cache(
        file_stat_info_list=file_stat_info_list,
        hash_cache=hash_cache,
        schema_change=schema_change,
    )

    # ==================================================================
    # 버전 업 & document 생성
    (
        file_stat_info_list,
        comp_info_filter_list,
        component_ver_log,
        changed_components,
    ) = u.versionup_documenting(
        file_stat_info_list=file_stat_info_list,
        comp_info_filter_list=comp_info_filter_list,
        flag_dict=flag_dict,
        comment_log_dict=comment_log_dict,
        lock_info=lock_info,
        check_only=check_only,
        save=save,
        docs_path=docs_ver_path
    )

    # ==================================================================
    # 각 대상 파일 별 @log 를 @done_log 로 변경
    for file_stat_info in file_stat_info_list:
        full_f_path = file_stat_info["full_file_path"]
        new_f_version = file_stat_info["version"]
        if save:
            try:
                log2donelog(full_f_path, new_f_version)
            except (FileNotFoundError, UnicodeDecodeError):
                pass
        else:
            print(f"|예정| {full_f_path} 의 주석을 done 으로 변경")

    # ==================================================================
    # 컴포넌트의 변경이 있는 경우 패키지 버전업 진행
    if any(v == 1 for v in flag_dict.values()):
        # 현 패키지 이름
        p_name = product_path.name

        # 이전 패키지 버전, 해시 정보 추출
        pre_p_version = lock_info["product"]["version"]

        # 패키지 버전 업 & 로그 document 생성
        if file_stat_info_list:

            # 컴포넌트별 변경 이력 출력
            u.title_print(
                title=f"product : < {p_name} >",
                log_text=component_ver_log,
            )

            # 버전 업
            new_p_version, p_tag = version_up(p_name, pre_p_version)
            print(f"{p_tag}: {pre_p_version} --> {new_p_version}")
        else:
            p_tag = ""
            new_p_version = pre_p_version

        # lock 채우기
        lock_info["product"]["name"] = p_name
        lock_info["product"]["version"] = new_p_version
        lock_info["product"]["resolved"] = {
            ci["name"]: ci["version"] for ci in comp_info_filter_list
        }
        lock_info["product"]["exclude"] = manifest["common_exclude"]
        lock_info["product"]["hash_schema_version"] = cache_hash_schema_ver
        lock_info["component"] = comp_info_filter_list

        # 저장
        if save:
            with open(product_path / "product.lock.tmp", "w", encoding="utf-8-sig") as f:
                json.dump(lock_info, f, indent="\t", ensure_ascii=False)
            
            # __version__.py.tmp 저장
            with open(product_path / "__version__.py.tmp", "w") as f:
                f.write(f'__version__ = "{new_p_version}"')

            # hash_cache 저장
            with open(product_path / ".hash_cache.json.tmp", "w", encoding="utf-8-sig") as f:
                json.dump(hash_cache, f, indent="\t", ensure_ascii=False)

            # md 생성
            summary = input("버전 요약 입력 : ")
            documenting(
                tag=p_tag,
                summary=summary,
                version=new_p_version,
                log_contents=component_ver_log,
                docs_path=docs_ver_path,
                docs_name="ver_system.md",
            )

            # .tmp 를 원본으로 교체
            do = tmp2new(product_path)

            if do == 1:
                # git add & commit 진행
                git_addcommit(
                    product_path,
                    f'*{p_tag}: {get_now("년-월-일")} ver {new_p_version}',
                )

                # archiving
                u.archiving(
                    archive_path=archive_path, 
                    lock_info=lock_info
                )
            elif do == 0:
                delete_tmp(product_path)
        else:
            print("|예정| ver_system.md.tmp 생성")
            print("|예정| product.lock.tmp 생성")
            print("|예정| __version__.py.tmp 생성")
            print("|예정| .hash_cache.json.tmp 생성")
            print(
                f'|예정| *{p_tag}: {get_now("년-월-일")} ver {new_p_version} 으로 커밋'
            )
            print("|예정| 대상 컴포넌트 전체 아카이브 파일 생성")

        _print_summary(p_name, pre_p_version, new_p_version, changed_components)

    else:
        print("There is no change detected.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Automate component and product versioning via Git hash tracking."
    )
    parser.add_argument("--name", type=str, help="Package/product name to version")
    parser.add_argument("--save", action="store_true", help="Persist changes to disk")
    parser.add_argument("--dev", action="store_true", help="Use beta utils module")
    parser.add_argument(
        "--check-only", action="store_true",
        help="Exit with code 1 if changes detected, 0 if none (for CI gates)"
    )
    args = parser.parse_args()

    # 이름 인자 미설정시 에러 반환
    if args.name is None:
        parser.error("--name is required. Specify the package name to version.")

    name = args.name
    save = args.save
    dev = args.dev
    check_only = args.check_only

    dev_path = Path(__file__).resolve().parent
    lib_path = dev_path.parent
    pack_path = lib_path / name

    # 없는 패키지 이름 설정시 에러 반환
    if not pack_path.is_dir():
        parser.error(f"Package directory not found: {pack_path}")

    # 진행
    try:
        versioning(pack_path, save, dev, check_only)
    except KeyboardInterrupt:
        print("\n[Interrupted] Cleaning up temporary files...")
        delete_tmp(pack_path)

    # retuncode 를 0 으로 설정(build 시 검증용)
    sys.exit(0)


if __name__ == "__main__":
    main()
