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


def _process_versioning_and_logging(item_name, target_dict, file_paths, u, lo, save):
    """
    단일 파일 또는 폴더 단위의 로그를 취합하여 버전업 및 @log -> @done_log 변경을 수행하는 헬퍼 함수
    """
    all_logs = []
    
    # 1. 대상 파일(들)에서 로그 추출 및 병합
    for file_path in file_paths:
        extracted = lo.extract_log(file_path)
        if extracted:
            all_logs.extend(extracted)
            
    # 로그가 없는 경우의 기본값 처리
    if not all_logs:
        comment_log = "- (업데이트 내역 생략 / 자동 감지)"
    else:
        comment_log = "- " + "\n- ".join(all_logs)

    # 2. 버전 문서화 진행 및 새 버전 발급
    pre_version = target_dict[item_name]
    new_version = u.simple_documenting(item_name, comment_log, pre_version)
    target_dict[item_name] = new_version

    # 3. 각 파일의 @log 를 새 버전이 찍힌 @done_log 로 변경
    for file_path in file_paths:
        if save:
            try:
                # log2donelog 가 file_path 와 new_version 을 인자로 받는다고 가정
                from logie.docsutils import log2donelog
                log2donelog(file_path, new_version)
            except FileNotFoundError:
                pass
        else:
            print(f"|예정| {file_path} 의 주석을 [{new_version}] done 으로 변경")


# [1.1.0] @done_log: version_dict 의 구조 변경에 맞춰 simple 버저닝 방식도 변경
def versioning(tools_path, save, dev):
    if dev:
        from beta import utils as u
    else:
        import utils as u

    from utilskit import versionutils as vu
    import logie as lo
    from logie.docsutils import tmp2new, delete_tmp

    with open(Path(tools_path) / "version_dict.json", "r", encoding="utf-8-sig") as f:
        version_dict = json.load(f)

    valid_dir_list = list(version_dict["dir"].keys())
    valid_file_list = list(version_dict["file"].keys())

    # [1.1.0] @done_log: 폴더용 플래그 및 변경된 파일 경로를 담을 dict 생성
    dir_flag_dict = dict.fromkeys(valid_dir_list, 0)
    dir_changed_files = {d: [] for d in valid_dir_list} 
    
    # 파일용 변경 타겟 리스트
    file_changed_targets = []

    # ---------------------------------------------------------
    # Step 1: Git 변경 사항 스캔 및 분류 (플래그 수집)
    # ---------------------------------------------------------
    git_modi_list = vu.get_git_modified(tools_path, tools_path)
    git_new_list = vu.get_git_new(tools_path, tools_path)
    git_check_list = git_modi_list + git_new_list

    for git_check in git_check_list:
        file_path = git_check["file_path"]
        dir_name = Path(file_path).parent.name
        file_name = Path(file_path).name
        
        # 1-A. 폴더 단위 검증인 경우
        if dir_name in valid_dir_list:
            dir_flag_dict[dir_name] = 1                 # 플래그 활성화
            dir_changed_files[dir_name].append(file_path) # 로그 추출을 위해 파일 경로 보관
            continue

        # 1-B. 파일 단위 검증인 경우
        if file_name in valid_file_list:
            file_changed_targets.append((file_name, file_path))

    # ---------------------------------------------------------
    # Step 2: 수집된 타겟들을 대상으로 버전업 & 로깅 수행
    # ---------------------------------------------------------
    
    # 2-A. 단일 파일 처리
    for file_name, file_path in file_changed_targets:
        _process_versioning_and_logging(
            item_name=file_name,
            target_dict=version_dict["file"],
            file_paths=[file_path],
            u=u, lo=lo, save=save
        )

    # 2-B. 폴더 단위 처리 (플래그 값이 1인 경우만)
    for dir_name, flag in dir_flag_dict.items():
        if flag == 1:
            _process_versioning_and_logging(
                item_name=dir_name,
                target_dict=version_dict["dir"],
                file_paths=dir_changed_files[dir_name], # 폴더 내 변경된 모든 파일 전달
                u=u, lo=lo, save=save
            )

    # ---------------------------------------------------------
    # Step 3: 최종 저장 및 마무리
    # ---------------------------------------------------------
    if save:
        do = tmp2new(tools_path)
        with open(Path(tools_path) / "version_dict.json", "w", encoding="utf-8-sig") as f:
            json.dump(version_dict, f, indent="\t", ensure_ascii=False)

        if do == 1:
            # from utilskit.timeutils import get_now
            vu.git_addcommit(tools_path, f'*upload: {get_now("년-월-일")}')
        if do == 0:
            delete_tmp(tools_path)
    else:
        # from utilskit.timeutils import get_now
        print(f"|예정| release.md.tmp 생성")
        print(f"|예정| pyproject.toml.tmp 생성")
        print(f"|예정| .hash_cache.json.tmp 생성")
        print(f'|예정| *upload: {get_now("년-월-일")} 으로 커밋')
        print(f"|예정| 대상 컴포넌트 전체 아카이브 파일 생성")
        
    sys.exit()


# def versioning(tools_path, save, dev):
#     if dev:
#         from beta import utils as u
#     else:
#         import utils as u

#     # from utilskit import versionutils as vu
#     from utilskit import versionutils as vu
#     import fnmatch
#     import logie as lo

#     # tools_path = Path(__file__).resolve().parent
#     with open(Path(tools_path) / "version_dict.json", "r", encoding="utf-8-sig") as f:
#         version_dict = json.load(f)

#     valid_dir_list = list(version_dict["dir"].keys())
#     valid_file_list = list(version_dict["file"].keys())

#     dir_flag_dict = dict.fromkeys(valid_dir_list, 0)

#     # 컴포넌트별 git status 대상 추출
#     git_modi_list = vu.get_git_modified(tools_path, tools_path)
#     git_new_list = vu.get_git_new(tools_path, tools_path)
#     git_check_list = git_modi_list + git_new_list
#     for git_check in git_check_list:
#         file_path = git_check["file_path"]
#         dir_name = Path(file_path).parent.name
#         file_name = Path(file_path).name
        
#         # 폴더 단위 검증인 경우 패쓰
#         if dir_name in valid_dir_list:
#             continue

#         # 파일 단위 검증인 경우
#         if file_name not in valid_file_list:
#             continue

#         pre_version = version_dict["file"][file_name]
#         log_list = lo.extract_log(file_path)
#         comment_log = "\n- ".join(log_list)
#         comment_log = "- " + comment_log

#         # 
#         new_version = u.simple_documenting(file_name, comment_log, pre_version)
#         version_dict["file"][file_name] = new_version

#         # 각 대상 파일 별 @log 를 @done_log 로 변경
#         if save:
#             try:
#                 log2donelog(file_path, new_version)
#             except FileNotFoundError:
#                 pass
#         else:
#             print(f"|예정| {file_path} 의 주석을 done 으로 변경")


#     if save:
#         # .tmp 를 원본으로 교체
#         do = tmp2new(tools_path)
#         # [0.1.0] @done_log: version dict 저장되도록 수정
#         with open(Path(tools_path) / "version_dict.json", "w", encoding="utf-8-sig") as f:
#             json.dump(version_dict, f, indent="\t", ensure_ascii=False)

#         if do == 1:
#             # git add & commit 진행
#             git_addcommit(tools_path, f'*upload: {get_now("년-월-일")}')

#             # # archiving
#             # u.archiving(
#             #     archive_path=archive_path, 
#             #     lock_info=lock_info
#             # )
#         if do == 0:
#             delete_tmp(tools_path)
#     else:
#         print(f"|예정| release.md.tmp 생성")
#         print(f"|예정| pyproject.toml.tmp 생성")
#         print(f"|예정| .hash_cache.json.tmp 생성")
#         print(f'|예정| *upload: {get_now("년-월-일")} 으로 커밋')
#         print(f"|예정| 대상 컴포넌트 전체 아카이브 파일 생성")
#     sys.exit()


# [0.0.1] @done_log: dev_tools 에서 versioning 을 통해 각 패키지의 버저닝을 진행
# [0.0.1] @done_log: versioning 실행시 exit code를 받을 수 있도록 기본값을 가진 check_only 인자를 추가
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    save = args.save
    dev = args.dev

    # 경로설정
    tools_path = str(Path(__file__).resolve().parent)
    
    # 진행
    try:
        versioning(tools_path, save, dev)
    except KeyboardInterrupt:
        delete_tmp(tools_path)
    
    # retuncode 를 0 으로 설정(build 시 검증용)
    sys.exit(0)

if __name__ == "__main__":
    main()

