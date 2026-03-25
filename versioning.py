import sys
import os
import copy

import json
import argparse

from datetime import datetime
from pathlib import Path


USER_PATH = Path("~").expanduser()
sys.path.insert(0, str(USER_PATH / "library" / "dev_tools")) 
sys.path.insert(0, str(USER_PATH / "library" / "utilskit" / "src"))
sys.path.insert(0, str(USER_PATH / "library" / "logie" / "src"))
from utilskit.timeutils import get_now
from utilskit.versionutils import version_up, git_addcommit
from logie.docsutils import log2donelog, documenting, tmp2new, delete_tmp


# [1.0.0] @done_log: GitPython 활용에 맞춰서 버저닝 구조 대폭 변경
def versioning(product_path, save, dev, check_only):

    if dev:
        from beta import utils as u
    else:
        import utils as u

    # 패키지 경로
    # pack_path = lib_path / name
    archive_path = product_path / "archive"
    docs_ver_path = product_path / "docs_ver"

    # manifest.json 읽기
    with open(product_path / "manifest.json", "r", encoding="utf-8-sig") as f:
        manifest = json.load(f)

    # lock 불러오기
    with open(product_path / "product.lock", "r", encoding="utf-8-sig") as f:
        pre_lock_info = json.load(f)
    lock_info = copy.deepcopy(pre_lock_info)

    # .hash_cache.json 읽기
    if os.path.isfile(product_path / ".hash_cache.json"):
        with open(product_path / ".hash_cache.json", "r", encoding="utf-8-sig") as f:
            pre_hash_cache = json.load(f)
    else:
        pre_hash_cache = {}
    hash_cache = copy.deepcopy(pre_hash_cache)

    # ===============================================================
    # 컴포넌트별 변경 대상 파일 리스트 최초 필터링
    file_stat_info_list, comp_info_filter_list = u.get_info_result(
        manifest=manifest, 
        product_path=product_path
    )
    # ==================================================================
    # [1.0.0] @done_log: 해시 스키마 버전 비교 추가
    try:
        cache_hash_schema_ver = hash_cache["schema_version"]
        lock_hash_schema_ver = lock_info["product"]["hash_schema_version"]
        if cache_hash_schema_ver == lock_hash_schema_ver:
            schema_change = False
        else:
            schema_change = True
    except KeyError:
        if dev:
            schema_change = True
        else:
            schema_change = False

    # 대상 파일 별 해시 비교 및 로그 주석 추출
    comment_log_dict, hash_cache, flag_dict = u.compare_hash_cache(
        file_stat_info_list=file_stat_info_list, 
        hash_cache=hash_cache,
        schema_change=schema_change
    )
    # ==================================================================
    # 버전 업 & document 생성
    _result = u.versionup_documenting(
        file_stat_info_list=file_stat_info_list, 
        comp_info_filter_list=comp_info_filter_list, 
        flag_dict=flag_dict,
        comment_log_dict=comment_log_dict, 
        lock_info=lock_info, 
        check_only=check_only,
        save=save, 
        docs_path=docs_ver_path
    )

    file_stat_info_list = _result[0]
    comp_info_filter_list = _result[1]
    component_ver_log = _result[2]

    # ==================================================================
    # 각 대상 파일 별 @log 를 @done_log 로 변경
    for file_stat_info in file_stat_info_list:
        full_f_path = file_stat_info["full_file_path"]
        new_f_version = file_stat_info["version"]
        if save:
            try:
                log2donelog(full_f_path, new_f_version)
            except FileNotFoundError:
                pass
            except UnicodeDecodeError:
                pass
        else:
            print(f"|예정| {full_f_path} 의 주석을 done 으로 변경")

    # ==================================================================
    # 컴포넌트의 변경이 있는 경우 패키지 버전업 진행
    if any(c_flag == 1 for c_flag in flag_dict.values()):
        # 현 패키지 이름
        p_name = product_path.name

        # 이전 패키지 버전, 해시 정보 추출
        pre_p_version = lock_info["product"]["version"]

        # 패키지 버전 업 & 로그 document 생성
        if len(file_stat_info_list) > 0:
            
            # 컴포넌트별 변경 이력 출력
            u.title_print(
                title=f"product : < {p_name} >",
                log_text=component_ver_log
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
        lock_info["product"]["resolved"] = {ci["name"]:ci["version"] for ci in comp_info_filter_list}
        lock_info["product"]["exclude"] = manifest["common_exclude"]
        lock_info["product"]["hash_schema_version"] = cache_hash_schema_ver
        lock_info["component"] = comp_info_filter_list
        
        # 저장
        if save:
            with open(product_path / "product.lock.tmp", "w", encoding="utf-8-sig") as f:
                json.dump(lock_info, f, indent="\t", ensure_ascii=False)

            # __version__.py.tmp 저장
            with open(product_path / "__version__.py.tmp", 'w') as f:
                f.write(f'__version__ = "{new_p_version}"')

            # hash_cache 저장
            with open(product_path / ".hash_cache.json.tmp", "w", encoding="utf-8-sig") as f:
                json.dump(hash_cache, f, indent="\t", ensure_ascii=False)

            # md 생성
            summary = input("버전 요약 입력 : ")
            _ = documenting(
                tag=p_tag, 
                summary=summary, 
                version=new_p_version, 
                log_contents=component_ver_log,
                docs_path=docs_ver_path,
                docs_name="ver_system.md"
            )
        else:
            print("|예정| ver_system.md.tmp 생성")
        
        # ==================================================================
        # 저장    
        if save:
            
            # .tmp 를 원본으로 교체
            do = tmp2new(product_path)

            if do == 1:
                # git add & commit 진행
                git_addcommit(product_path, f'*{p_tag}: {get_now("년-월-일")} ver {new_p_version}')

                # archiving
                u.archiving(
                    archive_path=archive_path, 
                    lock_info=lock_info
                )
            if do == 0:
                delete_tmp(product_path)
        else:
            print(f"|예정| release.md.tmp 생성")
            print(f"|예정| pyproject.toml.tmp 생성")
            print(f"|예정| .hash_cache.json.tmp 생성")
            print(f'|예정| *{p_tag}: {get_now("년-월-일")} ver {new_p_version} 으로 커밋')
            print(f"|예정| 대상 컴포넌트 전체 아카이브 파일 생성")
    else: 
        print("There is no change detected.")


# [1.0.0] @done_log: dev_tools 에서 versioning 을 통해 각 패키지의 버저닝을 진행
# [1.0.0] @done_log: versioning 실행시 exit code를 받을 수 있도록 기본값을 가진 check_only 인자를 추가
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", type=str)
    parser.add_argument("--save", action="store_true")  # 향후 이거로 변경
    # parser.add_argument("--save", type=bool, default=False)
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    name = args.name
    save = args.save
    dev = args.dev
    check_only = args.check_only

    # 경로설정
    dev_path = Path(__file__).resolve().parent
    lib_path = dev_path.parent
    pack_path = lib_path / name

    # 이름 인자 미설정시 에러 반환
    try:
        os.path.isdir(lib_path / name)
    except TypeError:
        raise ValueError(f"You must specify a package name variable --name")

    # 없는 패키지 이름 설정시 에러 반환
    if not os.path.isdir(lib_path / name):
        raise ValueError(f"There is no package name {name}")
    
    # 진행
    try:
        versioning(pack_path, save, dev, check_only)
    except KeyboardInterrupt:
        delete_tmp(pack_path)
    
    # retuncode 를 0 으로 설정(build 시 검증용)
    sys.exit(0)

if __name__ == "__main__":
    main()

