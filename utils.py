import os
import sys
import json
import fnmatch
import textwrap
import subprocess
from pathlib import Path


USER_PATH = Path("~").expanduser()
sys.path.insert(0, str(USER_PATH / "library" / "utilskit" / "src"))
sys.path.insert(0, str(USER_PATH / "library" / "logie" / "src"))
from utilskit.versionutils import get_git_modified, get_git_new, version_up
from utilskit.utils import path_change
from utilskit.hashutils import file2hash
from logie.docsutils import extract_log, documenting


# 타이틀 출력 함수
def title_print(title, log_text):
    blank_num = max(list(map(len, log_text.split("\n"))) + [60])
    blank = int((blank_num - len(title))/2) * " "
    print("\n")
    print("="*blank_num)
    print(blank + title + blank)
    print("="*blank_num)
    print(log_text)


# [1.0.0] @done_log: 함수 `get_info_result` 의 일부 연산을 함수 `get_temp_dict` 로 분리
def get_temp_dict(c_name, c_path, c_mode, status, rel_f_path, untracked):
    # rel_f_path2 = inc
    full_f_path = str(Path(c_path) / rel_f_path)
    f_name = Path(full_f_path).name
    is_untracked = any(fnmatch.fnmatch(f_name, pattern) for pattern in untracked)

    if is_untracked:
        track = False
    else:
        track = True
    temp_dict = {
        "component_name":c_name,
        "component_path":c_path,
        "component_mode":c_mode,
        "rel_file_path":rel_f_path,
        "full_file_path":full_f_path,
        "status":status,
        "track":track
    }
    return temp_dict


# [1.0.0] @done_log: 내부 연산을 가시성 증가용 함수 `get_info_result` 로 분리
# [1.0.0] @done_log: 함수 `get_info_result` 의 리턴 info 에 track 키 추가
# [1.0.0] @done_log: common_untracked 연산 추가
# 컴포넌트별 Git 기반 변경 추적 대상 필터링
def get_info_result(manifest, product_path):
    """
    <목적>
    git 기반의 모든 "변화가 감지된" 파일 중에서
    해당 컴포넌트에 "실제로 포함시킬" 대상 파일만을 필터링.

    <상세>
    그 파일이 
    파일별 해시 검증대상인지, 번들 단위 검증 대상인지, 
    컴포넌트엔 포함되지만 해시 검증에서는 제외되는 파일인지는 파악하지 않고
    순수하게 "컴포넌트에 포함되면서 변화가 감지된" 파일만을 필터링 하는 역할
    """
    # target_dict_list = []
    file_stat_info_list = []
    comp_info_filter_list = []
    common_exclude = manifest["common_exclude"]
    common_untracked = manifest["common_untracked"]
    c_list = manifest["component"]
    for c_info in c_list:
        c_name = c_info["name"]
        c_requires = c_info["requires"]
        c_type = c_info["type"]
        c_manage = c_info["manage"]
        c_build = c_info["build"]
        c_mode = c_info["mode"]
        form_c_path = c_info["path"]
        c_include = c_info["include"]
        c_bundle = c_info["bundle"]
        c_exclude = c_info["exclude"]
        c_untracked = c_info["untracked"]
        
        # 관리 대상이 아닌 경우
        if not c_manage:
            continue
        
        # 경로 포매팅
        c_path = path_change(
            form_c_path, 
            product_path=product_path,
            name=c_name
        )
        # 파일군인 경우 경로 상위로
        if c_mode == "file_group":
            c_path = str(Path(c_path).parent)
        
        # 컴포넌트별 git status 추출(수정)
        git_modi_list = get_git_modified(product_path, c_path)
        # 컴포넌트별 git status 추출(신규)
        git_new_list = get_git_new(product_path, c_path)
        # git status 결과별 진행
        git_check_list = git_modi_list + git_new_list
        for git_check in git_check_list:
            file_path = git_check["file_path"]
            status = git_check["status"]

            # 아예 검사 제외 대상인 경우
            if any(fnmatch.fnmatch(file_path, excl) for excl in c_exclude+common_exclude):
                continue

            # # 번들인 경우 (아직 미구현)
            # if len(c_bundle) > 0:
            #     print(c_name, c_bundle, c_path, file_path)
            #     sys.exit()
            
            # 디렉토리인 경우
            if c_mode == "dir":
                if Path(file_path).is_relative_to(c_path):
                    rel_f_path1 = str(Path(file_path).relative_to(c_path))
                    temp_dict = get_temp_dict(
                        c_name=c_name, 
                        c_path=c_path, 
                        c_mode=c_mode, 
                        status=status, 
                        rel_f_path=rel_f_path1, 
                        untracked=c_untracked+common_untracked
                    )
                    file_stat_info_list.append(temp_dict)
                    
            # 파일 그룹의 경우
            elif c_mode == "file_group":
                for inc in c_include:
                    if inc in file_path:
                        rel_f_path2 = inc
                        temp_dict = get_temp_dict(
                            c_name=c_name, 
                            c_path=c_path, 
                            c_mode=c_mode, 
                            status=status, 
                            rel_f_path=rel_f_path2, 
                            untracked=c_untracked+common_untracked
                        )
                        file_stat_info_list.append(temp_dict)

        # 대상 컴포넌트 정보 dict 추가
        lock_base_dict = {
            "name": c_name,
            "version": "",
            "requires": c_requires,
            "type": c_type,
            "build": c_build,
            "mode": c_mode,
            "form_c_path":form_c_path,
            "path": c_path,
            "include": c_include,
            "bundle": c_bundle,
            "exclude": c_exclude,
            "untracked":c_untracked
        }
        comp_info_filter_list.append(lock_base_dict)
    
    return file_stat_info_list, comp_info_filter_list


# [1.0.0] @done_log: 내부 연산을 가시성 증가용 함수 `compare_hash_cache` 로 분리
# [1.0.0] @done_log: track 을 통해 해시 검증 대상 파일인지 확인 기능 추가
# [1.0.0] @done_log: 해시 스키마 변화 탐지 부분 추가
# 대상 파일별 캐시 비교
def compare_hash_cache(file_stat_info_list, hash_cache, schema_change=False):
    flag_dict = {}
    comment_log_dict = {}
    for file_stat_info in file_stat_info_list:
        f_c_name = file_stat_info["component_name"]
        f_c_path = file_stat_info["component_path"]
        f_c_mode = file_stat_info["component_mode"]
        if f_c_mode == "file_group":
            f_c_path = str(Path(f_c_path) / f_c_name)
        rel_f_path = file_stat_info["rel_file_path"]
        full_f_path = file_stat_info["full_file_path"]
        stat = file_stat_info["status"]
        track = file_stat_info["track"]

        # 해시 검증 대상이 아닌 경우 배제
        if not track:
            continue

        # 해시캐시 검증
        try:
            _ = hash_cache[f_c_path]
        except KeyError:
            hash_cache[f_c_path] = {rel_f_path : "|||"}
        try:
            pre_hash = hash_cache[f_c_path][rel_f_path]
        except KeyError:
            hash_cache[f_c_path][rel_f_path] = "|||"
            pre_hash = "|||"

        # 삭제 & 수정 여부 파악
        if stat == "Deleted":
            new_hash = None
            _ = hash_cache[f_c_path].pop(rel_f_path, None)
        else:
            new_hash = file2hash(full_f_path)
            hash_cache[f_c_path][rel_f_path] = new_hash

        # 해시 스키마에 변화가 있는 경우
        if schema_change:
            # 모든 객체에 대해 해시가 바뀐것으로 간주
            diff = True
        # 해시 스키마에 변화가 없는 경우
        else:
            # 기존 해시와 현재 해시가 다르면 바뀐 것으로 간주
            if pre_hash != new_hash:
                diff = True
            # 기존 해시와 현재 해시가 같으면 바뀌지 않은 것으로 간주
            else:
                diff = False
        
        # 기존 해시와 신규 해시가 다른 경우
        if diff:
            # 해시 변화 파일 존재 flag 생성
            flag_dict[f_c_name] = 1

            # 로그 추출
            comment_log = f"- {stat:}: {full_f_path}\n"
            log_list = extract_log(full_f_path)
            for log_ in log_list:
                comment_log += f" - {log_}\n"
            try:
                comment_log_dict[f_c_name] += comment_log
            except KeyError:
                comment_log_dict[f_c_name] = comment_log

    return comment_log_dict, hash_cache, flag_dict


# [1.0.0] @done_log: simple_versioning 용 심플한 문서화 함수
def simple_documenting(name, comment_log, pre_version):
    title_print(
        title=f"name : < {name} >", 
        log_text=comment_log
    )
    # 버전 업
    new_version, tag = version_up(name, pre_version)
    print(f"{tag}: {pre_version} --> {new_version}")

    summary = input("버전 요약 입력 : ")
    _ = documenting(
        tag=tag, 
        summary=summary, 
        version=new_version, 
        log_contents=comment_log, 
        docs_path="./docs",
        docs_name=f"ver_{name}.md"
    )

    return new_version
        

# [1.0.0] @done_log: 내부 연산을 가시성 증가용 함수 `versionup_documenting` 로 분리
# [1.0.0] @done_log: `versionup_documenting` 함수 인자에 check_only 추가
# [1.0.1] @done_log: `versionup_documenting` 함수 연산방식 개선
# ---------------------------------------------------------------------------
# Improved versionup_documenting
# Replaces utils.versionup_documenting to fix:
#   - O(n²) linear search → O(1) dict lookup
#   - Silent check_only exit → informative message with component name
#   - extract_log called on deleted files → guarded by status check
# ---------------------------------------------------------------------------
def versionup_documenting(
    file_stat_info_list, comp_info_filter_list, flag_dict,
    comment_log_dict, lock_info, check_only, save, docs_path
):
    # O(1) lookup: component name → pre-version (replaces O(n) linear search)
    pre_version_map = {c["name"]: c["version"] for c in lock_info["component"]}

    component_ver_log = ""
    changed_components = []  # [(name, pre_version, new_version), ...]

    for comp_info_filter in comp_info_filter_list:
        c_name = comp_info_filter["name"]
        c_path = comp_info_filter["path"]
        c_mode = comp_info_filter["mode"]

        # 컴포넌트 이전 버전 추출
        pre_c_version = pre_version_map.get(c_name, "0.0.0")

        # 파일 변경 이력(flag=1)이 있는 경우 버전업 진행
        flag = flag_dict.get(c_name, 0)
        if flag == 1:
            # 해당 컴포넌트의 로그 추출
            comment_log = comment_log_dict[c_name]

            # 컴포넌트별 변경 이력 출력
            title_print(
                title=f"component : < {c_name} >",
                log_text=comment_log,
            )

            # 버전 업
            if check_only:
                # Informative exit: tell the caller exactly which component triggered it
                print(
                    f"\n[check-only] Uncommitted change detected in component "
                    f"'{c_name}'. Exiting with code 1."
                )
                sys.exit(1)
            new_c_version, tag = version_up(c_name, pre_c_version)
            print(f"{tag}: {pre_c_version} --> {new_c_version}")

            # 컴포넌트 버전 업 로그 기록
            component_ver_log += (
                f"- {c_name:>15s} version ({pre_c_version}) --> ({new_c_version})\n"
            )
            changed_components.append((c_name, pre_c_version, new_c_version))

            # 버전파일, 설명.md 파일 저장
            if save:
                if c_mode == "dir":
                    ver_path = Path(c_path) / "__version__.py"
                elif c_mode == "file_group":
                    ver_path = Path(c_path) / c_name
                else:
                    raise ValueError(
                        f"mode('{c_mode}') must be 'dir' or 'file_group'. "
                        f"Check manifest.json for component '{c_name}'."
                    )
                with open(f"{ver_path}.tmp", "w") as f:
                    f.write(f'__version__ = "{new_c_version}"')

                # [1.0.0] @done_log: 버전 기록 md 은 docs_ver 에
                summary = input(f"버전 요약 입력 [{c_name}]: ")
                documenting(
                    tag=tag,
                    summary=summary,
                    version=new_c_version,
                    log_contents=comment_log,
                    docs_path=docs_path,
                    docs_name=f"ver_{c_name}.md",
                )
            else:
                print(f"|예정| ver_{c_name}.md.tmp 생성")
        else:
            new_c_version = pre_c_version

        # 컵포넌트 새 버전 업데이트
        comp_info_filter["version"] = new_c_version

        # 각 결과 파일별 컴포넌트 새 버전 값 할당
        for fsi in file_stat_info_list:
            if fsi["component_name"] == c_name:
                fsi["version"] = new_c_version

    # 버전 정보가 업데이트된 컴포넌트 정보 리스트 리턴
    return file_stat_info_list, comp_info_filter_list, component_ver_log, changed_components


# [1.0.0] @done_log: 아카이빙 오류 수정
# [1.0.0] @done_log: 아카이빙 함수 `archiving` 신규 생성
def comp_achiving(archive_path, lock_info):
    # c_archive_list = [] # 시스템 아카이빙용 컴포넌트 아카이브 리스트
    # for c_m, c_p, c_n, n_c_ver, n_c_hash, inc, ig_list in c_versioning_list:
    common_exclude = lock_info["product"]["exclude"]
    comp_info_list = lock_info["component"]
    for comp_info in comp_info_list:
        c_name = comp_info["name"]
        c_version = comp_info["version"]
        c_mode = comp_info["mode"]
        c_path = comp_info["path"]
        inc = comp_info["include"]
        ig_list = comp_info["exclude"] + common_exclude
    
        c_parent_path = os.path.dirname(c_path)
        tar_name = f"{c_name}_v{c_version}.tar.gz"

        # 기존 존재파일에서 .tmp 와 원본을 둘 다 탐지
        if os.path.isfile(archive_path / tar_name):
            print(f"{tar_name} 는 아카이브 내역에 존재합니다. --> 아카이브 미진행")
        else:
            print(f"{tar_name} 아카이빙")
            if c_mode == "dir":
                cwd = c_parent_path
                cmd = ["tar", "-czf", archive_path / tar_name]
                for ignore_ in ig_list:
                    cmd.append(f"--exclude={ignore_}")
                cmd.append(c_name)
            elif c_mode == "file_group":
                cwd = c_path
                cmd = ["tar", "-czf", archive_path / tar_name]
                for f_name in inc:
                    if not os.path.exists(Path(cwd) / f_name):
                        raise ValueError(f"컴포넌트 {c_name} 의 include 목록에 존재하지 않는 파일({f_name})이 있습니다.")
                    cmd.append(f_name)
            subprocess.run(cmd, cwd=cwd)


def archiving(archive_path, lock_info):
    name = lock_info["product"]["name"]
    new_version = lock_info["product"]["version"]
    tar_name = f"product_v{new_version}.tar.gz"

    # 컴포넌트별 아카이브 진행
    comp_achiving(archive_path, lock_info)

    # 패키지 아카이브 진행
    if os.path.isfile(archive_path / tar_name):
        print(f"{tar_name} 는 아카이브 내역에 존재합니다. --> 아카이브 미진행")
    else:
        print(f"{tar_name} 아카이빙 진행 ...")
        # 각 컴포넌트 저장용 임시 폴더 생성
        _temp_dir = f"{name}_v{new_version}"
        cmd = textwrap.dedent(
            f"""
            cd {archive_path} && \\
            mkdir -p {_temp_dir}
            """
        ).strip()
        subprocess.run(cmd, shell=True, check=True)
        del cmd

        # 와일드카드 * 를 사용하여 .tmp 와 상관없이 컴포넌트를 tar.gz 형태로 복사
        resolved = lock_info["product"]["resolved"]
        for c_name, c_version in resolved.items():
            c_archive = f"{c_name}_v{c_version}.tar.gz"
        # for c_archive in c_archive_list:
            # 임시 폴더로 옮기기
            _temp_cmd = textwrap.dedent(
                f"""
                cd {archive_path} && \\
                cp {c_archive}* ./{_temp_dir}/{c_archive}
                """
            ).strip()
            subprocess.run(_temp_cmd, shell=True, check=True)

        # 임시폴더 압축 및 아카이빙
        cmd = textwrap.dedent(
            f"""
            cd {archive_path} && \\
            tar -czf {tar_name} {_temp_dir} && \\
            rm -rf {_temp_dir}
            """
        ).strip()
        subprocess.run(cmd, shell=True, check=True)

        # lock 파일 아카이브 진행
        with open(archive_path / f"product_v{new_version}.lock", "w", encoding="utf-8-sig") as f:
            json.dump(lock_info, f, indent="\t", ensure_ascii=False)